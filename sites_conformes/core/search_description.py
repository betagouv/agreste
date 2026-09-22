import logging
import re

from bs4 import BeautifulSoup
from wagtail.blocks import CharBlock, ListBlock, RichTextBlock, StreamBlock, StructBlock, TextBlock
from wagtailmarkdown.blocks import MarkdownBlock

logger = logging.getLogger(__name__)

REMOVABLE_BLOCK_NAMES = frozenset(
    {
        "image",
        "alert",
        "video",
        "stepper",
        "separator",
        "html",
        "iframe",
    }
)
SEARCH_DESCRIPTION_MAX_CHARS = 300


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")
    # Collapse spaces, tabs and other non-newline whitespace so HTML gaps
    # (e.g. between tags) become a single space.
    return re.sub(r"[^\S\n]+", " ", text).strip()


def _join_block_texts(children) -> str:
    parts = list(filter(None, (get_streamblock_raw_text(child) for child in children)))
    if not parts:
        return ""
    result = parts[0].rstrip()
    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        if result.endswith((".", "!", "?", ":", ";")):
            result = f"{result} {part}"
        else:
            result = f"{result}. {part}"
    return result


def get_streamblock_raw_text(block) -> str:
    """
    Get the raw text of a streamblock, walking nested values instead of rendering templates.
    Layout fields (width, alignment, margins, …) are skipped so their labels and
    values do not leak into search_description.
    """
    try:
        inner = getattr(block, "block", None)
        if inner is None or inner.name in REMOVABLE_BLOCK_NAMES:
            return ""

        value = block.value
        if value is None or value == "":
            return ""

        if isinstance(inner, RichTextBlock):
            html = value.source if hasattr(value, "source") else str(value)
            return _html_to_text(html)

        if isinstance(inner, MarkdownBlock):
            return _html_to_text(str(value))

        if isinstance(inner, (CharBlock, TextBlock)):
            return str(value).strip()

        if isinstance(inner, StructBlock):
            bound_blocks = getattr(value, "bound_blocks", None)
            if not bound_blocks:
                return ""
            return _join_block_texts(bound_blocks.values())

        if isinstance(inner, ListBlock):
            # ListValue iterates raw child values, not BoundBlocks.
            children = getattr(value, "bound_blocks", None)
            if children is None:
                return ""
            return _join_block_texts(children)

        if isinstance(inner, StreamBlock):
            return _join_block_texts(value)

        return ""
    except Exception:
        logger.exception(
            "Could not extract search description text from block %r",
            getattr(getattr(block, "block", None), "name", type(block).__name__),
        )
        return ""


def get_search_description(*streamfields, max_chars: int | None = None) -> str:
    """
    Get the raw text of one or more streamfields. Used to pre-fill the search description field.
    """
    raw_text = _join_block_texts(block for streamfield in streamfields if streamfield for block in streamfield)
    if not raw_text:
        return ""

    # Truncate at the last space before the max_chars limit.
    if max_chars and len(raw_text) > max_chars:
        truncated = raw_text[:max_chars]
        cut = truncated.rfind(" ")
        if cut > 0:
            truncated = truncated[:cut]
        raw_text = f"{truncated.rstrip()} [...]"

    return raw_text
