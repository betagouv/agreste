"""Faceted search filter tests.

Structured like ``publications.tests.test_publication_index_page``: shared filter
cases drive result filtering, sidebar visibility, and combination behaviour.

Blog-specific filters (e.g. category) are not covered here: this project uses
publications, not a standalone blog.
"""

from itertools import combinations
from urllib.parse import urlencode

from django.core.management import call_command
from django.urls import reverse
from wagtail.models import Site

from faceted_search.filters import ENABLED_FILTERS, get_active_filters_from_request_params, get_filter_context
from faceted_search.views import FacetedSearchResultsView
from publications.tests.test_publication_index_page import (
    FILTER_CASES,
    PublicationIndexPageFilterTestBase,
)
from sites_conformes.core.search_registry import get_search_results_view


def _all_filters_disabled() -> dict[str, bool]:
    return dict.fromkeys(ENABLED_FILTERS, False)


class FacetedSearchFilterTestBase(PublicationIndexPageFilterTestBase):
    filter_cases = FILTER_CASES
    search_query = "Post"

    def setUp(self):
        super().setUp()
        # Indexed for search but title does not match ``search_query`` ("Post").
        self.post_without_search_match = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            title="Annual Report",
            collections=[self.collection],
        )
        call_command("update_index")

    def search_url(self, query=None, **params):
        query = self.search_query if query is None else query
        url = reverse("cms_search")
        return f"{url}?{urlencode({'q': query, **params})}"


class FacetedSearchRegistrationTest(FacetedSearchFilterTestBase):
    def test_faceted_search_registers_its_view(self):
        self.assertIs(get_search_results_view().view_class, FacetedSearchResultsView)

    def test_search_uses_faceted_template(self):
        response = self.client.get(self.search_url())
        template_names = [template.name for template in response.templates]
        self.assertIn("faceted_search/search_results.html", template_names)


class FacetedSearchFilterContextTest(FacetedSearchFilterTestBase):
    """``get_filter_context`` builds sidebar lists according to ``enabled_filters``."""

    def _request_and_site(self):
        request = self.client.request().wsgi_request
        site = Site.objects.get(is_default_site=True)
        return request, site

    def test_enabled_filter_flags_populate_context_lists(self):
        request, site = self._request_and_site()

        for case in self.filter_cases:
            filter_name = case["name"]
            setting_field = f"filter_by_{filter_name}"
            context_list_key = f"{filter_name}s"
            expected_item = getattr(self, case.get("fixture", filter_name))
            enabled_flags = {**_all_filters_disabled(), setting_field: True}

            with self.subTest(filter_name):
                context = get_filter_context(request, site, enabled_filters=enabled_flags)
                self.assertTrue(context[setting_field])
                self.assertIn(expected_item, list(context[context_list_key]))

    def test_disabled_filter_flags_omit_context_lists(self):
        request, site = self._request_and_site()
        context = get_filter_context(request, site, enabled_filters=_all_filters_disabled())

        for case in self.filter_cases:
            filter_name = case["name"]
            setting_field = f"filter_by_{filter_name}"
            context_list_key = f"{filter_name}s"

            with self.subTest(filter_name):
                self.assertFalse(context[setting_field])
                self.assertNotIn(context_list_key, context)

    def test_show_search_filters_follows_enabled_flags(self):
        enabled_flags = {**_all_filters_disabled(), "filter_by_collection": True}
        context = get_filter_context(*self._request_and_site(), enabled_filters=enabled_flags)
        self.assertTrue(context["show_search_filters"])

        context = get_filter_context(*self._request_and_site(), enabled_filters=_all_filters_disabled())
        self.assertFalse(context["show_search_filters"])


class FacetedSearchFilterQueryTest(FacetedSearchFilterTestBase):
    """Full-text search combined with facet filters (``filter_before_search``)."""

    def test_filters_search_results(self):
        for case in self.filter_cases:
            filter_name = case["name"]
            fixture = getattr(self, case.get("fixture", filter_name))
            filter_url = self.search_url(**{filter_name: getattr(fixture, case["value_field"])})
            matching_post_title = getattr(self, case["matching_post"]).title
            other_post_title = getattr(self, case["other_post"]).title

            with self.subTest(filter_name):
                response = self.client.get(filter_url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, matching_post_title)
                self.assertNotContains(response, other_post_title)
                self.assertNotContains(response, self.post_without_search_match.title)

    def test_invalid_filter_value_returns_404(self):
        response = self.client.get(self.search_url(collection="nonexistent"))
        self.assertEqual(response.status_code, 404)


class FacetedSearchFilterCombinationTest(FacetedSearchFilterTestBase):
    def test_filters_combine(self):
        filter_cases = [case for case in self.filter_cases if case["name"] != "source"]
        for case_a, case_b in combinations(filter_cases, 2):
            filter_a = case_a["name"]
            filter_b = case_b["name"]

            fixture_a = getattr(self, case_a.get("fixture", filter_a))
            fixture_b = getattr(self, case_b.get("fixture", filter_b))
            search_params = {
                filter_a: getattr(fixture_a, case_a["value_field"]),
                filter_b: getattr(fixture_b, case_b["value_field"]),
            }

            post_kwargs = {}
            for field, fixture_names in case_a["matching_post_kwargs"].items():
                post_kwargs[field] = [getattr(self, fixture_name) for fixture_name in fixture_names]
            for field, fixture_names in case_b["matching_post_kwargs"].items():
                post_kwargs[field] = [getattr(self, fixture_name) for fixture_name in fixture_names]

            with self.subTest(f"{filter_a}+{filter_b}"):
                matching = self.entry_page_factory(parent=self.index, owner=self.admin, **post_kwargs)
                call_command("update_index")
                response = self.client.get(self.search_url(**search_params))
                self.assertContains(response, matching.title)
                for case in (case_a, case_b):
                    self.assertNotContains(response, getattr(self, case["matching_post"]).title)
                    self.assertNotContains(response, getattr(self, case["other_post"]).title)


class FacetedSearchGetActiveFiltersTest(FacetedSearchFilterTestBase):
    def test_get_active_filters_from_request_params(self):
        request = self.client.request().wsgi_request
        request.GET = request.GET.copy()
        request.GET["collection"] = self.collection.slug
        request.GET["tag"] = self.tag.slug
        site = Site.objects.get(is_default_site=True)
        active = get_active_filters_from_request_params(request, site)
        self.assertEqual(active.collection, self.collection)
        self.assertEqual(active.tag, self.tag)
