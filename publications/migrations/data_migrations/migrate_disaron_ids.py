"""Copy ``disaron_id`` out of top-level HTML blocks on publication pages.

A block counts only when its content is a single ``<div id="disaron-nom">…</div>``.
Whitespace around that div is ignored. Any other content is an error: the page is
logged and left unchanged. A page with no such block is logged as missing an id.
Either outcome leaves the other pages free to be written.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from bs4 import BeautifulSoup, NavigableString, Tag
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

MIGRATION_LOG_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
DISARON_ELEMENT_ID = "disaron-nom"

FOUND = "found"
MISSING = "missing"
CONFLICT = "conflict"
SKIPPED = "skipped"


def migration_log_path(*, override: Path | str | None = None, started_at=None) -> Path:
    if override is not None:
        return Path(override)
    started_at = started_at or timezone.now()
    stamp = started_at.strftime("%Y-%m-%dT%H-%M-%S")
    MIGRATION_LOG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return MIGRATION_LOG_OUTPUT_DIR / f"migrate_disaron_ids_{stamp}.log"


@dataclass
class StreamExtract:
    disaron_id: str | None = None
    error: str | None = None
    removed_blocks: int = 0
    body: list = field(default_factory=list)


@dataclass
class PageAssessment:
    pk: int
    title: str
    action: str
    disaron_id: str = ""
    removed_blocks: int = 0
    reason: str = ""
    needs_write: bool = False
    owns_id: bool = False
    also_on: list[tuple[int, str]] = field(default_factory=list)

    def describe(self) -> str:
        line = f"{self.action.upper()} pk={self.pk} disaron_id={self.disaron_id!r} title={self.title!r}"
        if self.action == FOUND:
            return f"{line} removed_blocks={self.removed_blocks}"
        if self.action == CONFLICT and self.also_on:
            also = ", ".join(f"pk={pk} title={title!r}" for pk, title in self.also_on)
            line = f"{line} also_on {also}"
        if self.reason and self.action != FOUND:
            line = f"{line} reason={self.reason}"
        return line


def transform_top_level_body(raw_data: list) -> StreamExtract:
    """Return the body with a valid top-level Disaron block removed.

    Nested HTML is ignored. A top-level HTML block that mentions the Disaron div
    but is not exactly that div is an error, and the body is returned unchanged.
    """
    found: list[str] = []
    errors: list[str] = []
    removed = 0
    new_body: list = []

    for block in raw_data:
        if not isinstance(block, dict) or block.get("type") != "html":
            new_body.append(block)
            continue
        kind, value, reason = _classify_html_block(block.get("value") or "")
        if kind == "ignore":
            new_body.append(block)
            continue
        if kind == "error":
            errors.append(reason or "invalid disaron block")
            if value:
                found.append(value)
            continue
        found.append(value or "")
        removed += 1

    original = list(raw_data)
    if errors:
        seen = _single_value(found) or ""
        detail = "; ".join(errors)
        if seen and "several values" not in detail:
            detail = f"{detail} (disaron_id={seen!r})"
        if len(set(found)) > 1:
            detail = f"{detail}; several values: {', '.join(found)}"
        return StreamExtract(disaron_id=seen or None, error=detail, body=original)
    if not found:
        return StreamExtract(body=original)
    if len(set(found)) > 1:
        return StreamExtract(error=f"several values: {', '.join(found)}", body=original)
    return StreamExtract(disaron_id=found[0], removed_blocks=removed, body=new_body)


def _single_value(values: list[str]) -> str | None:
    unique = list(dict.fromkeys(values))
    if len(unique) == 1:
        return unique[0]
    return None


def _classify_html_block(html: str) -> tuple[str, str | None, str | None]:
    """Return ``(ignore|found|error, value, reason)``."""
    soup = BeautifulSoup(html or "", "html.parser")
    nodes = soup.find_all(id=DISARON_ELEMENT_ID)
    if not nodes:
        return "ignore", None, None

    value = nodes[0].get_text(strip=True) if len(nodes) == 1 else ""
    reason = _invalid_disaron_block_reason(soup, nodes)
    if reason:
        return "error", value or None, reason
    return "found", value, None


def _invalid_disaron_block_reason(soup: BeautifulSoup, nodes: list) -> str | None:
    if len(nodes) != 1:
        return "several disaron divs"
    node = nodes[0]
    if node.name != "div":
        return "disaron id is not on a div"
    if set(node.attrs) != {"id"}:
        return "disaron div has extra attributes"
    if any(isinstance(child, Tag) for child in node.children):
        return "disaron div contains nested markup"
    if not node.get_text(strip=True):
        return "disaron div is empty"
    for child in soup.contents:
        if child is node:
            continue
        if isinstance(child, NavigableString) and not str(child).strip():
            continue
        return "html block contains other markup"
    return None


def _iter_pages(pages, chunk_size: int = 100):
    if not hasattr(pages, "filter"):
        yield from pages
        return

    last_pk = 0
    while True:
        chunk = list(pages.filter(pk__gt=last_pk).order_by("pk")[:chunk_size])
        if not chunk:
            return
        yield from chunk
        last_pk = chunk[-1].pk


def _body_raw(page) -> list:
    body = page.body
    if hasattr(body, "raw_data"):
        return list(body.raw_data)
    return list(body)


def _draft_page(page):
    latest = page.get_latest_revision()
    if latest is None:
        return None
    return latest.as_object()


def assess_page(page) -> tuple[PageAssessment, dict]:
    """Classify one page. The payload is what a later write applies."""
    if page.alias_of_id:
        return (
            PageAssessment(pk=page.pk, title=page.title, action=SKIPPED, reason="alias"),
            {},
        )

    row_extract = transform_top_level_body(_body_raw(page))
    draft = None
    draft_extract = None
    if not page.live or page.has_unpublished_changes:
        draft = _draft_page(page)
        if draft is not None:
            draft_extract = transform_top_level_body(_body_raw(draft))

    if page.live and draft_extract is not None:
        assessment = _assess_live_and_draft(page, row_extract, draft_extract)
    elif not page.live and draft_extract is not None:
        assessment = _assess_source(page, draft_extract, source_name="draft")
    else:
        assessment = _assess_source(page, row_extract, source_name="live" if page.live else "page")

    payload = {
        "row_extract": row_extract,
        "draft_extract": draft_extract,
        "target_id": assessment.disaron_id,
    }
    return assessment, payload


def _assess_source(page, extract: StreamExtract, *, source_name: str) -> PageAssessment:
    if extract.error:
        return PageAssessment(
            pk=page.pk,
            title=page.title,
            action=CONFLICT,
            disaron_id=extract.disaron_id or "",
            reason=f"{source_name}: {extract.error}",
        )
    return _assessment_for_id(
        page,
        extracted_id=extract.disaron_id,
        removed_blocks=extract.removed_blocks,
    )


def _assess_live_and_draft(page, live: StreamExtract, draft: StreamExtract) -> PageAssessment:
    if live.error or draft.error:
        reasons = []
        if live.error:
            reasons.append(f"live: {live.error}")
        if draft.error:
            reasons.append(f"draft: {draft.error}")
        seen = live.disaron_id if live.disaron_id == draft.disaron_id else ""
        return PageAssessment(
            pk=page.pk,
            title=page.title,
            action=CONFLICT,
            disaron_id=seen or "",
            reason="; ".join(reasons),
        )
    if live.disaron_id != draft.disaron_id:
        return PageAssessment(
            pk=page.pk,
            title=page.title,
            action=CONFLICT,
            reason=f"live disaron_id={live.disaron_id!r} draft disaron_id={draft.disaron_id!r}",
        )
    return _assessment_for_id(
        page,
        extracted_id=live.disaron_id,
        removed_blocks=live.removed_blocks + draft.removed_blocks,
    )


def _assessment_for_id(page, *, extracted_id: str | None, removed_blocks: int) -> PageAssessment:
    stored = page.disaron_id or None
    if stored and extracted_id and stored != extracted_id:
        return PageAssessment(
            pk=page.pk,
            title=page.title,
            action=CONFLICT,
            disaron_id=extracted_id,
            reason=f"stored disaron_id={stored!r} html disaron_id={extracted_id!r}",
        )
    final_id = extracted_id or stored
    if not final_id:
        return PageAssessment(pk=page.pk, title=page.title, action=MISSING)
    return PageAssessment(
        pk=page.pk,
        title=page.title,
        action=FOUND,
        disaron_id=final_id,
        removed_blocks=removed_blocks,
        needs_write=bool(extracted_id and stored != extracted_id) or removed_blocks > 0,
        owns_id=stored == final_id,
    )


def _mark_duplicates(assessments: list[PageAssessment]) -> None:
    grouped: dict[str, list[PageAssessment]] = {}
    for assessment in assessments:
        if assessment.action != FOUND or not assessment.disaron_id:
            continue
        grouped.setdefault(assessment.disaron_id, []).append(assessment)

    for disaron_id, group in grouped.items():
        if len(group) < 2:
            continue
        claimants = [assessment for assessment in group if not assessment.owns_id]
        if not claimants:
            continue
        for assessment in claimants:
            others = [other for other in group if other.pk != assessment.pk]
            assessment.action = CONFLICT
            assessment.needs_write = False
            assessment.disaron_id = disaron_id
            assessment.also_on = [(other.pk, other.title) for other in others]


def _apply(page, assessment: PageAssessment) -> bool:
    fresh, payload = assess_page(page)
    if fresh.action != FOUND or not fresh.needs_write or fresh.disaron_id != assessment.disaron_id:
        return False

    target_id = assessment.disaron_id
    row_extract: StreamExtract = payload["row_extract"]
    draft_extract: StreamExtract | None = payload["draft_extract"]

    if page.live and draft_extract is None:
        _assign(page, target_id, row_extract.body)
        page.save_revision(log_action=True, clean=False).publish()
        return True

    if page.live and draft_extract is not None:
        draft = _draft_page(page)
        _assign(page, target_id, row_extract.body)
        page.save_revision(log_action=True, clean=False).publish()
        _assign(draft, target_id, draft_extract.body)
        draft.save_revision(log_action=True, clean=False)
        return True

    draft = _draft_page(page)
    if draft is None:
        _assign(page, target_id, row_extract.body)
        page.save_revision(log_action=True, clean=False)
        page.save(update_fields=["disaron_id", "body"], clean=False)
        return True

    _assign(draft, target_id, draft_extract.body)
    draft.save_revision(log_action=True, clean=False)
    page.disaron_id = target_id
    update_fields = ["disaron_id"]
    if row_extract.disaron_id == target_id and row_extract.removed_blocks:
        page.body = row_extract.body
        update_fields.append("body")
    page.save(update_fields=update_fields, clean=False)
    return True


def _assign(page, disaron_id: str, body: list) -> None:
    page.disaron_id = disaron_id
    page.body = body


def _save_line(label: str, assessment: PageAssessment) -> str:
    return f"{label} pk={assessment.pk} disaron_id={assessment.disaron_id!r} title={assessment.title!r}"


@dataclass
class MigrationSummary:
    dry_run: bool
    pages_scanned: int = 0
    found: int = 0
    missing: int = 0
    conflicts: int = 0
    skipped: int = 0
    written: int = 0
    failed: int = 0
    assessments: list[PageAssessment] = field(default_factory=list)


def run_migration(pages, *, dry_run: bool, log_file: TextIO | None = None) -> MigrationSummary:
    summary = MigrationSummary(dry_run=dry_run)

    def log(line: str) -> None:
        if log_file is not None:
            log_file.write(line + "\n")
            log_file.flush()

    log("=== migrate_disaron_ids ===")
    log(f"dry_run: {dry_run}")
    log("")

    assessments: list[PageAssessment] = []
    for page in _iter_pages(pages):
        summary.pages_scanned += 1
        try:
            assessment, _payload = assess_page(page)
        except Exception as exc:
            logger.exception("Could not read disaron_id of page %s", page.pk)
            assessment = PageAssessment(
                pk=page.pk,
                title=page.title,
                action=CONFLICT,
                reason=f"{type(exc).__name__}: {exc}",
            )
        assessments.append(assessment)

    _mark_duplicates(assessments)
    summary.assessments = assessments

    for assessment in assessments:
        log(assessment.describe())
        if assessment.action == FOUND:
            summary.found += 1
        elif assessment.action == MISSING:
            summary.missing += 1
        elif assessment.action == CONFLICT:
            summary.conflicts += 1
        elif assessment.action == SKIPPED:
            summary.skipped += 1

    log("")
    log("Missing an id:")
    missing = [assessment for assessment in assessments if assessment.action == MISSING]
    if not missing:
        log("(none)")
    for assessment in missing:
        log(assessment.describe())

    log("")
    log("Conflicts:")
    conflicts = [assessment for assessment in assessments if assessment.action == CONFLICT]
    if not conflicts:
        log("(none)")
    for assessment in conflicts:
        log(assessment.describe())

    if not dry_run:
        log("")
        log("Saving pages:")
        for assessment in assessments:
            if assessment.action != FOUND or not assessment.needs_write:
                continue
            log(_save_line("SAVING", assessment))
            try:
                with transaction.atomic():
                    page = pages.model.objects.get(pk=assessment.pk)
                    wrote = _apply(page, assessment)
            except Exception as exc:
                logger.exception("Could not save disaron_id of page %s", assessment.pk)
                summary.failed += 1
                log(
                    f"FAILED pk={assessment.pk} disaron_id={assessment.disaron_id!r} "
                    f"title={assessment.title!r} reason={type(exc).__name__}: {exc}"
                )
                continue
            if wrote:
                summary.written += 1
                log(_save_line("SAVED", assessment))
            else:
                log(_save_line("NOT SAVED", assessment) + " reason=unchanged since scan")

    log("")
    log(f"pages_scanned: {summary.pages_scanned}")
    log(f"found: {summary.found}")
    log(f"missing: {summary.missing}")
    log(f"conflicts: {summary.conflicts}")
    log(f"skipped: {summary.skipped}")
    log(f"written: {summary.written}")
    log(f"failed: {summary.failed}")
    return summary
