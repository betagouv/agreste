"""
Recompute ``search_description`` from the hero and body of every page.

Only live pages without a pending draft are republished. Anything else is left
untouched and reported, so it can be fixed by hand.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TextIO

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from wagtail.models import Page

from publications.search_description import build_page_search_description
from sites_conformes.core.abstract import SitesFacilesBasePage

logger = logging.getLogger(__name__)

PROGRESS_EVERY = 25

PUBLISHED = "published"
UNCHANGED = "unchanged"
SKIPPED_NOT_LIVE = "not_live"
SKIPPED_PENDING_DRAFT = "pending_draft"
SKIPPED_EMPTY = "empty"
FAILED = "failed"

NEEDS_ATTENTION = (SKIPPED_NOT_LIVE, SKIPPED_PENDING_DRAFT, SKIPPED_EMPTY, FAILED)


@dataclass
class PageResult:
    page_id: int
    page_type: str
    title: str
    url: str
    action: str
    old_description: str = ""
    new_description: str = ""
    error: str = ""

    def describe(self) -> str:
        line = f"pk={self.page_id} title={self.title!r} type={self.page_type} url={self.url}"
        if self.action in NEEDS_ATTENTION:
            line = f"{line} reason={self.action}"
        if self.error:
            line = f"{line} error={self.error}"
        return line


@dataclass
class BackfillSummary:
    dry_run: bool
    scanned: int = 0
    results: list[PageResult] = field(default_factory=list)

    def count(self, action: str) -> int:
        return sum(1 for result in self.results if result.action == action)

    @property
    def needs_attention(self) -> list[PageResult]:
        return [result for result in self.results if result.action in NEEDS_ATTENTION]

    def counters(self) -> str:
        return (
            f"scanned={self.scanned} "
            f"published={self.count(PUBLISHED)} "
            f"unchanged={self.count(UNCHANGED)} "
            f"skipped_not_live={self.count(SKIPPED_NOT_LIVE)} "
            f"skipped_pending_draft={self.count(SKIPPED_PENDING_DRAFT)} "
            f"skipped_empty={self.count(SKIPPED_EMPTY)} "
            f"failed={self.count(FAILED)}"
        )


def pages_to_process(page_types: list[str] | None = None):
    """All pages built on SitesFacilesBasePage, as specific instances.

    Pages are fetched once through the base Page queryset rather than per model,
    so multi-table inheritance (a PublicationPage is also a BlogEntryPage) does
    not yield the same page twice.
    """
    queryset = Page.objects.all().order_by("pk")
    if page_types:
        queryset = queryset.filter(content_type__in=_content_types(page_types))
    return queryset.specific()


def _content_types(page_types: list[str]):
    content_types = []
    for page_type in page_types:
        app_label, _, model = page_type.partition(".")
        if not model:
            raise ValueError(f"Expected a page type as app_label.ModelName, got {page_type!r}")
        try:
            content_types.append(ContentType.objects.get(app_label=app_label, model=model.lower()))
        except ContentType.DoesNotExist:
            raise ValueError(f"Unknown page type {page_type!r}") from None
    return content_types


def _iter_pages(pages, chunk_size: int = 100):
    """Walk the queryset by primary key ranges.

    ``QuerySet.iterator()`` opens a server-side cursor, which Postgres drops as
    soon as the surrounding transaction ends: the per-page ``atomic()`` blocks
    below would invalidate it mid-iteration.
    """
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


def _make_result(page, action: str, **kwargs) -> PageResult:
    return PageResult(
        page_id=page.pk,
        page_type=f"{page._meta.app_label}.{page._meta.object_name}",
        title=page.title,
        url=page.get_url() or "",
        action=action,
        **kwargs,
    )


def _publish_description(page, description: str) -> None:
    page.search_description = description
    # clean=False: full_clean() on legacy pages can fail over unrelated fields.
    page.save_revision(log_action=False, clean=False).publish()


def regenerate_page(page, *, dry_run: bool) -> PageResult:
    if not page.live:
        return _make_result(page, SKIPPED_NOT_LIVE)
    if page.has_unpublished_changes:
        # Publishing a revision built from the live content would become the
        # latest revision and bury the editor's pending draft.
        return _make_result(page, SKIPPED_PENDING_DRAFT)

    old_description = page.search_description
    try:
        description = build_page_search_description(page)
    except Exception as exc:
        logger.exception("Could not build the search description of page %s", page.pk)
        return _make_result(page, FAILED, old_description=old_description, error=f"{type(exc).__name__}: {exc}")

    if not description:
        # Never write an empty description: SitesFacilesBasePage.save() would
        # then refill the field with the legacy 20-word extract.
        return _make_result(page, SKIPPED_EMPTY, old_description=old_description)
    if description == old_description:
        return _make_result(page, UNCHANGED, old_description=old_description, new_description=description)

    if not dry_run:
        try:
            with transaction.atomic():
                _publish_description(page, description)
        except Exception as exc:
            logger.exception("Could not publish the search description of page %s", page.pk)
            return _make_result(
                page,
                FAILED,
                old_description=old_description,
                new_description=description,
                error=f"{type(exc).__name__}: {exc}",
            )

    return _make_result(page, PUBLISHED, old_description=old_description, new_description=description)


def regenerate_search_descriptions(
    pages,
    *,
    dry_run: bool,
    limit: int | None = None,
    log=None,
    log_file: TextIO | None = None,
) -> BackfillSummary:
    summary = BackfillSummary(dry_run=dry_run)

    def write(line: str) -> None:
        if log is not None:
            log(line)
        if log_file is not None:
            log_file.write(line + "\n")
            log_file.flush()

    write("=== regenerate_search_descriptions ===")
    write(f"dry_run: {dry_run}")

    prefix = "[dry-run] " if dry_run else ""

    for page in _iter_pages(pages):
        if not isinstance(page, SitesFacilesBasePage):
            continue
        if limit is not None and summary.scanned >= limit:
            break

        summary.scanned += 1
        result = regenerate_page(page, dry_run=dry_run)
        summary.results.append(result)

        if result.action == PUBLISHED:
            write(
                f"{prefix}PUBLISHED: {result.describe()} "
                f"{_shorten(result.old_description)} -> {_shorten(result.new_description)}"
            )
        if summary.scanned % PROGRESS_EVERY == 0:
            write(f"... {summary.scanned} pages scanned")

    if summary.needs_attention:
        write("")
        write("Pages left untouched, to fix by hand:")
        for result in summary.needs_attention:
            write(result.describe())

    write("")
    write(summary.counters())

    return summary


def _shorten(text: str, max_chars: int = 60) -> str:
    if len(text) <= max_chars:
        return repr(text)
    return repr(f"{text[:max_chars]}…")
