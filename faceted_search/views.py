from django.views.generic import ListView
from wagtail.models import Page, Site

from faceted_search.filters import filter_queryset, get_filter_context, searchable_pages


class FacetedSearchResultsView(ListView):
    """Search with sidebar filters (collection, theme, tag, etc.).

    Template context (in addition to Django ``ListView`` defaults such as
    ``object_list``, ``page_obj``, ``paginator``, ``is_paginated``, ``view``):

    - ``query``: raw ``?q=`` string (or ``None``).
    - Everything returned by :func:`faceted_search.filters.get_filter_context`
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

        object_list = filter_queryset(self.request, searchable_pages(self.request, site), site)
        return object_list.search(query)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q")
        context.update(get_filter_context(self.request, query=context["query"]))
        return context
