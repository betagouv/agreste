"""
Inject publications StreamField blocks into Sites Conformes at Django startup.

The ``publications`` app extends page editors without editing ``sites_conformes``
or generating migrations there. On startup (``publications.apps.PublicationsConfig.ready``),
``register_sites_conformes_blocks()`` adds five blocks wherever ``blog_recent_entries``
is already available:

- ``publication_recent_entries`` — same picker group as ``blog_recent_entries``
- ``download_tile`` — always in the "Agreste" group (from ``DownloadTileBlock.Meta``)
- ``publication_subtitle`` — always in the "Agreste" group (from ``PublicationSubtitleBlock.Meta``)
- ``publication_summary`` — always in the "Agreste" group (from ``PublicationSummaryBlock.Meta``)
- ``standard_publication`` — always in the "Agreste" group (from ``StandardPublicationBlock.Meta``)

That includes the top-level ``body`` stream on every ``SitesFacilesBasePage``, and
nested streams inside layout blocks (multicolumns, item grid, tabs, etc.).

Wagtail copies block definitions when models are imported, so we patch the live
``child_blocks`` dicts on existing ``StreamField`` instances rather than changing
``STREAMFIELD_COMMON_BLOCKS`` in source.

Registration is skipped during ``makemigrations`` and ``squashmigrations`` so
running migrations against ``sites_conformes`` does not pick up these blocks.

Note: ``_register_publications_blocks_on_common_stream_blocks()`` also patches
``CommonStreamBlock.base_blocks``, but that is probably redundant: Wagtail copies
``base_blocks`` into each instance at creation time, and the walk over page
``StreamField`` trees is what actually updates the block definitions the admin uses.
"""

import sys

from django.apps import apps
from wagtail import blocks
from wagtail.blocks import StreamBlock
from wagtail.fields import StreamField

from publications.blocks.download_tile import DOWNLOAD_TILE_BLOCK, DownloadTileBlock
from publications.blocks.publication_subtitle import (
    PUBLICATION_SUBTITLE_BLOCK,
    PublicationSubtitleBlock,
)
from publications.blocks.publication_summary import (
    PUBLICATION_SUMMARY_BLOCK,
    PublicationSummaryBlock,
)
from publications.blocks.recent_entries import (
    PUBLICATION_RECENT_ENTRIES_BLOCK,
    PublicationRecentEntriesBlock,
)
from publications.blocks.standard_publication import (
    STANDARD_PUBLICATION_BLOCK,
    StandardPublicationBlock,
)
from sites_conformes.core.abstract import SitesFacilesBasePage

_MIGRATION_AUTHORING_COMMANDS = frozenset({"makemigrations", "squashmigrations"})


def _is_migration_authoring_command() -> bool:
    return len(sys.argv) > 1 and sys.argv[1] in _MIGRATION_AUTHORING_COMMANDS


BLOG_RECENT_ENTRIES_BLOCK = "blog_recent_entries"


def _make_publication_recent_entries_block(group) -> PublicationRecentEntriesBlock:
    block = PublicationRecentEntriesBlock(group=group)
    block.set_name(PUBLICATION_RECENT_ENTRIES_BLOCK)
    return block


def _make_download_tile_block() -> DownloadTileBlock:
    block = DownloadTileBlock()
    block.set_name(DOWNLOAD_TILE_BLOCK)
    return block


def _make_publication_subtitle_block() -> PublicationSubtitleBlock:
    block = PublicationSubtitleBlock()
    block.set_name(PUBLICATION_SUBTITLE_BLOCK)
    return block


def _make_publication_summary_block() -> PublicationSummaryBlock:
    block = PublicationSummaryBlock()
    block.set_name(PUBLICATION_SUMMARY_BLOCK)
    return block


def _make_standard_publication_block() -> StandardPublicationBlock:
    block = StandardPublicationBlock()
    block.set_name(STANDARD_PUBLICATION_BLOCK)
    return block


def _add_publications_blocks_to_mapping(blocks_mapping: dict) -> bool:
    """Add publications blocks next to ``blog_recent_entries`` in a block mapping."""
    if BLOG_RECENT_ENTRIES_BLOCK not in blocks_mapping:
        return False

    added = False
    blog_block = blocks_mapping[BLOG_RECENT_ENTRIES_BLOCK]

    if PUBLICATION_RECENT_ENTRIES_BLOCK not in blocks_mapping:
        blocks_mapping[PUBLICATION_RECENT_ENTRIES_BLOCK] = _make_publication_recent_entries_block(
            blog_block.meta.group
        )
        added = True

    if DOWNLOAD_TILE_BLOCK not in blocks_mapping:
        blocks_mapping[DOWNLOAD_TILE_BLOCK] = _make_download_tile_block()
        added = True

    if PUBLICATION_SUBTITLE_BLOCK not in blocks_mapping:
        blocks_mapping[PUBLICATION_SUBTITLE_BLOCK] = _make_publication_subtitle_block()
        added = True

    if PUBLICATION_SUMMARY_BLOCK not in blocks_mapping:
        blocks_mapping[PUBLICATION_SUMMARY_BLOCK] = _make_publication_summary_block()
        added = True

    if STANDARD_PUBLICATION_BLOCK not in blocks_mapping:
        blocks_mapping[STANDARD_PUBLICATION_BLOCK] = _make_standard_publication_block()
        added = True

    return added


def _walk_and_patch_block_tree(block) -> None:
    """Patch every ``StreamBlock`` in the tree that allows ``blog_recent_entries``."""
    if isinstance(block, StreamBlock):
        _add_publications_blocks_to_mapping(block.child_blocks)
        for child in block.child_blocks.values():
            _walk_and_patch_block_tree(child)
        return

    if isinstance(block, blocks.StructBlock):
        for child in block.child_blocks.values():
            _walk_and_patch_block_tree(child)
        return

    if isinstance(block, blocks.ListBlock):
        _walk_and_patch_block_tree(block.child_block)


def _add_publications_blocks_to_stream_field(field) -> bool:
    """Register on a model ``StreamField`` whose block list already includes ``blog_recent_entries``."""
    if not hasattr(field, "stream_block"):
        return False

    current_block = field.stream_block
    _walk_and_patch_block_tree(current_block)
    return BLOG_RECENT_ENTRIES_BLOCK in current_block.child_blocks


def _register_publications_blocks_on_common_stream_blocks() -> None:
    """Patch ``CommonStreamBlock`` class definitions for newly created instances."""
    from sites_conformes.core.blocks.layout import CommonStreamBlock

    def all_subclasses(cls):
        for subclass in cls.__subclasses__():
            yield subclass
            yield from all_subclasses(subclass)

    for block_cls in (CommonStreamBlock, *all_subclasses(CommonStreamBlock)):
        if BLOG_RECENT_ENTRIES_BLOCK not in block_cls.base_blocks:
            continue
        _add_publications_blocks_to_mapping(block_cls.base_blocks)


def register_sites_conformes_blocks():
    """Register publications StreamField blocks on Sites Conformes page types."""
    if _is_migration_authoring_command():
        return

    _register_publications_blocks_on_common_stream_blocks()

    for model in apps.get_models():
        if model._meta.abstract or not issubclass(model, SitesFacilesBasePage):
            continue
        for field in model._meta.get_fields():
            if not isinstance(field, StreamField):
                continue
            _add_publications_blocks_to_stream_field(field)
