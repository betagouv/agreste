"""Tests for the faceted search results view."""

import zoneinfo
from datetime import datetime
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import reverse
from django.utils.translation import gettext
from wagtail.models import Page, Site
from wagtail.rich_text import RichText
from wagtail.test.utils import WagtailPageTestCase

from faceted_search.tests.test_facets import FacetedSearchTestBase, get_post_titles_in_response
from faceted_search.views import FacetedSearchResultsView
from publications.tests.factories import PublicationIndexPageFactory, PublicationPageFactory
from sites_conformes.core.models import ContentPage
from sites_conformes.core.tests.test_search import SearchResultsTestCase

PARIS_TZ = zoneinfo.ZoneInfo("Europe/Paris")


class FacetedSearchResultsTestCase(SearchResultsTestCase):
    """Run the core search scenarios against the faceted search view.

    With facets disabled, FacetedSearchResultsView should behave the same as
    the core SearchResultsView, except that an empty query lists dated posts
    instead of showing no results.
    """

    def test_search_no_query(self):
        index = PublicationIndexPageFactory(parent=self.home_page, owner=self.admin)
        post = PublicationPageFactory(
            parent=index,
            owner=self.admin,
            title="Published post without query",
            slug="published-post-without-query",
        )

        response = self.client.get(reverse("cms_search"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, post.title)
        self.assertContains(response, gettext("All results"))
        self.assertNotContains(response, "Page de contenu publique")
        self.assertNotContains(response, "Page de contenu privée")
        self.assertNotContains(response, "Page de contenu brouillon")

        soup = BeautifulSoup(response.content, "html.parser")
        selected = soup.select_one('select[name="rank_by"] option[selected]')
        self.assertIsNotNone(selected)
        self.assertEqual(selected["value"], "date")


class FacetedSearchResultsViewTest(FacetedSearchTestBase):
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

    def test_get_context_data_includes_facet_context(self):
        view = self._build_view(query=self.search_query)
        view.object_list = view.get_queryset()
        context = view.get_context_data()
        self.assertIn("enabled_facets", context)
        self.assertTrue(context["enabled_facets"]["collection"])
        self.assertIn("collection_tree", context)


class FacetedSearchPaginationTestBase(WagtailPageTestCase):
    """Minimal base for pagination tests: no taxonomy fixtures, just an index and posts."""

    search_query = "Post"

    @classmethod
    def setUpTestData(cls):
        cls.home = Page.objects.get(slug="home")
        cls.admin = get_user_model().objects.create_superuser("test", "test@test.test", "pass")
        cls.index = PublicationIndexPageFactory(parent=cls.home, owner=cls.admin)

    def search_url(self, query=None, **params):
        query = self.search_query if query is None else query
        return f"{reverse('cms_search')}?{urlencode({'q': query, **params}, doseq=True)}"


class FacetedSearchEmptyFacetTest(FacetedSearchPaginationTestBase):
    """Enabled facets stay in the sidebar even when they have no values."""

    def test_enabled_facets_render_when_empty(self):
        response = self.client.get(self.search_url())
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, "html.parser")
        empty_messages = {
            "filter-theme": gettext("No themes corresponding to this search"),
            "filter-collection": gettext("No collections corresponding to this search"),
        }
        for accordion_id, empty_message in empty_messages.items():
            with self.subTest(accordion_id=accordion_id):
                panel = soup.select_one(f"#{accordion_id}")
                self.assertIsNotNone(panel)
                self.assertIn(empty_message, panel.get_text())
                self.assertEqual(panel.select("input[type=checkbox]"), [])
        for disabled_id in ("filter-category", "filter-tag", "filter-author", "filter-source"):
            self.assertIsNone(soup.select_one(f"#{disabled_id}"))


class FacetedSearchPaginationTest(FacetedSearchPaginationTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for _ in range(15):
            PublicationPageFactory(parent=cls.index, owner=cls.admin)

    def test_pagination_first_page_is_limited_to_page_size(self):
        response = self.client.get(self.search_url())
        self.assertEqual(response.status_code, 200)
        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.paginator.per_page, 10)
        self.assertEqual(page_obj.paginator.count, 15)
        self.assertEqual(len(page_obj), 10)
        self.assertTrue(page_obj.has_next())

        soup = BeautifulSoup(response.content, "html.parser")
        result_items = soup.select("#search-results .agr-search-results > li")
        self.assertEqual(len(result_items), 10)

    def test_pagination_second_page_shows_remaining_results(self):
        response = self.client.get(self.search_url(page=2))
        self.assertEqual(response.status_code, 200)
        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.number, 2)
        self.assertEqual(page_obj.paginator.count, 15)
        self.assertEqual(len(page_obj), 5)
        self.assertFalse(page_obj.has_next())

        soup = BeautifulSoup(response.content, "html.parser")
        result_items = soup.select("#search-results .agr-search-results > li")
        self.assertEqual(len(result_items), 5)

    def test_pagination_widget_appears_when_multiple_pages(self):
        response = self.client.get(self.search_url())
        soup = BeautifulSoup(response.content, "html.parser")
        pagination_nav = soup.select_one("nav.fr-pagination")
        self.assertIsNotNone(pagination_nav)
        boost = pagination_nav.find_parent(attrs={"hx-boost": "true"})
        self.assertIsNotNone(boost)
        self.assertEqual(boost["hx-target"], "#faceted-search-swap")
        self.assertEqual(boost["hx-select"], "#faceted-search-swap")
        self.assertEqual(boost["hx-swap"], "outerHTML")
        self.assertEqual(boost["hx-push-url"], "true")

    def test_search_form_carries_no_page_control(self):
        """Submitting the form drops ``page``, so a new search starts at page 1."""
        response = self.client.get(self.search_url(page=2))
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form", id="faceted-search-form")
        self.assertIsNotNone(form)
        self.assertEqual(form.select('[name="page"]'), [])


class AccentInsensitiveSearchTest(FacetedSearchPaginationTestBase):
    """``blé`` and ``ble`` should return the same FTS hits under french_unaccent."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.wheat_page = PublicationPageFactory(
            parent=cls.index,
            owner=cls.admin,
            title="Culture du blé tendre",
            slug="culture-du-ble-tendre",
        )
        cls.other_page = PublicationPageFactory(
            parent=cls.index,
            owner=cls.admin,
            title="Rapport annuel",
            slug="rapport-annuel-unaccent",
        )

    def test_unaccented_query_matches_accented_title(self):
        response = self.client.get(self.search_url(query="ble"))
        titles = get_post_titles_in_response(response)
        self.assertIn(self.wheat_page.title, titles)
        self.assertNotIn(self.other_page.title, titles)

    def test_accented_and_unaccented_queries_return_the_same_results(self):
        accented = get_post_titles_in_response(self.client.get(self.search_url(query="blé")))
        unaccented = get_post_titles_in_response(self.client.get(self.search_url(query="ble")))
        self.assertEqual(accented, unaccented)
        self.assertIn(self.wheat_page.title, accented)


class FacetedSearchRankingTest(FacetedSearchPaginationTestBase):
    """Queryset ranking only (no full page render, to keep runtime down)."""

    search_query = "Report"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        body = [("paragraph", RichText("<p>Report content for search.</p>"))]
        cls.content_page = cls.home.add_child(
            instance=ContentPage(
                title="Report content page",
                body=body,
                slug="report-content-page",
                owner=cls.admin,
            )
        )
        cls.content_page.save_revision().publish()

        cls.older = PublicationPageFactory(
            parent=cls.index,
            owner=cls.admin,
            title="Older Report",
            slug="older-report",
            date=datetime(2020, 1, 1, 12, 0, 0, tzinfo=PARIS_TZ),
        )
        cls.newer = PublicationPageFactory(
            parent=cls.index,
            owner=cls.admin,
            title="Newer Report",
            slug="newer-report",
            date=datetime(2024, 6, 1, 12, 0, 0, tzinfo=PARIS_TZ),
        )

    def _result_titles(self, **params):
        request = RequestFactory().get("/search/", params)
        request.user = AnonymousUser()
        view = FacetedSearchResultsView()
        view.request = request
        view.kwargs = {}
        return [page.title for page in view.get_queryset()]

    def test_rank_by_date_excludes_content_pages_and_orders_by_date(self):
        self.assertIn(self.content_page.title, self._result_titles(q=self.search_query))
        self.assertIn(self.content_page.title, self._result_titles(q=self.search_query, rank_by="relevance"))
        self.assertEqual(
            self._result_titles(q=self.search_query, rank_by="date"), [self.newer.title, self.older.title]
        )

    def test_empty_query_defaults_to_date_ranking(self):
        self.assertEqual(self._result_titles(), [self.newer.title, self.older.title])
        self.assertEqual(self._result_titles(q=""), [self.newer.title, self.older.title])

    def test_empty_query_with_relevance_includes_content_pages(self):
        titles = self._result_titles(rank_by="relevance")
        self.assertIn(self.content_page.title, titles)
        self.assertIn(self.newer.title, titles)
        self.assertIn(self.older.title, titles)
