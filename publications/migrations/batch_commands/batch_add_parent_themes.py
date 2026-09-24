"""
Tag each publication page with the ancestors of its themes.

Live pages without a pending draft are republished. Pages with a pending draft
and unpublished pages get a new revision, which an editor has to publish.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TextIO

from django.db import transaction

from publications.models import Theme

logger = logging.getLogger(__name__)

PUBLISHED = "published"
DRAFT_SAVED_PENDING = "draft_saved_pending"
DRAFT_SAVED_NOT_LIVE = "draft_saved_not_live"
UNCHANGED = "unchanged"
SKIPPED_ALIAS = "alias"
FAILED = "failed"

DRAFT_SAVED = (DRAFT_SAVED_PENDING, DRAFT_SAVED_NOT_LIVE)
LEFT_UNTOUCHED = (SKIPPED_ALIAS, FAILED)


@dataclass
class PageResult:
    page_id: int
    title: str
    action: str
    themes: str = ""
    added: str = ""
    error: str = ""

    def describe(self) -> str:
        line = f"pk={self.page_id} title={self.title!r}"
        if self.themes:
            line = f"{line} themes={self.themes}"
        if self.added:
            line = f"{line} -> {self.added}"
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
            f"skipped_alias={self.count(SKIPPED_ALIAS)} "
            f"failed={self.count(FAILED)}"
        )


def missing_ancestors(themes: list[Theme]) -> list[Theme]:
    """Ancestors of ``themes`` that are not already in the list, closest parent first.

    A parent whose locale differs from the theme is skipped, and so is the rest of
    that chain. A cycle stops the walk.
    """
    existing = {theme.pk for theme in themes}
    to_add: list[Theme] = []
    for theme in themes:
        seen = {theme.pk}
        parent = theme.parent
        while parent is not None:
            if parent.pk in seen or parent.locale_id != theme.locale_id:
                break
            seen.add(parent.pk)
            if parent.pk not in existing:
                to_add.append(parent)
                existing.add(parent.pk)
            parent = parent.parent
    return to_add


def _names(themes: list[Theme]) -> str:
    return ", ".join(theme.name for theme in themes)


def _make_result(page, action: str, **kwargs) -> PageResult:
    return PageResult(page_id=page.pk, title=page.title, action=action, **kwargs)


def _draft_source(page):
    """The page as the editor sees it: its latest revision, or the row if it has none."""
    latest = page.get_latest_revision()
    if latest is None:
        return page
    return latest.as_object()


def _draft_action(source) -> str:
    return DRAFT_SAVED_PENDING if source.live else DRAFT_SAVED_NOT_LIVE


def add_parent_themes_to_page(page, *, dry_run: bool) -> PageResult:
    if page.alias_of_id:
        return _make_result(page, SKIPPED_ALIAS)

    publishing = page.live and not page.has_unpublished_changes

    try:
        source = page if publishing else _draft_source(page)
        current = list(source.themes.all())
        to_add = missing_ancestors(current)
    except Exception as exc:
        logger.exception("Could not list themes of page %s", page.pk)
        return _make_result(page, FAILED, error=f"{type(exc).__name__}: {exc}")

    theme_names = _names(current)
    if not to_add:
        return _make_result(source, UNCHANGED, themes=theme_names)

    added_names = _names(to_add)
    if not dry_run:
        try:
            with transaction.atomic():
                for theme in to_add:
                    source.themes.add(theme)
                revision = source.save_revision(log_action=True, clean=False)
                if publishing:
                    revision.publish()
        except Exception as exc:
            logger.exception("Could not add parent themes to page %s", page.pk)
            return _make_result(
                page,
                FAILED,
                themes=theme_names,
                added=added_names,
                error=f"{type(exc).__name__}: {exc}",
            )

    action = PUBLISHED if publishing else _draft_action(source)
    return _make_result(source, action, themes=theme_names, added=added_names)


def add_parent_themes(
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

    write("=== add_parent_themes ===")
    write(f"dry_run: {dry_run}")

    prefix = "[dry-run] " if dry_run else ""
    last_pk = 0
    while True:
        chunk = list(pages.filter(pk__gt=last_pk).order_by("pk")[:100])
        if not chunk:
            break
        for page in chunk:
            last_pk = page.pk
            if limit is not None and summary.scanned >= limit:
                break
            summary.scanned += 1
            result = add_parent_themes_to_page(page, dry_run=dry_run)
            summary.results.append(result)
            if result.action == PUBLISHED or result.action in DRAFT_SAVED:
                label = "PUBLISHED" if result.action == PUBLISHED else "DRAFT SAVED"
                write(f"{prefix}{label}: {result.describe()}")
        else:
            continue
        break

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
