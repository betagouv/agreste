from django.views.generic import ListView
from wagtail.models import Page, Site

from faceted_search.facets import filter_queryset_for_facets, get_facet_context
from faceted_search.search import (
    RANK_BY_DATE,
    RANK_BY_RELEVANCE,
    get_rank_by_from_querystring,
    searchable_pages,
)


class FacetedSearchResultsView(ListView):
    """Search with sidebar facets (collection, theme, tag, etc.).

    Template context (in addition to Django ``ListView`` defaults such as
    ``object_list``, ``page_obj``, ``paginator``, ``is_paginated``, ``view``):

    - ``query``: raw ``?q=`` string (or ``None``).
    - ``rank_by``: ``relevance`` (default) or ``date``.
    - ``rank_by_relevance_url`` / ``rank_by_date_url``: same search with ranking swapped.
    - Everything returned by :func:`faceted_search.facets.get_facet_context`
      (see its docstring).

    For doc on how result counts are computed, see ``faceted_search/result_counts.md``.
    """

    model = Page
    template_name = "faceted_search/search_results.html"
    paginate_by = 10

    def get_queryset(self):
        site = Site.find_for_request(self.request)
        query = self.request.GET.get("q", None)
        if not query:
            return Page.objects.none()

        object_list = filter_queryset_for_facets(self.request, searchable_pages(self.request, site), site)
        if get_rank_by_from_querystring(self.request) == RANK_BY_DATE:
            # order_by_relevance=False is needed, from Wagtail docs.
            return object_list.order_by("-date").search(query, order_by_relevance=False)
        return object_list.search(query)

    def _rank_by_url(self, rank_by: str) -> str:
        params = self.request.GET.copy()
        params["rank_by"] = rank_by
        params.pop("page", None)  # reset to page 1 because results will change
        return f"?{params.urlencode()}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q")
        context["rank_by"] = get_rank_by_from_querystring(self.request)
        context["rank_by_relevance_url"] = self._rank_by_url(RANK_BY_RELEVANCE)
        context["rank_by_date_url"] = self._rank_by_url(RANK_BY_DATE)
        context.update(get_facet_context(self.request, query=context["query"]))
        return context
