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
        "post_field": "collections",
    },
    {
        "name": "theme",
        "post_field": "themes",
    },
    {
        "name": "tag",
        "post_field": "tags",
    },
]


class PublicationIndexPageFilterTestBase(BlogIndexPageFilterTestBase):
    index_page_class = PublicationIndexPage
    index_page_factory = PublicationIndexPageFactory
    entry_page_factory = PublicationPageFactory
    filter_cases = FILTER_CASES

    def setup_taxonomy_filter_fixtures(self):
        locale = self.index.locale
        self.collection = CollectionFactory(locale=locale)
        self.other_collection = CollectionFactory(locale=locale)
        self.theme = ThemeFactory(locale=locale)
        self.other_theme = ThemeFactory(locale=locale)

        self.post_with_collection = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            collections=[self.collection],
        )
        self.post_with_other_collection = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            collections=[self.other_collection],
        )
        self.post_with_theme = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            themes=[self.theme],
        )
        self.post_with_other_theme = self.entry_page_factory(
            parent=self.index,
            owner=self.admin,
            themes=[self.other_theme],
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
        collection_tag = f'<p class="fr-tag">{self.collection.name}</p>'
        theme_tag = f'<p class="fr-tag">{self.theme.name}</p>'
        soup = BeautifulSoup(response.content, "html.parser")
        matching_card = None
        for card in soup.select("div.fr-card"):
            tag_html = "".join(str(tag) for tag in card.select("p.fr-tag"))
            if post.title in card.get_text() and collection_tag in tag_html:
                matching_card = card
                break
        self.assertIsNotNone(
            matching_card,
            "Expected a post card containing the title and the collection tag.",
        )
        self.assertNotIn(theme_tag, "".join(str(tag) for tag in matching_card.select("p.fr-tag")))
