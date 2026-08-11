from django import template
from django.http import QueryDict
from django.template.loader import render_to_string as _render_to_string

from sites_conformes.core.templatetags.wagtail_dsfr_tags import FilterSpec

register = template.Library()


@register.simple_tag
def facet_label(name, count=None):
    """Label for a facet value tag, with result count when available.

    See ``faceted_search/result_counts.md`` for how ``count`` is computed.
    """
    if count is None or count == "":
        return str(name)
    return f"{name} ({count})"


SEARCH_FACETS: list[FilterSpec] = [
    ("author", "id"),
    ("category", "slug"),
    ("collection", "slug"),
    ("theme", "slug"),
    ("source", "slug"),
    ("tag", "slug"),
    ("year", ""),
]


@register.simple_tag(takes_context=True)
def toggle_url_facet(context, *_, **kwargs):
    """Toggle one faceted-search facet value in the current URL.

    ``context`` is the Django template context and must contain ``request``.
    The request's GET parameters provide the current URL state, for example
    ``?q=climate&collection=agriculture&collection=water``.

    ``kwargs`` contains the one facet value being toggled, for example
    ``collection=collection`` or ``author=author`` from the template. The
    value is added if it is not selected and removed if it is selected.
    Other request parameters, including ``q`` and repeated facet values, are
    preserved.

    The return value is a URL query string such as
    ``"?q=climate&collection=water"`` or an empty string if no parameters
    remain.
    """

    def _toggle_facet_value(query_params: QueryDict, facet: str, value: str) -> QueryDict:
        """Add a facet value to the query or remove it if already selected."""
        current_values = query_params.getlist(facet)
        if value in current_values:
            current_values.remove(value)
        else:
            current_values.append(value)
        query_params.setlist(facet, current_values)
        return query_params

    url_params = context["request"].GET.copy()

    for facet, attribute_name in SEARCH_FACETS:
        # Template calls pass one facet object/value, e.g. collection=collection or year=2024.
        object_to_toggle = kwargs.get(facet)
        if not object_to_toggle:
            continue

        if facet == "year":
            string_value_to_toggle = str(object_to_toggle)
        else:
            string_value_to_toggle = str(getattr(object_to_toggle, attribute_name))

        url_params = _toggle_facet_value(url_params, facet, string_value_to_toggle)

    # When the user changes a facet selection, we reset the page number to 1.
    url_params.pop("page", None)

    query_string = url_params.urlencode()
    return f"?{query_string}" if query_string else ""


@register.simple_tag(takes_context=True)
def render_to_string(context, template_name, **kwargs):
    """Render a template to a string so it can be passed to inclusion tags."""
    new_context = context.flatten()
    new_context.update(kwargs)
    return _render_to_string(template_name, new_context, request=context.get("request"))
