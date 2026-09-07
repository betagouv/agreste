"""Extract Disaron identifiers embedded in publication page stream content."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

DISARON_NOM_ELEMENT_ID = "disaron-nom"


def _as_json_data(value: Any) -> Any:
    """Normalize StreamField values to plain JSON-serializable data."""
    if value is None:
        return None
    raw_data = getattr(value, "raw_data", None)
    if raw_data is not None:
        return raw_data
    get_prep_value = getattr(value, "get_prep_value", None)
    if callable(get_prep_value):
        return get_prep_value()
    return value


def _collect_html_fragments(value: Any, fragments: list[str]) -> None:
    """Recursively collect string fragments that may contain HTML from StreamField JSON."""
    value = _as_json_data(value)
    if isinstance(value, str):
        if "<" in value:
            fragments.append(value)
        return
    if isinstance(value, dict):
        for child in value.values():
            _collect_html_fragments(child, fragments)
        return
    if isinstance(value, list):
        for child in value:
            _collect_html_fragments(child, fragments)


def extract_disaron_id_from_html(html: str) -> str | None:
    """Return the stripped text of ``div#disaron-nom`` in ``html``, or ``None``."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    element = soup.find(id=DISARON_NOM_ELEMENT_ID)
    if element is None:
        return None
    text = element.get_text(strip=True)
    return text or None


def extract_disaron_id_from_stream_data(*stream_values: Any) -> str | None:
    """
    Walk StreamField JSON (body, hero, …) and return the first ``#disaron-nom`` text found.
    """
    fragments: list[str] = []
    for stream_value in stream_values:
        _collect_html_fragments(stream_value, fragments)
    if not fragments:
        return None
    return extract_disaron_id_from_html("\n".join(fragments))
