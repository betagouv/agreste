#!/usr/bin/env python3
"""Upload documents from a directory to the Albert API.

Auth: set ALBERT_API_KEY (Bearer). Optional ALBERT_API_BASE_URL overrides the
default https://albert.api.etalab.gouv.fr. Collection id may come from
--collection-id or ALBERT_COLLECTION_ID.

Uploads via POST /v1/documents (multipart: file + collection_id). Supported
formats per Albert RAG docs: PDF, TXT, HTML, Markdown; max 20 MB by default.

Usage:
  export ALBERT_API_KEY=...
  export ALBERT_COLLECTION_ID=123   # optional if you pass --collection-id
  python scripts/albert/upload_albert_documents.py /path/to/dir
  python scripts/albert/upload_albert_documents.py /path/to/dir --collection-id 123
  python scripts/albert/upload_albert_documents.py /path/to/dir --create-collection agreste-rag
  python scripts/albert/upload_albert_documents.py /path/to/dir --dry-run
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import pathlib
import sys
import time
import uuid
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://albert.api.etalab.gouv.fr"
DEFAULT_MAX_MB = 20.0
SUPPORTED_EXTENSIONS = frozenset(
    {".pdf", ".txt", ".html", ".htm", ".md", ".markdown"}
)


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
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


def _encode_multipart(
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> tuple[bytes, str]:
    """Build a multipart/form-data body. Returns (body, content_type)."""
    boundary = f"----AlbertUpload{uuid.uuid4().hex}"
    lines: list[bytes] = []

    for name, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        lines.append(b"")
        lines.append(value.encode("utf-8"))

    for name, (filename, content, content_type) in files.items():
        lines.append(f"--{boundary}".encode())
        disposition = (
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"'
        )
        lines.append(disposition.encode("utf-8"))
        lines.append(f"Content-Type: {content_type}".encode())
        lines.append(b"")
        lines.append(content)

    lines.append(f"--{boundary}--".encode())
    lines.append(b"")
    body = b"\r\n".join(lines)
    return body, f"multipart/form-data; boundary={boundary}"


def create_collection(base_url: str, api_key: str, name: str) -> int:
    url = f"{base_url.rstrip('/')}/v1/collections"
    payload = json.dumps({"name": name}).encode("utf-8")
    headers = {
        **_auth_headers(api_key),
        "Content-Type": "application/json",
    }
    status, body = _request_json(url, headers=headers, method="POST", data=payload)
    if status not in (200, 201) or not isinstance(body, dict) or "id" not in body:
        raise SystemExit(f"Failed to create collection (HTTP {status}): {body}")
    collection_id = body["id"]
    print(f"Created collection {name!r} with id={collection_id}")
    return int(collection_id)


def upload_document(
    base_url: str,
    api_key: str,
    collection_id: int,
    path: pathlib.Path,
) -> tuple[bool, str]:
    data = path.read_bytes()
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body, content_type_header = _encode_multipart(
        fields={"collection_id": str(collection_id)},
        files={"file": (path.name, data, content_type)},
    )
    url = f"{base_url.rstrip('/')}/v1/documents"
    headers = {
        **_auth_headers(api_key),
        "Content-Type": content_type_header,
    }
    status, resp = _request_json(
        url, headers=headers, method="POST", data=body, timeout=300
    )
    if status in (200, 201) and isinstance(resp, dict):
        doc_id = resp.get("id", "?")
        return True, f"ok document_id={doc_id}"
    return False, f"HTTP {status}: {resp}"


def iter_candidate_files(
    directory: pathlib.Path, *, recursive: bool
) -> list[pathlib.Path]:
    if recursive:
        paths = sorted(p for p in directory.rglob("*") if p.is_file())
    else:
        paths = sorted(p for p in directory.iterdir() if p.is_file())
    return paths


def resolve_collection_id(
    *,
    collection_id: int | None,
    create_collection: str | None,
) -> int | None:
    """Return an existing collection id from CLI or ALBERT_COLLECTION_ID.

    Returns None when --create-collection was requested (caller creates later).
    Exits via SystemExit on invalid/missing configuration.
    """
    if create_collection:
        return None
    if collection_id is not None:
        return collection_id
    env_id = os.environ.get("ALBERT_COLLECTION_ID", "").strip()
    if not env_id:
        raise SystemExit(
            "Provide --collection-id, --create-collection, "
            "or set ALBERT_COLLECTION_ID"
        )
    try:
        return int(env_id)
    except ValueError as exc:
        raise SystemExit(
            f"ALBERT_COLLECTION_ID must be an integer, got {env_id!r}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upload documents from a directory to the Albert API."
    )
    parser.add_argument(
        "directory",
        type=pathlib.Path,
        help="Directory containing documents to upload",
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--collection-id",
        type=int,
        default=None,
        help="Existing Albert collection ID (default: ALBERT_COLLECTION_ID)",
    )
    group.add_argument(
        "--create-collection",
        metavar="NAME",
        help="Create a new private collection with this name, then upload into it",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("ALBERT_API_BASE_URL", DEFAULT_BASE_URL),
        help=f"Albert API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (default: top-level only)",
    )
    parser.add_argument(
        "--max-mb",
        type=float,
        default=DEFAULT_MAX_MB,
        help=f"Skip files larger than this many megabytes (default: {DEFAULT_MAX_MB})",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="Pause between uploads (default: 0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be uploaded without calling the API",
    )
    args = parser.parse_args(argv)

    directory = args.directory.expanduser().resolve()
    if not directory.is_dir():
        print(f"Not a directory: {directory}", file=sys.stderr)
        return 2

    api_key = os.environ.get("ALBERT_API_KEY", "").strip()
    if not args.dry_run and not api_key:
        print("ALBERT_API_KEY is not set", file=sys.stderr)
        return 2

    # Validate collection targeting early (create happens after dry-run).
    collection_id = resolve_collection_id(
        collection_id=args.collection_id,
        create_collection=args.create_collection,
    )

    max_bytes = int(args.max_mb * 1024 * 1024)
    candidates = iter_candidate_files(directory, recursive=args.recursive)

    to_upload: list[pathlib.Path] = []
    skipped: list[tuple[pathlib.Path, str]] = []
    for path in candidates:
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            skipped.append((path, f"unsupported extension {suffix or '(none)'}"))
            continue
        size = path.stat().st_size
        if size > max_bytes:
            skipped.append((path, f"too large ({size} bytes > {max_bytes})"))
            continue
        to_upload.append(path)

    for path, reason in skipped:
        print(f"skip  {path.relative_to(directory)}  ({reason})")

    if args.dry_run:
        for path in to_upload:
            print(f"would upload  {path.relative_to(directory)}")
        target = (
            f"create {args.create_collection!r}"
            if args.create_collection
            else f"collection_id={collection_id}"
        )
        print(
            f"\nDry run: {len(to_upload)} to upload, {len(skipped)} skipped "
            f"({target}, no API calls)."
        )
        return 0

    if args.create_collection:
        collection_id = create_collection(
            args.base_url, api_key, args.create_collection
        )

    assert collection_id is not None

    ok = 0
    failed = 0
    for i, path in enumerate(to_upload):
        rel = path.relative_to(directory)
        success, detail = upload_document(
            args.base_url, api_key, collection_id, path
        )
        if success:
            ok += 1
            print(f"ok    {rel}  ({detail})")
        else:
            failed += 1
            print(f"FAIL  {rel}  ({detail})", file=sys.stderr)
        if args.sleep > 0 and i < len(to_upload) - 1:
            time.sleep(args.sleep)

    print(
        f"\nDone: {ok} uploaded, {failed} failed, {len(skipped)} skipped "
        f"(collection_id={collection_id})."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
