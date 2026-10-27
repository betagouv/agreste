from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.utils.translation import gettext, override
from wagtail.documents import get_document_model

from publications.blocks.standard_publication import StandardPublicationBlock

Document = get_document_model()


class StandardPublicationBlockTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.enterContext(override("fr"))
        self.document = Document.objects.create(
            title="Publication PDF",
            file=SimpleUploadedFile("my-publication.pdf", b"%PDF-1.4", content_type="application/pdf"),
        )

    def _render_block(self, **overrides):
        block = StandardPublicationBlock()
        value = block.to_python(
            {
                "subtitle": "Section title",
                "summary": "<p>Publication summary text.</p>",
                "downloadable_documents": [
                    {
                        "download_type": "publication",
                        "document": self.document.pk,
                    }
                ],
                **overrides,
            }
        )
        return block.render(value, context={"request": RequestFactory().get("/")})

    def test_renders_subtitle_summary_and_downloadable_documents_in_two_columns(self):
        html = self._render_block(
            presentation="<p>Presentation body.</p>",
            additional_information="<p>Additional information body.</p>",
            notes="<ul><li>Notes body.</li></ul>",
        )
        soup = BeautifulSoup(html, "html.parser")
        first_column = soup.select_one(".fr-col-md-8")
        tiles = soup.select_one(".cmsfr-block-standard-publication__tiles")

        self.assertIn("cmsfr-block-standard-publication", html)
        self.assertIn("fr-col-md-4", html)
        headings = [heading.get_text(strip=True) for heading in first_column.find_all("h2")]
        self.assertEqual(
            headings,
            [
                "Section title",
                gettext("Presentation"),
                gettext("Additional information"),
                gettext("Notes"),
            ],
        )
        column_text = first_column.get_text(" ", strip=True)
        self.assertIn("Publication summary text.", column_text)
        self.assertIn("Presentation body.", column_text)
        self.assertIn("Additional information body.", column_text)
        self.assertIsNotNone(first_column.find("ul"))
        self.assertIn("Notes body.", column_text)
        self.assertIn("fr-tile--download", str(tiles))
        self.assertIn(gettext("Download publication"), tiles.get_text())
        self.assertIn("Publication PDF", tiles.get_text())
        self.assertIn(self.document.url, str(tiles))
        self.assertNotIn("Presentation body.", tiles.get_text())

    def test_renders_without_subtitle_or_summary(self):
        html = self._render_block(subtitle="", summary="", notes='<p data-block-key="a"></p>')

        self.assertIn("cmsfr-block-standard-publication", html)
        self.assertNotIn("<h2>", html)
        self.assertNotIn("Publication summary text.", html)
        self.assertIn("fr-tile--download", html)
        self.assertIn("Publication PDF", html)
        self.assertIn(self.document.url, html)
