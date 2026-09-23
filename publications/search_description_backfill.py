"""
Recompute ``search_description`` from the hero and body of every page.

Live pages without a pending draft are republished. Pages with a pending draft
and unpublished pages get a new revision built from their draft content, which
nobody publishes: an editor has to, for the change to reach the site.
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
DRAFT_SAVED_PENDING = "draft_saved_pending"
DRAFT_SAVED_NOT_LIVE = "draft_saved_not_live"
UNCHANGED = "unchanged"
SKIPPED_EMPTY = "empty"
SKIPPED_ALIAS = "alias"
FAILED = "failed"

DRAFT_SAVED = (DRAFT_SAVED_PENDING, DRAFT_SAVED_NOT_LIVE)
LEFT_UNTOUCHED = (SKIPPED_EMPTY, SKIPPED_ALIAS, FAILED)


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
        if self.action in LEFT_UNTOUCHED or self.action in DRAFT_SAVED:
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
    def draft_saved(self) -> list[PageResult]:
        return [result for result in self.results if result.action in DRAFT_SAVED]

    @property
    def left_untouched(self) -> list[PageResult]:
        return [result for result in self.results if result.action in LEFT_UNTOUCHED]

    def counters(self) -> str:
        return (
            f"scanned={self.scanned} "
            f"published={self.count(PUBLISHED)} "
            f"draft_saved_pending={self.count(DRAFT_SAVED_PENDING)} "
            f"draft_saved_not_live={self.count(DRAFT_SAVED_NOT_LIVE)} "
            f"unchanged={self.count(UNCHANGED)} "
            f"skipped_empty={self.count(SKIPPED_EMPTY)} "
            f"skipped_alias={self.count(SKIPPED_ALIAS)} "
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


def _save_draft_description(source, description: str) -> None:
    source.search_description = description
    # log_action: the History tab lists log entries, so a revision saved
    # without one would not show up there at all.
    source.save_revision(log_action=True, clean=False)
    if not source.live:
        # Not public, so the row can carry the new value too. update_fields
        # keeps the rest of the draft out of the row, and makes Wagtail skip
        # the slug comparison that would otherwise rewrite descendant urls.
        source.save(update_fields=["search_description"], clean=False)


def _draft_source(page):
    """The page as the editor sees it: its latest revision, or the row if it has none.

    The row holds the published content, so a revision built from it would
    become the latest one and hide the pending draft from the editor.
    """
    latest = page.get_latest_revision()
    if latest is None:
        return page
    return latest.as_object()


def _draft_action(source) -> str:
    return DRAFT_SAVED_PENDING if source.live else DRAFT_SAVED_NOT_LIVE


def regenerate_page(page, *, dry_run: bool) -> PageResult:
    if page.alias_of_id:
        # An alias mirrors its source page and rejects save_revision().
        return _make_result(page, SKIPPED_ALIAS)

    publishing = page.live and not page.has_unpublished_changes

    try:
        source = page if publishing else _draft_source(page)
        description = build_page_search_description(source)
    except Exception as exc:
        logger.exception("Could not build the search description of page %s", page.pk)
        return _make_result(
            page,
            FAILED,
            old_description=page.search_description,
            error=f"{type(exc).__name__}: {exc}",
        )

    old_description = source.search_description
    if not description:
        # Never write an empty description: SitesFacilesBasePage.save() would
        # then refill the field with the legacy 20-word extract.
        return _make_result(source, SKIPPED_EMPTY, old_description=old_description)
    if description == old_description:
        return _make_result(source, UNCHANGED, old_description=old_description, new_description=description)

    if not dry_run:
        try:
            with transaction.atomic():
                if publishing:
                    _publish_description(source, description)
                else:
                    _save_draft_description(source, description)
        except Exception as exc:
            logger.exception("Could not save the search description of page %s", page.pk)
            return _make_result(
                page,
                FAILED,
                old_description=old_description,
                new_description=description,
                error=f"{type(exc).__name__}: {exc}",
            )

    action = PUBLISHED if publishing else _draft_action(source)
    return _make_result(source, action, old_description=old_description, new_description=description)


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

        if result.action == PUBLISHED or result.action in DRAFT_SAVED:
            label = "PUBLISHED" if result.action == PUBLISHED else "DRAFT SAVED"
            write(
                f"{prefix}{label}: {result.describe()} "
                f"{_shorten(result.old_description)} -> {_shorten(result.new_description)}"
            )
        if summary.scanned % PROGRESS_EVERY == 0:
            write(f"... {summary.scanned} pages scanned")

    if summary.draft_saved:
        write("")
        write("Revision saved, an editor has to publish the page to apply it:")
        for result in summary.draft_saved:
            write(result.describe())

    if summary.left_untouched:
        write("")
        write("Pages left untouched, to fix by hand:")
        for result in summary.left_untouched:
            write(result.describe())

    write("")
    write(summary.counters())

    return summary


def _shorten(text: str, max_chars: int = 60) -> str:
    if len(text) <= max_chars:
        return repr(text)
    return repr(f"{text[:max_chars]}…")
