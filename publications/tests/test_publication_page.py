import zoneinfo
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase

from faceted_search.search import RANK_BY_DATE
from publications.models import Collection, PublicationIndexPage, PublicationPage, Theme

User = get_user_model()


class PublicationPageDisplayTest(WagtailPageTestCase):
    def setUp(self):
        self.home = Page.objects.get(slug="home")
        self.admin = User.objects.create_superuser("test", "test@test.test", "pass")
        self.admin.save()
        self.paris_tz = zoneinfo.ZoneInfo("Europe/Paris")

        self.index = self.home.add_child(
            instance=PublicationIndexPage(
                title="Publications",
                slug="publications-index",
                owner=self.admin,
            )
        )
        self.index.save_revision().publish()

        locale = self.index.locale
        self.collection = Collection.objects.create(
            name="Agriculture",
            slug="agriculture",
            locale=locale,
        )
        self.theme = Theme.objects.create(name="Climate", slug="climate", locale=locale)

        self.post = PublicationPage(
            title="Post with taxonomies",
            date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=self.paris_tz),
            owner=self.admin,
            disaron_id="PostTaxonomies1",
        )
        self.index.add_child(instance=self.post)
        self.post.collections.add(self.collection)
        self.post.themes.add(self.theme)
        self.post.save_revision().publish()

    def test_display_collections_and_themes(self):
        response = self.client.get(self.post.url)
        meta_paragraph = next(
            paragraph
            for paragraph in BeautifulSoup(response.content, "html.parser").select("div.fr-container p")
            if "Publié le" in paragraph.get_text()
        )
        collection_link = meta_paragraph.find("a", string=self.collection.name)
        theme_link = meta_paragraph.find("a", string=self.theme.name)
        self.assertIsNotNone(collection_link)
        self.assertIsNotNone(theme_link)
        self._assert_search_link(collection_link, collection=self.collection.slug)
        self._assert_search_link(theme_link, theme=self.theme.slug)

    def _assert_search_link(self, link, **expected_params):
        parsed = urlparse(link["href"])
        self.assertEqual(parsed.path, reverse("cms_search"))
        query = parse_qs(parsed.query)
        self.assertEqual(query.get("rank_by"), [RANK_BY_DATE])
        self.assertEqual(set(query) - {"rank_by"}, set(expected_params))
        for key, value in expected_params.items():
            self.assertEqual(query[key], [value])

    def test_clean_strips_disaron_id_and_rejects_blank(self):
        self.post.disaron_id = "  TbdCpr2602  "
        self.post.clean()
        self.assertEqual(self.post.disaron_id, "TbdCpr2602")

        self.post.disaron_id = "   "
        with self.assertRaises(ValidationError) as caught:
            self.post.clean()
        self.assertIn("disaron_id", caught.exception.error_dict)
