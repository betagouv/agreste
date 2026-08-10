"""Search result filters (fork-specific; mirrors PublicationIndexPage and blog facets).

Result-count semantics for the sidebar are documented in ``faceted_search/result_counts.md``.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404
from modelsearch.backends.base import BaseSearchResults
from wagtail.models import Page, Site

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


def searchable_pages(request, site):
    """Live pages under the site root, restricted to public pages for anonymous users."""
    root = site.root_page.localized
    queryset = Page.objects.descendant_of(root, inclusive=True).live()
    if not request.user.is_authenticated:
        queryset = queryset.public()
    return queryset


def apply_active_filters(queryset, site, active: ActiveFilters, *, exclude: str | None = None):
    """Apply active facet filters to ``queryset``, optionally skipping one facet."""
    root = site.root_page.localized

    if active.categories and exclude != "category":
        facet_page_ids = (
            BlogEntryPage.objects.descendant_of(root)
            .live()
            .filter(blog_categories__in=active.categories)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    if active.collections and exclude != "collection":
        facet_page_ids = (
            PublicationPage.objects.descendant_of(root)
            .live()
            .filter(collections__in=active.collections)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    if active.themes and exclude != "theme":
        facet_page_ids = (
            PublicationPage.objects.descendant_of(root)
            .live()
            .filter(themes__in=active.themes)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    if active.tags and exclude != "tag":
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

    if active.sources and exclude != "source":
        facet_page_ids = (
            BlogEntryPage.objects.descendant_of(root)
            .live()
            .filter(authors__organization__in=active.sources)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    if active.authors and exclude != "author":
        facet_page_ids = (
            BlogEntryPage.objects.descendant_of(root)
            .live()
            .filter(authors__in=active.authors)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    if active.years and exclude != "year":
        facet_page_ids = (
            BlogEntryPage.objects.descendant_of(root)
            .live()
            .filter(date__year__in=active.years)
            .values_list("pk", flat=True)
        )
        queryset = queryset.filter(pk__in=facet_page_ids)

    return queryset


def filter_queryset(request, queryset, site):
    """Apply GET filter params before full-text search (see ``filter_before_search``)."""
    active = get_active_filters_from_request_params(request, site)
    return apply_active_filters(queryset, site, active)


def _page_pks_from_search_results(results: BaseSearchResults) -> list[int]:
    """Return primary keys from a Wagtail/modelsearch result set."""
    get_queryset = getattr(results, "get_queryset", None)
    if callable(get_queryset):
        return list(get_queryset().values_list("pk", flat=True))
    return [page.pk for page in results]


def _counts_for_m2m_field(model, page_ids: list[int], m2m_field_name: str) -> dict[int, int]:
    """Among ``page_ids``, count how many pages link to each related M2M object.

    For example::

        _counts_for_m2m_field(model=PublicationPage, page_ids=[101, 102, 103], m2m_field_name="themes")
        # → {7: 2, 9: 1}
        # theme 7 is on two of the three pages, theme 9 on one.

    Returns ``{m2m_object_pk: page_count}``

    Used for facets backed by a many-to-many (or parental M2M) on ``model``,
    e.g. ``PublicationPage.themes``.

    ``order_by()`` clears Page's default ``path`` ordering so it is not pulled
    into ``GROUP BY`` (which would otherwise cap every count at 1).
    """
    if not page_ids:
        return {}
    rows = (
        model.objects.filter(pk__in=page_ids)
        .order_by()
        .exclude(**{m2m_field_name: None})  # Exclude pages that don't have a value for the m2m field
        .values(m2m_field_name)  # Group by the m2m field
        .annotate(result_count=Count("pk", distinct=True))  # Count the number of pages for each m2m object
        .values_list(m2m_field_name, "result_count")  # Return the m2m object and the count
    )
    # rows is a list of (m2m_object_pk, count) tuples. Filter out None values.
    return {m2m_object_pk: count for m2m_object_pk, count in rows if m2m_object_pk is not None}


def _counts_for_tags(page_ids: list[int]) -> dict[int, int]:
    """Among ``page_ids``, count how many pages have each tag.

    Tags live on both ``ContentPage`` and ``BlogEntryPage`` (including
    publications), so both models are queried and the counts are merged.

    Returns ``{tag_pk: page_count}``, for example::

        _counts_for_tags([101, 102, 103])
        # → {4: 2, 8: 1} # tag 4 is on 2 pages, tag 8 is on 1 page
    """
    if not page_ids:
        return {}
    counter: Counter[int] = Counter()
    counter.update(ContentPage.objects.filter(pk__in=page_ids).order_by().values_list("tags", flat=True))
    counter.update(BlogEntryPage.objects.filter(pk__in=page_ids).order_by().values_list("tags", flat=True))
    counter.pop(None, None)
    return dict(counter)


def _counts_for_sources(page_ids: list[int]) -> dict[int, int]:
    """Among ``page_ids``, count how many pages have each source organization.

    Sources are not a direct M2M on the page: they are reached via
    ``BlogEntryPage.authors__organization``.

    Returns ``{organization_pk: page_count}``, for example::

        _counts_for_sources([101, 102, 103])
        # → {2: 2, 5: 1} # organization 2 is on 2 pages, organization 5 is on 1 page
    """
    if not page_ids:
        return {}
    rows = (
        BlogEntryPage.objects.filter(pk__in=page_ids)
        .order_by()
        .exclude(authors__organization=None)
        .values("authors__organization")
        .annotate(result_count=Count("pk", distinct=True))
        .values_list("authors__organization", "result_count")
    )
    return {pk: count for pk, count in rows if pk is not None}


def _search_without_given_facet(request, site, query: str, active: ActiveFilters, facet: str) -> BaseSearchResults:
    """Full-text search with all active filters except ``facet``."""
    queryset = apply_active_filters(searchable_pages(request, site), site, active, exclude=facet)
    return queryset.search(query)


def compute_facet_result_counts(
    request,
    site,
    query: str,
    active: ActiveFilters,
    *,
    enabled_filters: dict[str, bool],
) -> dict[str, dict[int, int]]:
    """Compute sidebar result counts for each enabled facet value.

    Returns ``{facet_name: {object_pk: count}}``, for example::

        {
        "theme": {7: 12, 9: 3}, # "theme 7 (12)", "theme 9 (3)"
        "tag": ...
        }

    See ``faceted_search/result_counts.md`` for how the counts are computed, with examples.
    """
    counts: dict[str, dict[int, int]] = {}

    if enabled_filters.get("filter_by_category"):
        page_ids = _page_pks_from_search_results(_search_without_given_facet(request, site, query, active, "category"))
        counts["category"] = _counts_for_m2m_field(BlogEntryPage, page_ids, "blog_categories")

    if enabled_filters.get("filter_by_collection"):
        page_ids = _page_pks_from_search_results(
            _search_without_given_facet(request, site, query, active, "collection")
        )
        counts["collection"] = _counts_for_m2m_field(PublicationPage, page_ids, "collections")

    if enabled_filters.get("filter_by_theme"):
        page_ids = _page_pks_from_search_results(_search_without_given_facet(request, site, query, active, "theme"))
        counts["theme"] = _counts_for_m2m_field(PublicationPage, page_ids, "themes")

    if enabled_filters.get("filter_by_tag"):
        page_ids = _page_pks_from_search_results(_search_without_given_facet(request, site, query, active, "tag"))
        counts["tag"] = _counts_for_tags(page_ids)

    if enabled_filters.get("filter_by_author"):
        page_ids = _page_pks_from_search_results(_search_without_given_facet(request, site, query, active, "author"))
        counts["author"] = _counts_for_m2m_field(BlogEntryPage, page_ids, "authors")

    if enabled_filters.get("filter_by_source"):
        page_ids = _page_pks_from_search_results(_search_without_given_facet(request, site, query, active, "source"))
        counts["source"] = _counts_for_sources(page_ids)

    return counts


def _set_result_counts(items, counts_by_pk: dict[int, int]) -> None:
    """Set ``result_count`` on each item from ``counts_by_pk`` (0 if missing)."""
    for item in items:
        item.result_count = counts_by_pk.get(item.pk, 0)


def _drop_zeroes(items, *, selected=()) -> list:
    """Keep items with ``result_count > 0``, plus any currently selected values."""
    return [item for item in items if item.result_count > 0 or item in selected]


def _taxonomies_with_counts_or_selected(taxonomy_model, locale, counts_by_pk: dict[int, int], selected) -> list:
    """Taxonomies with a positive result count or currently selected (for tree building)."""
    selected_pks = {item.pk for item in selected}
    keep_pks = {pk for pk, count in counts_by_pk.items() if count > 0} | selected_pks
    taxonomies = list(taxonomy_model.objects.filter(locale=locale, id__in=keep_pks).order_by("name"))
    _set_result_counts(taxonomies, counts_by_pk)
    return taxonomies


def _attach_counts_to_tree(nodes, counts_by_pk: dict[int, int]) -> None:
    for node in nodes:
        _set_result_counts((node.taxonomy,), counts_by_pk)
        _attach_counts_to_tree(node.children, counts_by_pk)


def _taxonomy_filter_tree(
    taxonomy_model,
    locale,
    *,
    related_ids,
    counts_by_pk: dict[int, int] | None = None,
    selected=(),
) -> list[TaxonomyFilterNode]:
    """Build a collection/theme filter tree, optionally scoped by result counts."""
    if counts_by_pk is not None:
        taxonomies = _taxonomies_with_counts_or_selected(taxonomy_model, locale, counts_by_pk, selected)
        tree = _build_taxonomy_filter_tree(taxonomies, taxonomy_model, locale)
        _attach_counts_to_tree(tree, counts_by_pk)
        return tree
    taxonomies = taxonomy_model.objects.filter(locale=locale, id__in=related_ids).order_by("name")
    return _build_taxonomy_filter_tree(taxonomies, taxonomy_model, locale)


def _set_active_filter_result_counts(active: ActiveFilters, facet_counts: dict[str, dict[int, int]]) -> None:
    """Attach result counts to selected filter objects (sidebar chips)."""
    _set_result_counts(active.categories, facet_counts.get("category", {}))
    _set_result_counts(active.collections, facet_counts.get("collection", {}))
    _set_result_counts(active.themes, facet_counts.get("theme", {}))
    _set_result_counts(active.tags, facet_counts.get("tag", {}))
    _set_result_counts(active.sources, facet_counts.get("source", {}))
    _set_result_counts(active.authors, facet_counts.get("author", {}))


def get_filter_context(request, *, enabled_filters: dict[str, bool] | None = None, query: str | None = None) -> dict:
    """Build context for the filter sidebar.

    Always present
    --------------
    - ``filter_by_*``: ``bool`` for each enabled facet.
    - ``current_*``: ``list[T]`` for each selected facet value.
    - ``years``: ``list[str]`` selected via ``?year=`` (valid YYYY only).
      There is no year option list in the sidebar yet; years are only applied
      as active filters when present in the URL.
    - ``show_search_filters``: ``bool``, true when at least one enabled facet
      has options to display.

    Present only when the matching ``filter_by_*`` flag is true
    -----------------------------------------------------------
    - ``categories``: ``list[Category]`` (flat).
    - ``tags``: ``list[Tag]`` (flat).
    - ``authors``: ``list[Person]`` (flat).
    - ``sources``: ``list[Organization]`` (flat).
    - ``collection_tree``: ``list[TaxonomyFilterNode]`` (hierarchical).
    - ``theme_tree``: ``list[TaxonomyFilterNode]`` (hierarchical).

    When ``query`` is set (search page with ``?q=``)
    -----------------------------------------------
    Result counts are attached as ``result_count`` (``int``) on:

    - each item in ``categories`` / ``tags`` / ``authors`` / ``sources``;
    - each ``node.taxonomy`` in ``collection_tree`` / ``theme_tree``;
    - each object in the corresponding ``current_*`` lists (for selected chips).

    Unselected options with ``result_count == 0`` are omitted from the option
    lists/trees; selected values are kept. How counts are computed is described
    in ``faceted_search/result_counts.md``.

    When ``query`` is omitted, option lists are built from all live content
    under the site root (no ``result_count``, zeroes not filtered out).

    Example
    -------
    Request ``/search/?q=blé&theme=agriculture&author=42`` with only theme and
    author filters enabled::

        theme = Theme(name="Agriculture")
        theme.result_count = 12
        author = Person(name="Ada")
        author.result_count = 5

        {
            "filter_by_theme": True,
            "filter_by_author": True,
            "current_themes": [theme],    # theme.result_count == 12
            "current_authors": [author],  # author.result_count == 5
            "theme_tree": [
                TaxonomyFilterNode(taxonomy=theme, children=[]),
            ],
            "authors": [author],          # author.result_count == 5
            "show_search_filters": True,
            # …other filter_by_* / current_* keys omitted here for brevity
        }
    """
    if enabled_filters is None:
        enabled_filters = ENABLED_FILTERS

    site = Site.find_for_request(request)
    root = site.root_page.localized
    locale = root.locale
    # Includes PublicationPage entries (subclass of BlogEntryPage).
    blog_entries = BlogEntryPage.objects.descendant_of(root).live()
    content_pages = ContentPage.objects.descendant_of(root).live()
    publication_pages = PublicationPage.objects.descendant_of(root).live()
    active = get_active_filters_from_request_params(request, site)

    facet_counts: dict[str, dict[int, int]] = {}
    if query:
        facet_counts = compute_facet_result_counts(request, site, query, active, enabled_filters=enabled_filters)

    context = {
        **enabled_filters,
        "years": active.years,
    }

    if context["filter_by_category"]:
        category_ids = blog_entries.values_list("blog_categories", flat=True)
        categories = list(Category.objects.filter(id__in=category_ids, locale=locale).order_by("name"))
        if query:
            category_counts = facet_counts.get("category", {})
            _set_result_counts(categories, category_counts)
            categories = _drop_zeroes(categories, selected=active.categories)
        context["categories"] = categories

    if context["filter_by_tag"]:
        tag_ids = set(content_pages.values_list("tags", flat=True))
        tag_ids |= set(blog_entries.values_list("tags", flat=True))
        tag_ids.discard(None)
        tags = list(Tag.objects.filter(id__in=tag_ids).order_by("name"))
        if query:
            tag_counts = facet_counts.get("tag", {})
            _set_result_counts(tags, tag_counts)
            tags = _drop_zeroes(tags, selected=active.tags)
        context["tags"] = tags

    if context["filter_by_author"]:
        author_ids = blog_entries.values_list("authors", flat=True)
        authors = list(Person.objects.filter(id__in=author_ids).order_by("name"))
        if query:
            author_counts = facet_counts.get("author", {})
            _set_result_counts(authors, author_counts)
            authors = _drop_zeroes(authors, selected=active.authors)
        context["authors"] = authors

    if context["filter_by_source"]:
        org_ids = blog_entries.values_list("authors__organization", flat=True)
        sources = list(Organization.objects.filter(id__in=org_ids).order_by("name"))
        if query:
            source_counts = facet_counts.get("source", {})
            _set_result_counts(sources, source_counts)
            sources = _drop_zeroes(sources, selected=active.sources)
        context["sources"] = sources

    if context["filter_by_collection"]:
        context["collection_tree"] = _taxonomy_filter_tree(
            Collection,
            locale,
            related_ids=publication_pages.values_list("collections", flat=True),
            counts_by_pk=facet_counts.get("collection") if query else None,
            selected=active.collections,
        )

    if context["filter_by_theme"]:
        context["theme_tree"] = _taxonomy_filter_tree(
            Theme,
            locale,
            related_ids=publication_pages.values_list("themes", flat=True),
            counts_by_pk=facet_counts.get("theme") if query else None,
            selected=active.themes,
        )

    if query:
        _set_active_filter_result_counts(active, facet_counts)

    context["current_categories"] = active.categories
    context["current_collections"] = active.collections
    context["current_themes"] = active.themes
    context["current_tags"] = active.tags
    context["current_sources"] = active.sources
    context["current_authors"] = active.authors

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
