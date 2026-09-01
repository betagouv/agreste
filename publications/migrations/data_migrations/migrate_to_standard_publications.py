from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from bs4 import BeautifulSoup
from django.db import transaction
from django.utils import timezone

MIGRATION_LOG_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"

COMPLEMENT_TITRE_ID = "complement-titre"
CHAPEAU_ID = "chapeau"
LEFT_COLUMN_WIDTH = "8"
RIGHT_COLUMN_WIDTH = "4"
MAX_HTML_BLOCKS = 2

TILE_TITLE_PUBLICATION = "Télécharger la publication"
TILE_TITLE_DATA = "Télécharger les données"

TILE_TITLE_TO_DOWNLOAD_TYPE = {
    TILE_TITLE_PUBLICATION: "publication",
    TILE_TITLE_DATA: "data",
}

STANDARD_PUBLICATION_BLOCK = "standard_publication"
MULTICOLUMNS_BLOCK = "multicolumns"


def migration_log_path(*, override: Path | str | None = None, started_at=None) -> Path:
    if override is not None:
        return Path(override)
    started_at = started_at or timezone.now()
    stamp = started_at.strftime("%Y-%m-%dT%H-%M-%S")
    MIGRATION_LOG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return MIGRATION_LOG_OUTPUT_DIR / f"migrate_to_standard_{stamp}.log"


@dataclass
class BlockMigrationResult:
    action: str
    reason: str | None = None


@dataclass
class PageMigrationResult:
    page_id: int
    page_url: str
    block_results: list[BlockMigrationResult] = field(default_factory=list)

    @property
    def migrated_count(self) -> int:
        return sum(1 for result in self.block_results if result.action == "migrated")

    @property
    def skipped_count(self) -> int:
        return sum(1 for result in self.block_results if result.action == "skipped")


@dataclass
class MigrationSummary:
    dry_run: bool
    pages_scanned: int = 0
    pages_changed: int = 0
    blocks_migrated: int = 0
    blocks_skipped: int = 0
    page_results: list[PageMigrationResult] = field(default_factory=list)


def _column_content_by_width(columns: list, width: str) -> list | None:
    content = None
    for column in columns:
        if column.get("type") != "column":
            return None
        if column.get("value", {}).get("width") != width:
            continue
        if content is not None:
            return None
        content = column.get("value", {}).get("content", [])
    return content


def _parse_html_fields(html_blocks: list[dict]) -> tuple[str, str, str | None]:
    subtitle = ""
    summary = ""

    for html_block in html_blocks:
        soup = BeautifulSoup(html_block.get("value", ""), "html.parser")
        complement_titre = soup.find(id=COMPLEMENT_TITRE_ID)
        chapeau = soup.find(id=CHAPEAU_ID)

        if not complement_titre and not chapeau:
            return "", "", "html block without complement-titre or chapeau"

        if complement_titre:
            if subtitle:
                return "", "", "duplicate complement-titre"
            subtitle = complement_titre.get_text(strip=True)

        if chapeau:
            if summary:
                return "", "", "duplicate chapeau"
            summary = chapeau.decode_contents().strip()

    return subtitle, summary, None


def _parse_downloadable_documents(tile_blocks: list[dict]) -> tuple[list[dict], str | None]:
    downloadable_documents = []

    for tile_block in tile_blocks:
        tile_value = tile_block.get("value", {})
        tile_title = tile_value.get("title", "")
        download_type = TILE_TITLE_TO_DOWNLOAD_TYPE.get(tile_title)
        if download_type is None:
            return [], f"unknown tile title: {tile_title!r}"

        document_id = tile_value.get("link", {}).get("document")
        if not document_id:
            return [], "tile missing document"

        downloadable_documents.append(
            {
                "download_type": download_type,
                "document": document_id,
            }
        )

    if not downloadable_documents:
        return [], "right column has no tiles"

    return downloadable_documents, None


def try_convert_multicolumns_block(block: dict) -> tuple[dict | None, str | None]:
    if block.get("type") != MULTICOLUMNS_BLOCK:
        return None, "not a multicolumns block"

    value = block.get("value", {})
    if value.get("title"):
        return None, "multicolumns title must be empty"

    columns = value.get("columns", [])
    if len(columns) != 2:
        return None, f"expected 2 columns, found {len(columns)}"

    left_content = _column_content_by_width(columns, LEFT_COLUMN_WIDTH)
    right_content = _column_content_by_width(columns, RIGHT_COLUMN_WIDTH)
    if left_content is None or right_content is None:
        return None, "missing required column widths 8 and 4"

    non_html_blocks = [item for item in left_content if item.get("type") != "html"]
    if non_html_blocks:
        block_types = ", ".join(sorted({item.get("type", "?") for item in non_html_blocks}))
        return None, f"left column contains non-html blocks: {block_types}"

    html_blocks = [item for item in left_content if item.get("type") == "html"]
    if len(html_blocks) > MAX_HTML_BLOCKS:
        return None, f"left column has more than {MAX_HTML_BLOCKS} html blocks"

    subtitle, summary, parse_error = _parse_html_fields(html_blocks)
    if parse_error:
        return None, parse_error

    non_tile_blocks = [item for item in right_content if item.get("type") != "tile"]
    if non_tile_blocks:
        block_types = ", ".join(sorted({item.get("type", "?") for item in non_tile_blocks}))
        return None, f"right column contains non-tile blocks: {block_types}"

    tile_blocks = [item for item in right_content if item.get("type") == "tile"]
    downloadable_documents, tile_error = _parse_downloadable_documents(tile_blocks)
    if tile_error:
        return None, tile_error

    return (
        {
            "type": STANDARD_PUBLICATION_BLOCK,
            "id": str(uuid.uuid4()),
            "value": {
                "subtitle": subtitle,
                "summary": summary,
                "downloadable_documents": downloadable_documents,
            },
        },
        None,
    )


def transform_body_stream(stream_data: list) -> tuple[list, list[BlockMigrationResult]]:
    transformed_stream = []
    results: list[BlockMigrationResult] = []

    for block in stream_data:
        if block.get("type") != MULTICOLUMNS_BLOCK:
            transformed_stream.append(block)
            continue

        converted_block, skip_reason = try_convert_multicolumns_block(block)
        if converted_block is None:
            transformed_stream.append(block)
            results.append(BlockMigrationResult(action="skipped", reason=skip_reason))
            continue

        transformed_stream.append(converted_block)
        results.append(BlockMigrationResult(action="migrated"))

    return transformed_stream, results


def _migrate_page_body(page, *, dry_run: bool) -> PageMigrationResult:
    stream_data = list(page.body.raw_data)
    transformed_stream, block_results = transform_body_stream(stream_data)
    result = PageMigrationResult(page_id=page.pk, page_url=page.url, block_results=block_results)

    if result.migrated_count == 0:
        return result

    if dry_run:
        return result

    page.body = transformed_stream
    page.save(update_fields=["body"])

    for revision in page.revisions.all().iterator():
        content = revision.content
        body = content.get("body")
        if not body:
            continue
        revision_stream, revision_results = transform_body_stream(body)
        if not any(item.action == "migrated" for item in revision_results):
            continue
        content = copy.copy(content)
        content["body"] = revision_stream
        revision.content = content
        revision.save(update_fields=["content"])

    return result


def run_migration(
    pages,
    *,
    dry_run: bool,
    log_file: TextIO | None = None,
) -> MigrationSummary:
    summary = MigrationSummary(dry_run=dry_run)

    def log(line: str) -> None:
        if log_file is not None:
            log_file.write(line + "\n")
            log_file.flush()

    log("=== migrate_to_standard_publications ===")
    log(f"dry_run: {dry_run}")

    page_iter = pages.iterator() if hasattr(pages, "iterator") else iter(pages)

    with transaction.atomic():
        for page in page_iter:
            summary.pages_scanned += 1
            page_result = _migrate_page_body(page, dry_run=dry_run)
            if page_result.migrated_count == 0 and page_result.skipped_count == 0:
                continue

            summary.page_results.append(page_result)
            summary.blocks_migrated += page_result.migrated_count
            summary.blocks_skipped += page_result.skipped_count

            if page_result.migrated_count:
                summary.pages_changed += 1
                log(f"MIGRATED: id={page_result.page_id} {page_result.page_url} ({page_result.migrated_count} block(s))")

            for block_result in page_result.block_results:
                if block_result.action != "skipped":
                    continue
                log(f"SKIPPED: id={page_result.page_id} {page_result.page_url} reason: {block_result.reason}")

        if dry_run:
            transaction.set_rollback(True)

    log("")
    log(f"pages_scanned: {summary.pages_scanned}")
    log(f"pages_changed: {summary.pages_changed}")
    log(f"blocks_migrated: {summary.blocks_migrated}")
    log(f"blocks_skipped: {summary.blocks_skipped}")

    return summary
