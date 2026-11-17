from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.utils.translation import gettext, override
from wagtail.documents import get_document_model

from publications.blocks.freeform_publication import FreeformPublicationBlock

Document = get_document_model()


class FreeformPublicationBlockTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.enterContext(override("fr"))
        self.document = Document.objects.create(
            title="Publication PDF",
            file=SimpleUploadedFile("my-publication.pdf", b"%PDF-1.4", content_type="application/pdf"),
        )

    def test_renders_content_and_downloadable_documents_in_two_columns(self):
        block = FreeformPublicationBlock()
        value = block.to_python(
            {
                "content": [("text", "<p>Free-form body.</p>")],
                "downloadable_documents": [
                    {
                        "download_type": "publication",
                        "document": self.document.pk,
                    }
                ],
            }
        )
        html = block.render(value, context={"request": RequestFactory().get("/")})
        soup = BeautifulSoup(html, "html.parser")
        first_column = soup.select_one(".fr-col-md-8")
        tiles = soup.select_one(".cmsfr-block-freeform-publication__tiles")

        self.assertIn("cmsfr-block-freeform-publication", html)
        self.assertIn("fr-col-md-4", html)
        self.assertIn("Free-form body.", first_column.get_text())
        self.assertNotIn("Free-form body.", tiles.get_text())
        self.assertIn("fr-tile--download", str(tiles))
        self.assertIn(gettext("Download publication"), tiles.get_text())
        self.assertIn("Publication PDF", tiles.get_text())
        self.assertIn(self.document.url, str(tiles))
