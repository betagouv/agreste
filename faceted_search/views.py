from django.views.generic import ListView
from wagtail.models import Page, Site

from faceted_search.filters import filter_queryset, get_filter_context


class FacetedSearchResultsView(ListView):
    """Search with sidebar filters (collection, theme, tag, etc.)."""

    model = Page
    template_name = "faceted_search/search_results.html"

    def get_searchable_queryset(self, site):
        root_page = site.root_page.localized
        queryset = Page.objects.descendant_of(root_page, inclusive=True).live()
        if not self.request.user.is_authenticated:
            queryset = queryset.public()
        return queryset

    def get_queryset(self):
        site = Site.find_for_request(self.request)
        query = self.request.GET.get("q", None)
        if not query:
            return Page.objects.none()

        object_list = self.get_searchable_queryset(site)
        object_list = filter_queryset(self.request, object_list, site)
        return object_list.search(query)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q")
        site = Site.find_for_request(self.request)
        context.update(get_filter_context(self.request, site))
        return context
