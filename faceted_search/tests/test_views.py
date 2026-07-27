"""Tests for the faceted search results view."""

from bs4 import BeautifulSoup
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
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
        view.kwargs = {}
        return view

    def test_get_context_data_includes_filter_context(self):
        view = self._build_view(query=self.search_query)
        view.object_list = view.get_queryset()
        context = view.get_context_data()
        self.assertIn("filter_by_collection", context)
        self.assertIn("collection_tree", context)


class FacetedSearchPaginationTest(FacetedSearchFilterTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for _ in range(30):
            cls.entry_page_factory(parent=cls.index, owner=cls.admin)
        call_command("update_index")

    def test_pagination_first_page_is_limited_to_page_size(self):
        response = self.client.get(self.search_url())
        self.assertEqual(response.status_code, 200)
        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.paginator.per_page, 25)
        self.assertGreater(page_obj.paginator.count, 25)
        self.assertEqual(len(page_obj), 25)
        self.assertTrue(page_obj.has_next())

        soup = BeautifulSoup(response.content, "html.parser")
        result_items = soup.select("#search-results ol > li")
        self.assertEqual(len(result_items), 25)

    def test_pagination_second_page_shows_remaining_results(self):
        response = self.client.get(self.search_url(page=2))
        self.assertEqual(response.status_code, 200)
        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.number, 2)
        self.assertEqual(len(page_obj), page_obj.paginator.count - 25)
        self.assertFalse(page_obj.has_next())

        soup = BeautifulSoup(response.content, "html.parser")
        result_items = soup.select("#search-results ol > li")
        self.assertEqual(len(result_items), page_obj.paginator.count - 25)

    def test_pagination_widget_appears_when_multiple_pages(self):
        response = self.client.get(self.search_url())
        soup = BeautifulSoup(response.content, "html.parser")
        pagination_nav = soup.select_one("nav.fr-pagination")
        self.assertIsNotNone(pagination_nav)

    def test_pagination_result_count_and_page_size_are_displayed(self):
        response = self.client.get(self.search_url())
        page_obj = response.context["page_obj"]
        soup = BeautifulSoup(response.content, "html.parser")
        paragraph = soup.select_one("#search-results > p.fr-text--sm")
        self.assertIsNotNone(paragraph)
        text = paragraph.get_text()
        self.assertIn(str(page_obj.paginator.count), text)
        self.assertIn("25", text)
        self.assertIn("résultats", text)
        self.assertIn("par page", text)

    def test_pagination_result_numbering_continues_across_pages(self):
        response = self.client.get(self.search_url(page=2))
        soup = BeautifulSoup(response.content, "html.parser")
        ol = soup.select_one("#search-results ol")
        self.assertIsNotNone(ol)
        self.assertEqual(int(ol["start"]), 26)
        self.assertIn("--list-start: 26", ol["style"])
