from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.utils.translation import gettext, override
from wagtail.documents import get_document_model

from publications.blocks.download_tile import DownloadTileBlock

Document = get_document_model()


@override("fr")
class DownloadTileBlockTestCase(TestCase):
    def _render_block(self, document, download_type="publication"):
        block = DownloadTileBlock()
        value = block.to_python({"download_type": download_type, "document": document.pk})
        return block.render(value, context={"request": RequestFactory().get("/")})

    def test_renders_download_publication_tile(self):
        document = Document.objects.create(
            title="Publication PDF",
            file=SimpleUploadedFile("my-publication.pdf", b"%PDF-1.4", content_type="application/pdf"),
        )

        html = self._render_block(document, download_type="publication")

        self.assertIn("fr-tile--download", html)
        self.assertIn(gettext("Download publication"), html)
        self.assertIn("Publication PDF", html)
        self.assertIn(document.url, html)

    def test_renders_download_data_tile(self):
        document = Document.objects.create(
            title="Dataset CSV",
            file=SimpleUploadedFile("dataset.csv", b"a,b,c", content_type="text/csv"),
        )

        html = self._render_block(document, download_type="data")

        self.assertIn("fr-tile--download", html)
        self.assertIn(gettext("Download data"), html)
        self.assertIn("Dataset CSV", html)
        self.assertIn(document.url, html)

    def test_renders_incomplete_tile_without_document(self):
        block = DownloadTileBlock()
        value = block.to_python({"download_type": "publication", "document": None})
        html = block.render(value, context={"request": RequestFactory().get("/")})

        self.assertIn(gettext("Download publication"), html)
        self.assertIn("fr-tile--download", html)
        self.assertIn('href="#"', html)
        document_placeholder = gettext("Your document will appear here")
        self.assertIn(document_placeholder, html)
        self.assertIn(f"<em>{document_placeholder}</em>", html)
