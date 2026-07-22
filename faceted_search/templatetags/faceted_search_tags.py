from django import template
from django.http import QueryDict
from django.template.loader import render_to_string as _render_to_string

from sites_conformes.core.templatetags.wagtail_dsfr_tags import FilterSpec

register = template.Library()

SEARCH_FILTERS: list[FilterSpec] = [
    ("author", "id"),
    ("category", "slug"),
    ("collection", "slug"),
    ("theme", "slug"),
    ("source", "slug"),
    ("tag", "slug"),
    ("year", ""),
]


@register.simple_tag(takes_context=True)
def toggle_url_filter(context, *_, **kwargs):
    """Toggle one faceted-search filter in the current URL.

    ``context`` is the Django template context and must contain ``request``.
    The request's GET parameters provide the current URL state, for example
    ``?q=climate&collection=agriculture&collection=water``.

    ``kwargs`` contains the one filter option being toggled, for example
    ``collection=collection`` or ``author=author`` from the template. The
    option is added if it is not selected and removed if it is selected.
    Other request parameters, including ``q`` and repeated filter values, are
    preserved.

    ``filters_dict`` is only needed when a caller wants to toggle a filter
    against a prepared URL state instead of the current request, such as when
    building a link from saved or inherited filters. It replaces
    ``request.GET`` as the starting URL state. Its values may be scalars or
    lists, for example
    ``{"collection": ["agriculture", "water"], "q": "climate"}``.

    The return value is a URL query string such as
    ``"?q=climate&collection=water"`` or an empty string if no parameters
    remain.
    """

    def get_filters_before_toggle(context, filters_dict=None) -> QueryDict:
        """Build the query parameters that exist before toggling a filter."""
        if filters_dict:
            # Expected format: {"collection": ["agriculture", "climate"], "q": "search text"}.
            query_params = QueryDict("", mutable=True)
            for key, values in filters_dict.items():
                query_params.setlist(key, values if isinstance(values, list) else [values])
            return query_params
        return context["request"].GET.copy()

    def toggle_filter_value(query_params: QueryDict, filter_name: str, value: str) -> QueryDict:
        """Add a filter value to the query or remove it if already selected."""
        current_values = query_params.getlist(filter_name)
        if value in current_values:
            current_values.remove(value)
        else:
            current_values.append(value)
        query_params.setlist(filter_name, current_values)
        return query_params

    filters_dict = kwargs.pop("filters_dict", None)
    url_params = get_filters_before_toggle(context, filters_dict)

    for filter_name, attribute_name in SEARCH_FILTERS:
        # Template calls pass one facet object/value, e.g. collection=collection or year=2024.
        object_to_toggle = kwargs.get(filter_name)
        if not object_to_toggle:
            continue

        if filter_name == "year":
            string_value_to_toggle = str(object_to_toggle)
        else:
            string_value_to_toggle = str(getattr(object_to_toggle, attribute_name))

        url_params = toggle_filter_value(url_params, filter_name, string_value_to_toggle)

    query_string = url_params.urlencode()
    return f"?{query_string}" if query_string else ""


@register.simple_tag(takes_context=True)
def render_to_string(context, template_name, **kwargs):
    """Render a template to a string so it can be passed to inclusion tags."""
    new_context = context.flatten()
    new_context.update(kwargs)
    return _render_to_string(template_name, new_context, request=context.get("request"))
