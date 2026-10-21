from datetime import date
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.translation import gettext
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase

from publications.models import Collection, Theme
from sites_conformes.core.models import ContentPage

User = get_user_model()


class SearchLinkTypeTest(WagtailPageTestCase):
    def setUp(self):
        self.home = Page.objects.get(slug="home")
        self.admin = User.objects.create_superuser("test", "test@test.test", "pass")
        self.page = self.home.add_child(
            instance=ContentPage(
                title="Search links",
                slug="search-links",
                owner=self.admin,
            )
        )
        locale = self.page.locale
        self.collection = Collection.objects.create(name="Agriculture", slug="agriculture", locale=locale)
        self.theme = Theme.objects.create(name="Climate", slug="climate", locale=locale)
        self.body = ContentPage._meta.get_field("body").stream_block
        self.tile_link = self.body.child_blocks["tile"].child_blocks["link"]
        self.button = self.body.child_blocks["buttons_list"].child_blocks["buttons"].child_blocks["button"]

    def test_tile_and_button_offer_search_results(self):
        for link_block in (self.tile_link, self.button):
            with self.subTest(link_block=link_block.name):
                choices = dict(link_block.child_blocks["link_type"]._constructor_kwargs["choices"])
                self.assertEqual(str(choices["search"]), gettext("Search results"))
                self.assertIn("search", link_block.link_types)

    def test_url_includes_only_the_selected_search_parameters(self):
        value = self.tile_link.to_python(
            {
                "link_type": "search",
                "q": "blé",
                "collection": self.collection.pk,
                "theme": self.theme.pk,
                "date_from": "2024-01-01",
                "date_to": "2024-06-30",
                "rank_by": "date",
            }
        )

        parsed = urlparse(value.url())
        self.assertEqual(parsed.path, reverse("cms_search"))
        self.assertEqual(
            parse_qs(parsed.query),
            {
                "q": ["blé"],
                "collection": [self.collection.slug],
                "theme": [self.theme.slug],
                "date_from": ["2024-01-01"],
                "date_to": ["2024-06-30"],
                "rank_by": ["date"],
            },
        )
        self.assertEqual(value["date_from"], date(2024, 1, 1))

    def test_url_omits_empty_rank_by(self):
        value = self.tile_link.to_python({"link_type": "search", "q": "report"})
        self.assertEqual(parse_qs(urlparse(value.url()).query), {"q": ["report"]})

    def test_rendered_tile_and_button_link_to_search(self):
        self.page.body = self.body.to_python(
            [
                {
                    "type": "tile",
                    "value": {
                        "title": "Climate tile",
                        "link": {"link_type": "search", "theme": self.theme.pk},
                    },
                },
                {
                    "type": "buttons_list",
                    "value": {
                        "buttons": [
                            {
                                "type": "button",
                                "value": {
                                    "link_type": "search",
                                    "text": "See results",
                                    "q": "report",
                                },
                            }
                        ]
                    },
                },
            ]
        )
        self.page.save_revision().publish()

        soup = BeautifulSoup(self.client.get(self.page.url).content, "html.parser")
        tile_link = soup.select_one(".fr-tile__title a")
        button_link = soup.find("a", string="See results")
        self.assertIsNotNone(tile_link)
        self.assertIsNotNone(button_link)
        self.assertIn("Climate tile", tile_link.get_text())
        self.assertIn("See results", button_link.get_text())

        tile_query = parse_qs(urlparse(tile_link["href"]).query)
        button_query = parse_qs(urlparse(button_link["href"]).query)
        self.assertEqual(urlparse(tile_link["href"]).path, reverse("cms_search"))
        self.assertEqual(tile_query, {"theme": [self.theme.slug]})
        self.assertEqual(urlparse(button_link["href"]).path, reverse("cms_search"))
        self.assertEqual(button_query, {"q": ["report"]})
        self.assertNotIn("target", tile_link.attrs)
        self.assertNotIn("target", button_link.attrs)

    def test_clean_drops_search_fields_for_a_page_link(self):
        value = self.button.to_python(
            {
                "link_type": "page",
                "page": self.page.pk,
                "q": "report",
                "collection": self.collection.pk,
                "theme": self.theme.pk,
                "date_from": "2024-01-01",
                "rank_by": "date",
            }
        )
        cleaned = self.button.clean(value)
        self.assertEqual(cleaned["page"].pk, self.page.pk)
        self.assertEqual(cleaned["q"], "")
        self.assertIsNone(cleaned["collection"])
        self.assertIsNone(cleaned["theme"])
        self.assertIsNone(cleaned["date_from"])
        self.assertEqual(cleaned["rank_by"], "")

    def test_clean_drops_page_anchor_and_query_string_for_search(self):
        value = self.tile_link.to_python(
            {
                "link_type": "search",
                "page": self.page.pk,
                "anchor": "intro",
                "query_string": "?tag=news",
                "q": "report",
            }
        )
        cleaned = self.tile_link.clean(value)
        self.assertIsNone(cleaned["page"])
        self.assertEqual(cleaned["anchor"], "")
        self.assertEqual(cleaned["query_string"], "")
        self.assertEqual(cleaned["q"], "report")
