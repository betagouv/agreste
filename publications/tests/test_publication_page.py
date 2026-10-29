import zoneinfo
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from wagtail.models import Page
from wagtail.rich_text import RichText
from wagtail.test.utils import WagtailPageTestCase

from faceted_search.search import RANK_BY_DATE
from publications.models import (
    Collection,
    GeographicLevel,
    PublicationIndexPage,
    PublicationPage,
    ReferenceYear,
    StatisticalSource,
    Theme,
)

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
        self.parent_collection = Collection.objects.create(name="Crops", slug="crops", locale=locale)
        self.child_collection = Collection.objects.create(
            name="Wheat",
            slug="wheat",
            locale=locale,
            parent=self.parent_collection,
        )
        self.theme = Theme.objects.create(name="Climate", slug="climate", locale=locale)
        self.statistical_source = StatisticalSource.objects.create(
            name="SSP",
            slug="ssp",
            locale=locale,
            colophon=[("paragraph", RichText("<p>Statistical source colophon.</p>"))],
        )
        self.reference_year = ReferenceYear.objects.create(name="2024", slug="2024", locale=locale)
        self.geographic_level = GeographicLevel.objects.create(name="National", slug="national", locale=locale)

        self.post = PublicationPage(
            title="Post with taxonomies",
            date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=self.paris_tz),
            owner=self.admin,
            disaron_id="PostTaxonomies1",
        )
        self.index.add_child(instance=self.post)
        self.post.collections.add(self.collection, self.parent_collection, self.child_collection)
        self.post.themes.add(self.theme)
        self.post.statistical_sources.add(self.statistical_source)
        self.post.reference_years.add(self.reference_year)
        self.post.geographic_levels.add(self.geographic_level)
        self.post.save_revision().publish()

    def test_display_metadata(self):
        response = self.client.get(self.post.url)
        html = response.content.decode()
        soup = BeautifulSoup(html, "html.parser")
        meta_paragraph = next(
            paragraph for paragraph in soup.select("div.fr-container p") if "Publié le" in paragraph.get_text()
        )
        collection_link = meta_paragraph.find("a", string=self.collection.name)
        self.assertIsNotNone(collection_link)
        self.assertIsNone(meta_paragraph.find("a", string=self.theme.name))
        self._assert_search_link(collection_link, collection=self.collection.slug)
        self.assertIn(f"{self.parent_collection.name} > {self.child_collection.name}", meta_paragraph.get_text())
        parent_links = meta_paragraph.find_all("a", string=self.parent_collection.name)
        self.assertEqual(len(parent_links), 1)
        self._assert_search_link(parent_links[0], collection=self.parent_collection.slug)
        child_link = meta_paragraph.find("a", string=self.child_collection.name)
        self._assert_search_link(child_link, collection=self.child_collection.slug)

        theme_link = soup.select_one("a.fr-tag")
        self.assertEqual(theme_link.get_text(strip=True), self.theme.name)
        self._assert_search_link(theme_link, theme=self.theme.slug)
        self.assertLess(html.find("Publié le"), html.find(self.theme.name))

        labeled_values = {
            "Sources statistiques": self.statistical_source.name,
            "Années de référence": self.reference_year.name,
            "Niveaux géographiques": self.geographic_level.name,
        }
        self.assertLess(html.find(self.theme.name), html.find("Sources statistiques"))
        metadata = soup.find("dl", class_="publication-page__metadata")
        for label, value in labeled_values.items():
            term = metadata.find("dt", string=label)
            description = term.find_next_sibling("dd")
            self.assertEqual(description.get_text(strip=True), value)
            self.assertIsNone(description.find("a"))
        self.assertIn("Statistical source colophon.", html)

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
