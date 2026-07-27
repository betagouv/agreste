"""Tests for the faceted search results view."""

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from wagtail.models import Site

from faceted_search.tests.test_filters import FacetedSearchFilterTestBase
from faceted_search.views import FacetedSearchResultsView
from sites_conformes.core.tests.test_search import SearchResultsTestCase


class FacetedSearchResultsTestCase(SearchResultsTestCase):
    """Run the core search scenarios against the faceted search view.

    With filters disabled, FacetedSearchResultsView should behave the same as
    the core SearchResultsView.
    """


class FacetedSearchResultsViewTest(FacetedSearchFilterTestBase):
    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()

    def _build_view(self, query=None, user=None):
        request = self.factory.get("/search/", {"q": query} if query else {})
        request.user = user or AnonymousUser()
        request.site = Site.objects.get(is_default_site=True)
        view = FacetedSearchResultsView()
        view.request = request
        return view

    def test_get_context_data_includes_filter_context(self):
        view = self._build_view(query=self.search_query)
        view.object_list = view.get_queryset()
        context = view.get_context_data()
        self.assertIn("filter_by_collection", context)
        self.assertIn("collection_tree", context)
