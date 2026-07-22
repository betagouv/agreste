"""Faceted search filter tests.

Structured like ``publications.tests.test_publication_index_page``: shared filter
cases drive result filtering, sidebar visibility, and combination behaviour.

Blog-specific filters (e.g. category) are not covered here: this project uses
publications, not a standalone blog.
"""

import zoneinfo
from datetime import datetime
from itertools import combinations
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from django.core.management import call_command
from django.http import Http404
from django.urls import reverse
from wagtail.models import Site

from faceted_search.filters import ENABLED_FILTERS, get_active_filters_from_request_params, get_filter_context
from faceted_search.views import FacetedSearchResultsView
from publications.tests.factories import CollectionFactory, ThemeFactory
from publications.tests.test_publication_index_page import PublicationIndexPageFilterTestBase
from sites_conformes.core.search_registry import get_search_results_view

FILTER_CASES = [
    {
        "name": "collection",
        "relation": "collections",
    },
    {
        "name": "theme",
        "relation": "themes",
    },
    {
        "name": "tag",
        "relation": "tags",
    },
]


def _all_filters_disabled() -> dict[str, bool]:
    return dict.fromkeys(ENABLED_FILTERS, False)


def get_post_titles_in_response(response) -> list[str]:
    return [
        link.get_text(strip=True)
        for link in BeautifulSoup(response.content, "html.parser").select("#search-results ol a")
    ]


class FacetedSearchFilterTestBase(PublicationIndexPageFilterTestBase):
    filter_cases = FILTER_CASES
    search_query = "Post"

    def setUp(self):
        super().setUp()
        call_command("update_index")

    def search_url(self, query=None, **params):
        query = self.search_query if query is None else query
        url = reverse("cms_search")
        return f"{url}?{urlencode({'q': query, **params}, doseq=True)}"


class FacetedSearchRegistrationTest(FacetedSearchFilterTestBase):
    def test_faceted_search_registers_its_view(self):
        self.assertIs(get_search_results_view().view_class, FacetedSearchResultsView)

    def test_search_uses_faceted_template(self):
        response = self.client.get(self.search_url())
        template_names = [template.name for template in response.templates]
        self.assertIn("faceted_search/search_results.html", template_names)


class FacetedSearchFilterContextTest(FacetedSearchFilterTestBase):
    """Test that``get_filter_context`` builds sidebar lists according to ``enabled_filters``."""

    def test_enabled_filter_flags_populate_context_lists(self):
        """Test that when a given filter is enabled, the context also has the filter activated,
        and it includes the taxonomy item for that filter."""
        request = self.client.request().wsgi_request
        site = Site.objects.get(is_default_site=True)

        def tree_nodes(tree):
            for node in tree:
                yield node.taxonomy
                yield from tree_nodes(node.children)

        for case in self.filter_cases:
            filter_name = case["name"]
            expected_item = getattr(self, filter_name)
            enabled_flags = {**_all_filters_disabled(), f"filter_by_{filter_name}": True}

            with self.subTest(filter_name):
                context = get_filter_context(request, site, enabled_filters=enabled_flags)
                self.assertTrue(context[f"filter_by_{filter_name}"])
                if filter_name in ("collection", "theme"):
                    self.assertIn(expected_item, list(tree_nodes(context[f"{filter_name}_tree"])))
                else:
                    self.assertIn(expected_item, list(context[f"{filter_name}s"]))

        with self.subTest("author"):
            enabled_flags = {**_all_filters_disabled(), "filter_by_author": True}
            context = get_filter_context(request, site, enabled_filters=enabled_flags)
            self.assertTrue(context["filter_by_author"])
            self.assertIn(self.author, list(context["authors"]))

        with self.subTest("source"):
            enabled_flags = {**_all_filters_disabled(), "filter_by_source": True}
            context = get_filter_context(request, site, enabled_filters=enabled_flags)
            self.assertTrue(context["filter_by_source"])
            self.assertIn(self.organization, list(context["sources"]))

    def test_collection_and_theme_filter_context_is_hierarchical(self):
        parent_collection = CollectionFactory(locale=self.index.locale, name="Parent collection")
        child_collection = CollectionFactory(
            locale=self.index.locale,
            name="Child collection",
            parent=parent_collection,
        )
        parent_theme = ThemeFactory(locale=self.index.locale, name="Parent theme")
        child_theme = ThemeFactory(locale=self.index.locale, name="Child theme", parent=parent_theme)
        self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            collections=[child_collection],
            themes=[child_theme],
        )
        request = self.client.request().wsgi_request
        site = Site.objects.get(is_default_site=True)
        context = get_filter_context(request, site)

        collection_parent = next(node for node in context["collection_tree"] if node.taxonomy == parent_collection)
        theme_parent = next(node for node in context["theme_tree"] if node.taxonomy == parent_theme)
        self.assertEqual([node.taxonomy for node in collection_parent.children], [child_collection])
        self.assertEqual([node.taxonomy for node in theme_parent.children], [child_theme])

    def test_disabled_filter_flags_omit_context_lists(self):
        request = self.client.request().wsgi_request
        site = Site.objects.get(is_default_site=True)
        context = get_filter_context(request, site, enabled_filters=_all_filters_disabled())

        for case in self.filter_cases:
            filter_name = case["name"]

            with self.subTest(filter_name):
                self.assertFalse(context[f"filter_by_{filter_name}"])
                self.assertNotIn(f"{filter_name}s", context)

        self.assertFalse(context["filter_by_author"])
        self.assertNotIn("authors", context)
        self.assertFalse(context["filter_by_source"])
        self.assertNotIn("sources", context)

    def test_show_search_filters_follows_enabled_flags(self):
        request = self.client.request().wsgi_request
        site = Site.objects.get(is_default_site=True)
        enabled_flags = {**_all_filters_disabled(), "filter_by_collection": True}
        context = get_filter_context(request, site, enabled_filters=enabled_flags)
        self.assertTrue(context["show_search_filters"])

        context = get_filter_context(request, site, enabled_filters=_all_filters_disabled())
        self.assertFalse(context["show_search_filters"])


class FacetedSearchFilterQueryTest(FacetedSearchFilterTestBase):
    """Full-text search combined with facet filters (``filter_before_search``).
    Posts should match the search query and the given filter. Other combinations should not match."""

    def test_single_filter_single_value(self):
        for case in self.filter_cases:
            filter_name = case["name"]
            taxonomy = getattr(self, filter_name)
            filtered_url = self.search_url(**{filter_name: taxonomy.slug})
            matching_post_title = getattr(self, f"post_with_{filter_name}").title
            other_post_title = getattr(self, f"post_with_other_{filter_name}").title

            with self.subTest(filter_name):
                post_without_search_match = self.entry_page_factory(
                    parent=self.index,
                    owner=self.admin,
                    title="Annual Report",
                    slug=f"annual-report-no-search-match-{filter_name}",
                    **{case["relation"]: [taxonomy]},
                )
                call_command("update_index")
                response = self.client.get(filtered_url)
                self.assertEqual(response.status_code, 200)
                post_titles = get_post_titles_in_response(response)
                self.assertIn(matching_post_title, post_titles)
                self.assertNotIn(other_post_title, post_titles)
                self.assertNotIn(post_without_search_match.title, post_titles)

    def test_single_filter_multiple_values(self):
        for case in self.filter_cases:
            filter_name = case["name"]
            taxonomy = getattr(self, filter_name)
            other_taxonomy = getattr(self, f"other_{filter_name}")

            with self.subTest(filter_name):
                post_without_search_match = self.entry_page_factory(
                    parent=self.index,
                    owner=self.admin,
                    title="Annual Report",
                    slug=f"annual-report-no-search-match-{filter_name}-multiple",
                    **{case["relation"]: [taxonomy, other_taxonomy]},
                )
                call_command("update_index")
                response = self.client.get(self.search_url(**{filter_name: [taxonomy.slug, other_taxonomy.slug]}))
                self.assertEqual(response.status_code, 200)
                post_titles = get_post_titles_in_response(response)
                self.assertIn(getattr(self, f"post_with_{filter_name}").title, post_titles)
                self.assertIn(getattr(self, f"post_with_other_{filter_name}").title, post_titles)
                self.assertNotIn(post_without_search_match.title, post_titles)

    def test_author_filter_single_value(self):
        post_without_search_match = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            title="Annual Report",
            slug="annual-report-no-search-match-author",
            authors=[self.author],
        )
        call_command("update_index")
        response = self.client.get(self.search_url(author=self.author.id))
        self.assertEqual(response.status_code, 200)
        post_titles = get_post_titles_in_response(response)
        self.assertIn(self.post_with_author.title, post_titles)
        self.assertNotIn(self.post_with_other_author.title, post_titles)
        self.assertNotIn(post_without_search_match.title, post_titles)

    def test_author_filter_multiple_values(self):
        response = self.client.get(self.search_url(author=[self.author.id, self.other_author.id]))
        self.assertEqual(response.status_code, 200)
        post_titles = get_post_titles_in_response(response)
        self.assertIn(self.post_with_author.title, post_titles)
        self.assertIn(self.post_with_other_author.title, post_titles)

    def test_source_filter_single_value(self):
        post_without_search_match = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            title="Annual Report",
            slug="annual-report-no-search-match-source",
            authors=[self.author],
        )
        call_command("update_index")
        response = self.client.get(self.search_url(source=self.organization.slug))
        self.assertEqual(response.status_code, 200)
        post_titles = get_post_titles_in_response(response)
        self.assertIn(self.post_with_author.title, post_titles)
        self.assertNotIn(self.post_with_other_author.title, post_titles)
        self.assertNotIn(post_without_search_match.title, post_titles)

    def test_source_filter_multiple_values(self):
        response = self.client.get(self.search_url(source=[self.organization.slug, self.other_organization.slug]))
        self.assertEqual(response.status_code, 200)
        post_titles = get_post_titles_in_response(response)
        self.assertIn(self.post_with_author.title, post_titles)
        self.assertIn(self.post_with_other_author.title, post_titles)

    def test_invalid_filter_value_returns_404(self):
        response = self.client.get(self.search_url(collection="nonexistent"))
        self.assertEqual(response.status_code, 404)

    def test_invalid_filter_multiple_values_returns_404(self):
        response = self.client.get(self.search_url(collection=[self.collection.slug, "nonexistent"]))
        self.assertEqual(response.status_code, 404)

    def test_invalid_author_id_returns_404(self):
        response = self.client.get(self.search_url(author="not-an-id"))
        self.assertEqual(response.status_code, 404)

    def test_invalid_year_is_ignored(self):
        response = self.client.get(self.search_url(year="not-a-year"))
        self.assertEqual(response.status_code, 200)
        post_titles = get_post_titles_in_response(response)
        self.assertIn(self.post_with_collection.title, post_titles)
        self.assertIn(self.post_with_theme.title, post_titles)

    def test_year_filter_filters_by_year(self):
        post_from_other_year = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            title="Post from 2023",
            slug="post-from-2023",
            date=datetime(2023, 1, 1, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Paris")),
        )
        call_command("update_index")
        response = self.client.get(self.search_url(year=2024))
        self.assertEqual(response.status_code, 200)
        post_titles = get_post_titles_in_response(response)
        self.assertIn(self.post_with_collection.title, post_titles)
        self.assertIn(self.post_with_theme.title, post_titles)
        self.assertNotIn(post_from_other_year.title, post_titles)

    def test_uses_OR_within_filter(self):
        """Test that multiple values within a single filter use OR semantics."""
        response = self.client.get(self.search_url(collection=[self.collection.slug, self.other_collection.slug]))
        self.assertEqual(response.status_code, 200)
        post_titles = get_post_titles_in_response(response)
        """Test that posts that match any of the values are included in the results."""
        self.assertIn(self.post_with_collection.title, post_titles)
        self.assertIn(self.post_with_other_collection.title, post_titles)

    def test_uses_AND_across_filters(self):
        """Test that multiple values across filters use AND semantics."""
        matching = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            collections=[self.collection],
            themes=[self.theme],
        )
        call_command("update_index")
        response = self.client.get(
            self.search_url(
                collection=[self.collection.slug, self.other_collection.slug],
                theme=[self.theme.slug, self.other_theme.slug],
            )
        )
        self.assertEqual(response.status_code, 200)
        post_titles = get_post_titles_in_response(response)
        self.assertIn(matching.title, post_titles)
        """Test that posts that match only one filter are not included in the results."""
        self.assertNotIn(self.post_with_collection.title, post_titles)
        self.assertNotIn(self.post_with_theme.title, post_titles)


class FacetedSearchFilterCombinationTest(FacetedSearchFilterTestBase):
    """Test that two filters can be combined in the search URL."""

    def test_two_filters_single_value(self):
        for case_a, case_b in combinations(self.filter_cases, 2):
            filter_a = case_a["name"]
            filter_b = case_b["name"]
            search_params = {
                filter_a: getattr(self, filter_a).slug,
                filter_b: getattr(self, filter_b).slug,
            }
            post_kwargs = {
                case_a["relation"]: [getattr(self, filter_a)],
                case_b["relation"]: [getattr(self, filter_b)],
            }

            with self.subTest(f"{filter_a}+{filter_b}"):
                matching = self.entry_page_factory(parent=self.index, owner=self.admin, **post_kwargs)
                post_without_search_match = self.entry_page_factory(
                    parent=self.index,
                    owner=self.admin,
                    title="Annual Report",
                    slug=f"annual-report-no-search-match-{filter_a}-{filter_b}",
                    **post_kwargs,
                )
                call_command("update_index")
                response = self.client.get(self.search_url(**search_params))
                post_titles = get_post_titles_in_response(response)
                self.assertIn(matching.title, post_titles)
                self.assertNotIn(post_without_search_match.title, post_titles)
                for case in (case_a, case_b):
                    """Test that posts that match only one filter are not included in the results."""
                    case_name = case["name"]
                    self.assertNotIn(getattr(self, f"post_with_{case_name}").title, post_titles)
                    self.assertNotIn(getattr(self, f"post_with_other_{case_name}").title, post_titles)

    def test_two_filters_multiple_values(self):
        # Example: filter_a="collection", values_a=[self.collection, self.other_collection],
        # filter_b="theme", values_b=[self.theme, self.other_theme].
        for case_a, case_b in combinations(self.filter_cases, 2):
            filter_a = case_a["name"]
            filter_b = case_b["name"]
            values_a = [getattr(self, filter_a), getattr(self, f"other_{filter_a}")]
            values_b = [getattr(self, filter_b), getattr(self, f"other_{filter_b}")]
            matching = self.entry_page_factory(
                parent=self.index,
                owner=self.admin,
                **{
                    case_a["relation"]: values_a,
                    case_b["relation"]: values_b,
                },
            )
            post_without_search_match = self.entry_page_factory(
                parent=self.index,
                owner=self.admin,
                title="Annual Report",
                slug=f"annual-report-no-search-match-{filter_a}-{filter_b}-multiple",
                **{
                    case_a["relation"]: values_a,
                    case_b["relation"]: values_b,
                },
            )
            call_command("update_index")
            response = self.client.get(
                self.search_url(
                    **{
                        filter_a: [taxonomy.slug for taxonomy in values_a],
                        filter_b: [taxonomy.slug for taxonomy in values_b],
                    }
                )
            )
            self.assertEqual(response.status_code, 200)
            post_titles = get_post_titles_in_response(response)
            self.assertIn(matching.title, post_titles)
            self.assertNotIn(post_without_search_match.title, post_titles)
            """ Test that posts that match only one filter are not included in the results."""
            self.assertNotIn(getattr(self, f"post_with_{filter_a}").title, post_titles)
            self.assertNotIn(getattr(self, f"post_with_other_{filter_a}").title, post_titles)
            self.assertNotIn(getattr(self, f"post_with_{filter_b}").title, post_titles)
            self.assertNotIn(getattr(self, f"post_with_other_{filter_b}").title, post_titles)


class FacetedSearchGetActiveFiltersTest(FacetedSearchFilterTestBase):
    def test_get_active_filters_from_request_params__single_value(self):
        request = self.client.request().wsgi_request
        request.GET = request.GET.copy()
        request.GET["collection"] = self.collection.slug
        request.GET["tag"] = self.tag.slug
        site = Site.objects.get(is_default_site=True)
        active = get_active_filters_from_request_params(request, site)
        self.assertEqual(active.collections, [self.collection])
        self.assertEqual(active.tags, [self.tag])

    def test_get_active_filters_from_request_params__multiple_values(self):
        request = self.client.request().wsgi_request
        request.GET = request.GET.copy()
        request.GET.setlist("collection", [self.collection.slug, self.other_collection.slug])
        site = Site.objects.get(is_default_site=True)
        active = get_active_filters_from_request_params(request, site)
        self.assertEqual(active.collections, [self.collection, self.other_collection])

    def test_get_active_filters_from_request_params__invalid_author_id_raises_404(self):
        request = self.client.request().wsgi_request
        request.GET = request.GET.copy()
        request.GET["author"] = "not-an-id"
        site = Site.objects.get(is_default_site=True)
        with self.assertRaises(Http404):
            get_active_filters_from_request_params(request, site)

    def test_get_active_filters_from_request_params__invalid_year_is_ignored(self):
        request = self.client.request().wsgi_request
        request.GET = request.GET.copy()
        request.GET.setlist("year", ["2024", "not-a-year", "23"])
        site = Site.objects.get(is_default_site=True)
        active = get_active_filters_from_request_params(request, site)
        self.assertEqual(active.years, ["2024"])
