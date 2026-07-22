"""Search result filters (fork-specific; mirrors PublicationIndexPage and blog facets)."""

from dataclasses import dataclass, field
from typing import Any

from django.http import Http404
from django.shortcuts import get_object_or_404

from publications.models import Collection, PublicationPage, Theme
from sites_conformes.blog.models import BlogEntryPage, Category, Organization, Person
from sites_conformes.core.models import ContentPage, Tag

"""Which filter sections to show on the search page."""
ENABLED_FILTERS: dict[str, bool] = {
    "filter_by_category": False,
    "filter_by_collection": True,
    "filter_by_theme": True,
    "filter_by_tag": True,
    "filter_by_author": True,
    "filter_by_source": True,
    "filter_by_year": True,
}


@dataclass
class ActiveFilters:
    categories: list[Category] = field(default_factory=list)
    collections: list[Collection] = field(default_factory=list)
    themes: list[Theme] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)
    sources: list[Organization] = field(default_factory=list)
    authors: list[Person] = field(default_factory=list)
    years: list[str] = field(default_factory=list)


@dataclass
class TaxonomyFilterNode:
    taxonomy: Any
    children: list["TaxonomyFilterNode"] = field(default_factory=list)


def _build_taxonomy_filter_tree(taxonomies, taxonomy_model, locale) -> list[TaxonomyFilterNode]:
    """Build a tree containing selected taxonomies and all of their ancestors."""
    nodes = {taxonomy.pk: TaxonomyFilterNode(taxonomy=taxonomy) for taxonomy in taxonomies}

    missing = {taxonomy.parent_id for taxonomy in taxonomies if taxonomy.parent_id} - nodes.keys()
    while missing:
        for parent in taxonomy_model.objects.filter(locale=locale, id__in=missing).order_by("name"):
            nodes[parent.pk] = TaxonomyFilterNode(taxonomy=parent)
        missing = {node.taxonomy.parent_id for node in nodes.values() if node.taxonomy.parent_id} - nodes.keys()

    roots = []
    for node in sorted(nodes.values(), key=lambda item: item.taxonomy.name):
        parent_id = node.taxonomy.parent_id
        if parent_id in nodes:
            nodes[parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


def _validate_int(value: str) -> int:
    """Return an integer from a query parameter, or raise Http404 for invalid input."""
    try:
        return int(value)
    except (ValueError, TypeError) as exc:
        raise Http404(f"Invalid integer filter value: {value}") from exc


def _is_valid_year(value: str) -> bool:
    """Return True if the value is a four-digit year string."""
    return isinstance(value, str) and value.isdigit() and len(value) == 4


def get_active_filters_from_request_params(request, site) -> ActiveFilters:
    """Resolve active filter objects from GET parameters."""
    locale = site.root_page.localized.locale
    active = ActiveFilters()

    category_slugs = request.GET.getlist("category")
    if category_slugs:
        active.categories = [get_object_or_404(Category, slug=slug, locale=locale) for slug in category_slugs]

    collection_slugs = request.GET.getlist("collection")
    if collection_slugs:
        active.collections = [get_object_or_404(Collection, slug=slug, locale=locale) for slug in collection_slugs]

    theme_slugs = request.GET.getlist("theme")
    if theme_slugs:
        active.themes = [get_object_or_404(Theme, slug=slug, locale=locale) for slug in theme_slugs]

    tag_slugs = request.GET.getlist("tag")
    if tag_slugs:
        active.tags = [get_object_or_404(Tag, slug=slug) for slug in tag_slugs]

    source_slugs = request.GET.getlist("source")
    if source_slugs:
        active.sources = [get_object_or_404(Organization, slug=slug) for slug in source_slugs]

    author_ids = request.GET.getlist("author")
    if author_ids:
        active.authors = [get_object_or_404(Person, id=_validate_int(author_id)) for author_id in author_ids]

    active.years = [year for year in request.GET.getlist("year") if _is_valid_year(year)]
    return active


def filter_queryset(request, queryset, site):
    """Apply GET filter params before full-text search (see ``filter_before_search``)."""
    root = site.root_page.localized
    active = get_active_filters_from_request_params(request, site)

    if active.categories:
        facet_page_ids = (
            BlogEntryPage.objects.descendant_of(root)
            .live()
            .filter(blog_categories__in=active.categories)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    if active.collections:
        facet_page_ids = (
            PublicationPage.objects.descendant_of(root)
            .live()
            .filter(collections__in=active.collections)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    if active.themes:
        facet_page_ids = (
            PublicationPage.objects.descendant_of(root)
            .live()
            .filter(themes__in=active.themes)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    if active.tags:
        content_page_ids = (
            ContentPage.objects.descendant_of(root).live().filter(tags__in=active.tags).values_list("pk", flat=True)
        )
        blog_page_ids = (
            # PublicationPage entries are included (subclass of BlogEntryPage).
            BlogEntryPage.objects.descendant_of(root)
            .live()
            .filter(tags__in=active.tags)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=content_page_ids.union(blog_page_ids))

    if active.sources:
        facet_page_ids = (
            BlogEntryPage.objects.descendant_of(root)
            .live()
            .filter(authors__organization__in=active.sources)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    if active.authors:
        facet_page_ids = (
            BlogEntryPage.objects.descendant_of(root)
            .live()
            .filter(authors__in=active.authors)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    if active.years:
        facet_page_ids = (
            BlogEntryPage.objects.descendant_of(root)
            .live()
            .filter(date__year__in=active.years)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    return queryset


def get_filter_context(request, site, *, enabled_filters: dict[str, bool] | None = None) -> dict:
    """Build context for the filter sidebar: enabled filters, filter values lists, active filter values."""
    if enabled_filters is None:
        enabled_filters = ENABLED_FILTERS

    root = site.root_page.localized
    locale = root.locale
    # Includes PublicationPage entries (subclass of BlogEntryPage).
    blog_entries = BlogEntryPage.objects.descendant_of(root).live()
    content_pages = ContentPage.objects.descendant_of(root).live()
    publication_pages = PublicationPage.objects.descendant_of(root).live()
    active = get_active_filters_from_request_params(request, site)

    context = {
        **enabled_filters,
        "current_categories": active.categories,
        "current_collections": active.collections,
        "current_themes": active.themes,
        "current_tags": active.tags,
        "current_sources": active.sources,
        "current_authors": active.authors,
        "years": active.years,
    }

    if context["filter_by_category"]:
        category_ids = blog_entries.values_list("blog_categories", flat=True)
        context["categories"] = Category.objects.filter(id__in=category_ids, locale=locale).order_by("name")

    if context["filter_by_tag"]:
        tag_ids = set(content_pages.values_list("tags", flat=True))
        tag_ids |= set(blog_entries.values_list("tags", flat=True))
        tag_ids.discard(None)
        context["tags"] = Tag.objects.filter(id__in=tag_ids).order_by("name")

    if context["filter_by_author"]:
        author_ids = blog_entries.values_list("authors", flat=True)
        context["authors"] = Person.objects.filter(id__in=author_ids).order_by("name")

    if context["filter_by_source"]:
        org_ids = blog_entries.values_list("authors__organization", flat=True)
        context["sources"] = Organization.objects.filter(id__in=org_ids).order_by("name")

    if context["filter_by_collection"]:
        collection_ids = publication_pages.values_list("collections", flat=True)
        collection_qs = Collection.objects.filter(id__in=collection_ids, locale=locale).order_by("name")
        context["collection_tree"] = _build_taxonomy_filter_tree(collection_qs, Collection, locale)

    if context["filter_by_theme"]:
        theme_ids = publication_pages.values_list("themes", flat=True)
        theme_qs = Theme.objects.filter(id__in=theme_ids, locale=locale).order_by("name")
        context["theme_tree"] = _build_taxonomy_filter_tree(theme_qs, Theme, locale)

    context["show_search_filters"] = _show_search_filters(context)
    return context


def _show_search_filters(context: dict) -> bool:
    if context.get("filter_by_category") and context.get("categories"):
        return True
    if context.get("filter_by_collection") and context.get("collection_tree"):
        return True
    if context.get("filter_by_theme") and context.get("theme_tree"):
        return True
    if context.get("filter_by_tag") and context.get("tags"):
        return True
    if context.get("filter_by_author") and context.get("authors"):
        return True
    if context.get("filter_by_source") and context.get("sources"):
        return True
    return False
