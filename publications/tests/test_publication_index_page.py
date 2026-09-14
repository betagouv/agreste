from bs4 import BeautifulSoup

from publications.models import PublicationIndexPage
from publications.tests.factories import (
    CollectionFactory,
    PublicationIndexPageFactory,
    PublicationPageFactory,
    ThemeFactory,
)
from sites_conformes.blog.tests.test_blog_index_page import (
    BlogIndexPageFilterQueryTest,
    BlogIndexPageFilterTestBase,
    BlogIndexPagePostsTest,
    BlogIndexPageSettingsTest,
)

FILTER_SETTINGS_DEFAULTS = {
    "filter_by_collection": True,
    "filter_by_theme": True,
    "filter_by_tag": True,
    "filter_by_author": False,
    "filter_by_source": False,
}

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


class PublicationIndexPageFilterTestBase(BlogIndexPageFilterTestBase):
    index_page_class = PublicationIndexPage
    index_page_factory = PublicationIndexPageFactory
    entry_page_factory = PublicationPageFactory
    filter_cases = FILTER_CASES

    @classmethod
    def setup_taxonomy_filter_fixtures(cls):
        locale = cls.index.locale
        cls.collection = CollectionFactory(locale=locale)
        cls.other_collection = CollectionFactory(locale=locale)
        cls.theme = ThemeFactory(locale=locale)
        cls.other_theme = ThemeFactory(locale=locale)

        cls.post_with_collection = cls.entry_page_factory(
            parent=cls.index,
            owner=cls.admin,
            collections=[cls.collection],
        )
        cls.post_with_other_collection = cls.entry_page_factory(
            parent=cls.index,
            owner=cls.admin,
            collections=[cls.other_collection],
        )
        cls.post_with_theme = cls.entry_page_factory(
            parent=cls.index,
            owner=cls.admin,
            themes=[cls.theme],
        )
        cls.post_with_other_theme = cls.entry_page_factory(
            parent=cls.index,
            owner=cls.admin,
            themes=[cls.other_theme],
        )


class PublicationIndexPageSettingsTest(PublicationIndexPageFilterTestBase, BlogIndexPageSettingsTest):
    filter_settings_defaults = FILTER_SETTINGS_DEFAULTS


class PublicationIndexPageFilterQueryTest(
    PublicationIndexPageFilterTestBase,
    BlogIndexPageFilterQueryTest,
):
    pass


class PublicationIndexPagePostsTest(
    PublicationIndexPageFilterTestBase,
    BlogIndexPagePostsTest,
):
    def test_posts_display_taxonomies_on_cards(self):
        # Themes are hidden on result cards (publication_index_posts_list.html) because
        # they are too verbose alongside collection tags.
        post = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            collections=[self.collection],
            themes=[self.theme],
        )
        response = self.client.get(self.index.url)  # no filters
        soup = BeautifulSoup(response.content, "html.parser")

        cards_with_title = [card for card in soup.select("div.fr-card") if post.title in card.get_text()]
        self.assertEqual(
            len(cards_with_title),
            1,
            f"Expected exactly one post card for title: {post.title!r}",
        )
        matching_card = cards_with_title[0]

        def card_contains_taxonomy_tag(card, tag_name: str) -> bool:
            """Look for any .fr-tag element with the expected taxonomy name."""
            return any(tag.get_text(strip=True) == tag_name for tag in card.select(".fr-tag"))

        self.assertTrue(
            card_contains_taxonomy_tag(matching_card, self.collection.name),
            "Expected the card to contain the collection tag.",
        )
        self.assertFalse(
            card_contains_taxonomy_tag(matching_card, self.theme.name),
            "Expected the card not to contain the theme tag.",
        )
