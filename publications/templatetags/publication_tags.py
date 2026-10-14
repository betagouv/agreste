from django import template

from sites_conformes.core.templatetags.wagtail_dsfr_tags import (
    FilterSpec,
    build_toggle_url_query_string,
)

register = template.Library()

PUBLICATION_FILTERS: list[FilterSpec] = [
    ("author", "id"),
    ("collection", "slug"),
    ("theme", "slug"),
    ("source", "slug"),
    ("tag", "slug"),
    ("year", ""),
]


@register.simple_tag(takes_context=True)
def toggle_url_filter(context, *_, **kwargs):
    """Blog ``toggle_url_filter`` with collection and theme query parameters."""
    return build_toggle_url_query_string(context, PUBLICATION_FILTERS, **kwargs)
