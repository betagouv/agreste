#!/usr/bin/env python3
"""Run a RAG query against the Albert API.

Auth: set ALBERT_API_KEY (Bearer). Optional ALBERT_API_BASE_URL overrides the
default https://albert.api.etalab.gouv.fr. Collection id may come from
--collection-id or ALBERT_COLLECTION_ID. Chat model from --model or ALBERT_MODEL
(default: openweight-small). List models with GET /v1/models.

Flow (official Albert RAG guide: search, then prompt, then chat):

    flowchart LR
      query[Query] --> search["POST /v1/search"]
      search --> show["Optionally print chunks"]
      search --> prompt[Build prompt with excerpts]
      prompt --> chat["POST /v1/chat/completions"]
      chat --> answer[Print answer]

Usage:
  export ALBERT_API_KEY=...
  export ALBERT_COLLECTION_ID=123
  python scripts/albert/albert_rag_query.py "Quelle est la production de blé en 2024 ?"
  python scripts/albert/albert_rag_query.py "..." --show-chunk-text
  python scripts/albert/albert_rag_query.py "..." --system-prompt-file my_prompt.txt
  python scripts/albert/albert_rag_query.py "..." --collection-id 123 --model openweight-small
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://albert.api.etalab.gouv.fr"
DEFAULT_MODEL = "openweight-small"
DEFAULT_LIMIT = 10
DEFAULT_METHOD = "semantic"
SEARCH_METHODS = ("semantic", "hybrid", "lexical")

SYSTEM_PROMPT = """\
Réponds uniquement en t'appuyant sur les documents fournis, et de façon concise.
Si les documents ne permettent pas de répondre, dis-le clairement.

À la fin de ta réponse, ajoute une section « Sources » listant chaque extrait utilisé, avec :
- le nom du document
- l'identifiant du document (document_id)
- l'identifiant du chunk (chunk_id)

Format attendu pour chaque source :
- document: <nom> | document_id: <id> | chunk_id: <id>
"""


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _request_json(
    url: str,
    *,
    headers: dict[str, str],
    method: str = "GET",
    data: bytes | None = None,
    timeout: float = 120,
) -> tuple[int, object]:
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            parsed = detail
        return exc.code, parsed
    except urllib.error.URLError as exc:
        raise SystemExit(f"Network error calling {url}: {exc.reason}") from exc

    if not body:
        return status, {}
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, body


def resolve_collection_id(cli_id: int | None) -> int:
    if cli_id is not None:
        return cli_id
    env_id = os.environ.get("ALBERT_COLLECTION_ID", "").strip()
    if not env_id:
        raise SystemExit("Provide --collection-id or set ALBERT_COLLECTION_ID")
    try:
        return int(env_id)
    except ValueError as exc:
        raise SystemExit(f"ALBERT_COLLECTION_ID must be an integer, got {env_id!r}") from exc


def search_chunks(
    base_url: str,
    api_key: str,
    *,
    query: str,
    collection_id: int,
    limit: int,
    method: str,
) -> list[dict]:
    url = f"{base_url.rstrip('/')}/v1/search"
    payload = {
        "query": query,
        "collection_ids": [collection_id],
        "limit": limit,
        "method": method,
    }
    status, body = _request_json(
        url,
        headers=_auth_headers(api_key),
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
    )
    if status not in (200, 201) or not isinstance(body, dict):
        raise SystemExit(f"Search failed (HTTP {status}): {body}")
    data = body.get("data")
    if not isinstance(data, list):
        raise SystemExit(f"Unexpected search response shape: {body}")
    return data


def document_name_from_chunk(chunk: dict) -> str | None:
    metadata = chunk.get("metadata")
    if isinstance(metadata, dict):
        for key in ("document_name", "filename", "file_name", "name", "title"):
            value = metadata.get(key)
            if value:
                return str(value)
    name = chunk.get("name")
    if name:
        return str(name)
    return None


def fetch_document_names(
    base_url: str,
    api_key: str,
    document_ids: set[int],
) -> dict[int, str]:
    """Resolve document display names via GET /v1/documents/{id}."""
    names: dict[int, str] = {}
    for document_id in sorted(document_ids):
        url = f"{base_url.rstrip('/')}/v1/documents/{document_id}"
        status, body = _request_json(url, headers=_auth_headers(api_key))
        if status == 200 and isinstance(body, dict) and body.get("name"):
            names[document_id] = str(body["name"])
        else:
            names[document_id] = "(unknown)"
    return names


def resolve_hit_document_names(
    base_url: str,
    api_key: str,
    hits: list[dict],
) -> dict[int, str]:
    """Prefer chunk metadata; fall back to GET /v1/documents/{id}."""
    names: dict[int, str] = {}
    missing: set[int] = set()
    for hit in hits:
        chunk = hit.get("chunk") if isinstance(hit.get("chunk"), dict) else {}
        doc_id = chunk.get("document_id")
        if not isinstance(doc_id, int):
            continue
        from_chunk = document_name_from_chunk(chunk)
        if from_chunk:
            names[doc_id] = from_chunk
        else:
            missing.add(doc_id)
    # Only fetch ids not already known from metadata.
    missing -= set(names)
    if missing:
        names.update(fetch_document_names(base_url, api_key, missing))
    return names


def print_retrieval(
    hits: list[dict],
    *,
    document_names: dict[int, str],
    show_chunk_text: bool = False,
) -> None:
    print("=== Retrieval (POST /v1/search) ===")
    if not hits:
        print("(no chunks retrieved)")
        print()
        return
    for i, hit in enumerate(hits, start=1):
        chunk = hit.get("chunk") if isinstance(hit.get("chunk"), dict) else {}
        doc_id = chunk.get("document_id")
        chunk_id = chunk.get("id")
        score = hit.get("score")
        name = (
            (document_names.get(doc_id) if isinstance(doc_id, int) else None)
            or document_name_from_chunk(chunk)
            or "(unknown)"
        )
        score_str = f"{score:.6g}" if isinstance(score, (int, float)) else str(score)
        print(f"{i}. {name}  document_id={doc_id}  chunk_id={chunk_id}  " f"score={score_str}")
        if show_chunk_text:
            content = (chunk.get("content") or "").strip()
            method = hit.get("method")
            print(f"   method={method}")
            metadata = chunk.get("metadata")
            if metadata:
                print(f"   metadata={json.dumps(metadata, ensure_ascii=False)}")
            if content:
                for line in content.splitlines():
                    print(f"   {line}")
            else:
                print("   (empty chunk)")
            print()
    print("=== End retrieval ===")
    print()


def format_excerpt(
    index: int,
    hit: dict,
    *,
    document_names: dict[int, str],
) -> str | None:
    chunk = hit.get("chunk") if isinstance(hit.get("chunk"), dict) else {}
    content = (chunk.get("content") or "").strip()
    if not content:
        return None
    doc_id = chunk.get("document_id")
    name = (
        (document_names.get(doc_id) if isinstance(doc_id, int) else None)
        or document_name_from_chunk(chunk)
        or "(unknown)"
    )
    return (
        f"[Extrait {index}]\n"
        f"document_name: {name}\n"
        f"document_id: {doc_id}\n"
        f"chunk_id: {chunk.get('id')}\n"
        f"content:\n{content}"
    )


def build_user_prompt(
    query: str,
    hits: list[dict],
    *,
    document_names: dict[int, str],
) -> str:
    excerpts = [
        text
        for i, hit in enumerate(hits, start=1)
        if (text := format_excerpt(i, hit, document_names=document_names)) is not None
    ]
    joined = "\n\n".join(excerpts) if excerpts else "(aucun extrait)"
    return f"[Question]\n{query}\n\n" f"[Extraits]\n{joined}"


def resolve_system_prompt(cli_text: str | None, prompt_file: pathlib.Path | None) -> str:
    if cli_text and prompt_file:
        raise SystemExit("Use only one of --system-prompt or --system-prompt-file")
    if prompt_file is not None:
        path = prompt_file.expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"System prompt file not found: {path}")
        return path.read_text(encoding="utf-8")
    if cli_text is not None:
        return cli_text
    return SYSTEM_PROMPT


def chat_completion(
    base_url: str,
    api_key: str,
    *,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    status, body = _request_json(
        url,
        headers=_auth_headers(api_key),
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        timeout=300,
    )
    if status not in (200, 201) or not isinstance(body, dict):
        hint = ""
        if status == 404:
            hint = (
                f"\nModel {model!r} was not found. Pass --model / ALBERT_MODEL "
                f"(e.g. openweight-small) or list models via GET {base_url.rstrip('/')}/v1/models"
            )
        raise SystemExit(f"Chat completion failed (HTTP {status}): {body}{hint}")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise SystemExit(f"No choices in chat response: {body}")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise SystemExit(f"Unexpected chat choice shape: {choices[0]}")
    content = message.get("content")
    if content is None:
        raise SystemExit(f"Empty assistant content: {choices[0]}")
    return str(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a RAG query against the Albert API (search + chat).")
    parser.add_argument("query", help="Natural-language question")
    parser.add_argument(
        "--collection-id",
        type=int,
        default=None,
        help="Albert collection ID (default: ALBERT_COLLECTION_ID)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("ALBERT_API_BASE_URL", DEFAULT_BASE_URL),
        help=f"Albert API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("ALBERT_MODEL", DEFAULT_MODEL),
        help=(
            f"Chat model id (default: {DEFAULT_MODEL} or ALBERT_MODEL; " "see GET /v1/models for text-generation ids)"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=(f"Max number of chunks to retrieve (default: {DEFAULT_LIMIT}; " "not unique documents)"),
    )
    parser.add_argument(
        "--method",
        choices=SEARCH_METHODS,
        default=DEFAULT_METHOD,
        help=f"Search method (default: {DEFAULT_METHOD})",
    )
    parser.add_argument(
        "--show-chunk-text",
        "--show-retrieval",
        dest="show_chunk_text",
        action="store_true",
        help="Also print full retrieved chunk text (default: names + ids only)",
    )
    parser.add_argument(
        "--system-prompt",
        default=None,
        help="Override the default system prompt (text)",
    )
    parser.add_argument(
        "--system-prompt-file",
        type=pathlib.Path,
        default=None,
        help="Override the default system prompt (read from file)",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("ALBERT_API_KEY", "").strip()
    if not api_key:
        print("ALBERT_API_KEY is not set", file=sys.stderr)
        return 2

    collection_id = resolve_collection_id(args.collection_id)
    system_prompt = resolve_system_prompt(args.system_prompt, args.system_prompt_file)

    hits = search_chunks(
        args.base_url,
        api_key,
        query=args.query,
        collection_id=collection_id,
        limit=args.limit,
        method=args.method,
    )

    document_names = resolve_hit_document_names(args.base_url, api_key, hits)
    print_retrieval(
        hits,
        document_names=document_names,
        show_chunk_text=args.show_chunk_text,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": build_user_prompt(args.query, hits, document_names=document_names),
        },
    ]
    answer = chat_completion(
        args.base_url,
        api_key,
        model=args.model,
        messages=messages,
    )
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
