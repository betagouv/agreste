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


@register.simple_tag
def collection_chains(collections):
    """Chains of collections assigned to one page, parents before their children.

    A parent is included only when it is assigned itself. An assigned child whose
    parent is not assigned stays a chain of one. Order follows ``collections``.
    """
    assigned = list(collections)
    assigned_ids = {collection.pk for collection in assigned}
    children_by_parent = {}
    for collection in assigned:
        if collection.parent_id in assigned_ids:
            children_by_parent.setdefault(collection.parent_id, []).append(collection)

    def chains_from(node):
        children = children_by_parent.get(node.pk, [])
        if not children:
            return [[node]]
        return [[node, *chain] for child in children for chain in chains_from(child)]

    chains = []
    for collection in assigned:
        if collection.parent_id not in assigned_ids:
            chains.extend(chains_from(collection))
    return chains
