"""Blog index page tests.

The tests are structured to allow easier future transition from single Categories to multiple Taxonomies.
The test classes are structured so that page types with multiple taxonomies can reuse them by subclassing.
Taxonomy-specific elements are overridden in subclasses (see publications tests in https://github.com/betagouv/agreste).
"""

from itertools import combinations

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.utils.translation import gettext
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase

from sites_conformes.blog.models import BlogIndexPage
from sites_conformes.blog.tests.factories import (
    BlogEntryPageFactory,
    BlogIndexPageFactory,
    CategoryFactory,
    OrganizationFactory,
    PersonFactory,
    TagFactory,
)

User = get_user_model()

# BlogIndexPage filter toggles: category and tag default on; author and source default off.
FILTER_SETTINGS_DEFAULTS = {
    "filter_by_category": True,
    "filter_by_tag": True,
    "filter_by_author": False,
    "filter_by_source": False,
}

TAXONOMY_FILTER_CASES = [
    {
        "name": "category",
        "value_field": "slug",
        "matching_post_kwargs": {"blog_categories": ["category"]},
        "matching_post": "post_with_category",
        "other_post": "post_with_other_category",
    },
]

SHARED_FILTER_CASES = [
    {
        "name": "tag",
        "value_field": "slug",
        "matching_post_kwargs": {"tags": ["tag"]},
        "matching_post": "post_with_tag",
        "other_post": "post_with_other_tag",
    },
    {
        "name": "author",
        "value_field": "id",
        "matching_post_kwargs": {"authors": ["author"]},
        "matching_post": "post_with_author",
        "other_post": "post_with_other_author",
    },
    {
        "name": "source",
        "fixture": "organization",
        "value_field": "slug",
        # You can't assign a source to a post directly, so we assign an author associated to the source.
        "matching_post_kwargs": {"authors": ["author"]},
        "matching_post": "post_with_author",
        "other_post": "post_with_other_author",
    },
]

FILTER_CASES = TAXONOMY_FILTER_CASES + SHARED_FILTER_CASES


class BlogIndexPageFilterTestBase(WagtailPageTestCase):
    index_page_class = BlogIndexPage
    index_page_factory = BlogIndexPageFactory
    entry_page_factory = BlogEntryPageFactory
    filter_cases = FILTER_CASES

    def setUp(self):
        self.home = Page.objects.get(slug="home")
        self.admin = User.objects.create_superuser("test", "test@test.test", "pass")
        self.admin.save()

        self.index = self.index_page_factory(parent=self.home, owner=self.admin)

        self.setup_filter_fixtures()
        self.setup_taxonomy_filter_fixtures()

    def setup_filter_fixtures(self):
        self.tag = TagFactory()
        self.other_tag = TagFactory()
        self.organization = OrganizationFactory()
        self.other_organization = OrganizationFactory()
        self.author = PersonFactory(organization=self.organization)
        self.other_author = PersonFactory(organization=self.other_organization)

        self.post_with_tag = self.entry_page_factory(parent=self.index, owner=self.admin, tags=[self.tag])
        self.post_with_other_tag = self.entry_page_factory(parent=self.index, owner=self.admin, tags=[self.other_tag])
        self.post_with_author = self.entry_page_factory(parent=self.index, owner=self.admin, authors=[self.author])
        self.post_with_other_author = self.entry_page_factory(
            parent=self.index, owner=self.admin, authors=[self.other_author]
        )

    def setup_taxonomy_filter_fixtures(self):
        locale = self.index.locale
        self.category = CategoryFactory(locale=locale)
        self.other_category = CategoryFactory(locale=locale)

        self.post_with_category = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            blog_categories=[self.category],
        )
        self.post_with_other_category = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            blog_categories=[self.other_category],
        )

    def _set_filter_settings(self, **settings):
        for field, value in settings.items():
            setattr(self.index, field, value)
        self.index.save_revision().publish()


class BlogIndexPageSettingsTest(BlogIndexPageFilterTestBase):
    """Test the "Show filters" panel in the page settings, and that it shows/hides filters in
    the left sidebar of the page."""

    filter_settings_defaults = FILTER_SETTINGS_DEFAULTS

    def test_settings_show_filters_panel_includes_all_fields(self):
        def list_settings_in_panel(panels):
            names = []
            for panel in panels:
                if hasattr(panel, "field_name"):
                    names.append(panel.field_name)
                if hasattr(panel, "children"):
                    names.extend(list_settings_in_panel(panel.children))
            return names

        field_names = list_settings_in_panel(self.index_page_class.settings_panels)
        for field_name in self.filter_settings_defaults:
            self.assertIn(field_name, field_names)

    def test_filter_settings_default_values(self):
        page = self.index_page_factory(parent=self.home, title="Defaults", slug="defaults", publish=False)
        for field_name, expected_default in self.filter_settings_defaults.items():
            self.assertEqual(getattr(page, field_name), expected_default, field_name)

    def test_filter_shown_when_enabled(self):
        for case in self.filter_cases:
            filter_name = case["name"]
            setting_field = f"filter_by_{filter_name}"
            sidebar_heading = gettext(f"Filter by {filter_name}")
            fixture = getattr(self, case.get("fixture", filter_name))
            visible_label = fixture.name

            with self.subTest(filter_name):
                self._set_filter_settings(**{setting_field: True})
                response = self.client.get(self.index.url)
                self.assertContains(response, sidebar_heading)
                self.assertContains(response, visible_label)

    def test_filter_hidden_when_disabled(self):
        for case in self.filter_cases:
            filter_name = case["name"]
            setting_field = f"filter_by_{filter_name}"
            sidebar_heading = gettext(f"Filter by {filter_name}")

            with self.subTest(filter_name):
                self._set_filter_settings(**{setting_field: False})
                response = self.client.get(self.index.url)
                self.assertNotContains(response, sidebar_heading)


class BlogIndexPageFilterQueryTest(BlogIndexPageFilterTestBase):
    """Test the filtering of the posts on the index page."""

    def test_filters_posts(self):
        for case in self.filter_cases:
            filter_name = case["name"]
            fixture = getattr(self, case.get("fixture", filter_name))
            param_value = getattr(fixture, case["value_field"])
            filter_url = f"{self.index.url}?{filter_name}={param_value}"
            matching_post_title = getattr(self, case["matching_post"]).title
            other_post_title = getattr(self, case["other_post"]).title

            with self.subTest(filter_name):
                response = self.client.get(filter_url)
                self.assertContains(response, matching_post_title)
                self.assertNotContains(response, other_post_title)

    def test_url_filter_applies_even_when_filter_disabled_in_settings(self):
        """
        Disabling a filter hides its sidemenu block, but passing it in the URL still filters the posts.
        """
        for case in self.filter_cases:
            filter_name = case["name"]
            setting_field = f"filter_by_{filter_name}"
            sidebar_heading = gettext(f"Filter by {filter_name}")
            fixture = getattr(self, case.get("fixture", filter_name))
            param_value = getattr(fixture, case["value_field"])
            filter_url = f"{self.index.url}?{filter_name}={param_value}"
            matching_post_title = getattr(self, case["matching_post"]).title
            other_post_title = getattr(self, case["other_post"]).title

            with self.subTest(filter_name):
                self._set_filter_settings(**{setting_field: False})
                response = self.client.get(filter_url)
                self.assertNotContains(response, sidebar_heading)
                self.assertContains(response, matching_post_title)
                self.assertNotContains(response, other_post_title)

    def test_filters_posts_with_two_query_params(self):
        """Tests pairs of filters, to check that they interact correctly."""
        # Source interacts with author in fixtures; skip it for pairwise tests.
        filter_cases = [case for case in self.filter_cases if case["name"] != "source"]
        for case_a, case_b in combinations(filter_cases, 2):
            filter_a = case_a["name"]
            filter_b = case_b["name"]

            fixture_a = getattr(self, case_a.get("fixture", filter_a))
            fixture_b = getattr(self, case_b.get("fixture", filter_b))
            query_param_a = f"{filter_a}={getattr(fixture_a, case_a['value_field'])}"
            query_param_b = f"{filter_b}={getattr(fixture_b, case_b['value_field'])}"
            query = f"{self.index.url}?{query_param_a}&{query_param_b}"

            post_kwargs = {}
            for field, fixture_names in case_a["matching_post_kwargs"].items():
                post_kwargs[field] = [getattr(self, fixture_name) for fixture_name in fixture_names]
            for field, fixture_names in case_b["matching_post_kwargs"].items():
                post_kwargs[field] = [getattr(self, fixture_name) for fixture_name in fixture_names]

            with self.subTest(f"{filter_a}+{filter_b}"):
                matching = self.entry_page_factory(parent=self.index, owner=self.admin, **post_kwargs)
                response = self.client.get(query)
                self.assertContains(response, matching.title)
                for case in (case_a, case_b):
                    self.assertNotContains(response, getattr(self, case["matching_post"]).title)
                    self.assertNotContains(response, getattr(self, case["other_post"]).title)


class BlogIndexPagePostsTest(BlogIndexPageFilterTestBase):
    """Test the display of the post list on the index page."""

    def test_posts_display_taxonomies_on_cards(self):
        post = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            blog_categories=[self.category],
        )
        response = self.client.get(self.index.url)  # no filters
        category_tag = f'<p class="fr-tag">{self.category.name}</p>'
        soup = BeautifulSoup(response.content, "html.parser")
        matching_card = None
        for card in soup.select("div.fr-card"):
            tag_html = "".join(str(tag) for tag in card.select("p.fr-tag"))
            if post.title in card.get_text() and category_tag in tag_html:
                matching_card = card
                break
        self.assertIsNotNone(
            matching_card,
            "Expected a post card containing the title and the category tag.",
        )
