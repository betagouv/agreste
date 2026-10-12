"""Add a "Search results" link type to Sites Conformes links without editing that package.

``LinkWithoutLabelBlock`` is the link inside tiles, cards, and tags, and the parent of
buttons. Patching it at startup covers all of them. The patch is skipped while
migrations are authored, so Sites Conformes migrations keep the original link definition.
"""

import sys
from collections import OrderedDict

from django.apps import apps
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.admin.telepath import register
from wagtail.blocks import StreamBlock
from wagtail.fields import StreamField
from wagtail.snippets.blocks import SnippetChooserBlock

from faceted_search.search import RANK_BY_DATE, RANK_BY_RELEVANCE
from faceted_search.templatetags.faceted_search_tags import search_link
from sites_conformes.core.blocks.buttons_links import (
    ButtonBlock,
    LinkBlock,
    LinkBlockAdapter,
    LinkStructValue,
    LinkWithoutLabelBlock,
    SingleLinkBlock,
)

SEARCH_LINK_TYPE = "search"
SEARCH_FIELD_NAMES = ("q", "collection", "theme", "date_from", "date_to", "rank_by")
_LINK_BLOCK_CLASSES = (LinkWithoutLabelBlock, LinkBlock, ButtonBlock, SingleLinkBlock)
_MIGRATION_AUTHORING_COMMANDS = frozenset({"makemigrations", "squashmigrations"})

_search_child_blocks: list[tuple[str, blocks.Block]] | None = None


def _is_migration_authoring_command() -> bool:
    return len(sys.argv) > 1 and sys.argv[1] in _MIGRATION_AUTHORING_COMMANDS


def _search_blocks() -> list[tuple[str, blocks.Block]]:
    """Child blocks inserted into every link, created once and shared."""
    global _search_child_blocks
    if _search_child_blocks is None:
        _search_child_blocks = [
            ("q", blocks.CharBlock(label=_("Query"), required=False)),
            (
                "collection",
                SnippetChooserBlock("publications.Collection", label=_("Collection"), required=False),
            ),
            (
                "theme",
                SnippetChooserBlock("publications.Theme", label=_("Theme"), required=False),
            ),
            ("date_from", blocks.DateBlock(label=_("Start date"), required=False)),
            ("date_to", blocks.DateBlock(label=_("End date"), required=False)),
            (
                "rank_by",
                blocks.ChoiceBlock(
                    label=_("Rank by:"),
                    choices=[
                        ("", _("Default")),
                        (RANK_BY_DATE, _("Date")),
                        (RANK_BY_RELEVANCE, _("Relevance")),
                    ],
                    required=False,
                    default="",
                ),
            ),
        ]
        for name, block in _search_child_blocks:
            block.set_name(name)
    return _search_child_blocks


def _date_param(value) -> str:
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _install_url_and_clean() -> None:
    if getattr(LinkStructValue.url, "_is_search_link_url", False):
        return

    original_url = LinkStructValue.url

    def url(self):
        if self.get("link_type") != SEARCH_LINK_TYPE:
            return original_url(self)

        collection = self.get("collection")
        theme = self.get("theme")
        return search_link(
            q=self.get("q") or "",
            collection=getattr(collection, "slug", None),
            theme=getattr(theme, "slug", None),
            date_from=_date_param(self.get("date_from")),
            date_to=_date_param(self.get("date_to")),
            rank_by=self.get("rank_by") or "",
        )

    url._is_search_link_url = True
    LinkStructValue.url = url

    original_clean = LinkWithoutLabelBlock.clean

    def clean(self, value):
        if value.get("link_type") == SEARCH_LINK_TYPE:
            value["anchor"] = ""
            value["query_string"] = ""
        else:
            value["q"] = ""
            value["collection"] = None
            value["theme"] = None
            value["date_from"] = None
            value["date_to"] = None
            value["rank_by"] = ""
        return original_clean(self, value)

    LinkWithoutLabelBlock.clean = clean


def _append_search_choice(link_type_block) -> None:
    choices = link_type_block._constructor_kwargs["choices"]
    if any(key == SEARCH_LINK_TYPE for key, _label in choices):
        return
    choices.append((SEARCH_LINK_TYPE, _("Search results")))


def _insert_search_fields_in_layout(block) -> None:
    layout = getattr(block.meta, "form_layout", None)
    children = getattr(layout, "children", None)
    if children is None:
        return
    if all(name in children for name in SEARCH_FIELD_NAMES):
        return
    index = children.index("query_string") + 1 if "query_string" in children else len(children)
    for offset, name in enumerate(SEARCH_FIELD_NAMES):
        if name not in children:
            children.insert(index + offset, name)


def _patch_child_block_mapping(child_blocks: OrderedDict) -> None:
    link_type_block = child_blocks.get("link_type")
    if link_type_block is None:
        return
    _append_search_choice(link_type_block)
    for name, block in _search_blocks():
        child_blocks.setdefault(name, block)


def _patch_link_block(block) -> None:
    _patch_child_block_mapping(block.child_blocks)
    if SEARCH_LINK_TYPE not in block.link_types:
        block.link_types.append(SEARCH_LINK_TYPE)
    _insert_search_fields_in_layout(block)


def _walk(block, seen: set[int]) -> None:
    if block is None or id(block) in seen:
        return
    seen.add(id(block))

    if isinstance(block, StreamBlock):
        children = list(block.child_blocks.values())
    elif isinstance(block, blocks.StructBlock):
        children = list(block.child_blocks.values())
    elif isinstance(block, blocks.ListBlock):
        children = [block.child_block]
    else:
        children = []

    for child in children:
        _walk(child, seen)

    if isinstance(block, LinkWithoutLabelBlock):
        _patch_link_block(block)


def register_search_link_type() -> None:
    """Patch live link blocks so editors can link to a filtered search page."""
    if _is_migration_authoring_command():
        return

    _install_url_and_clean()

    choices = LinkWithoutLabelBlock.LINK_TYPE_CHOICES
    if not any(key == SEARCH_LINK_TYPE for key, _label in choices):
        choices.append((SEARCH_LINK_TYPE, _("Search results")))

    seen: set[int] = set()
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if isinstance(field, StreamField) and hasattr(field, "stream_block"):
                _walk(field.stream_block, seen)

    for block_cls in _LINK_BLOCK_CLASSES:
        _patch_child_block_mapping(block_cls.base_blocks)

    register(SearchLinkBlockAdapter(), LinkWithoutLabelBlock)


class SearchLinkBlockAdapter(LinkBlockAdapter):
    """Same link editor, plus the script that shows search fields for this type."""

    @property
    def media(self):
        from django import forms

        # Evaluate the parent media on a throwaway instance. ``cached_property`` would
        # otherwise store that result on this instance and hide this property.
        scratch = object.__new__(LinkBlockAdapter)
        parent_media = LinkBlockAdapter.__dict__["media"].__get__(scratch, LinkBlockAdapter)
        return forms.Media(js=[*parent_media._js, "faceted_search/js/search_link_block.js"])
