from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils.translation import gettext
from wagtail.documents import get_document_model

from publications.blocks.download_tile import DOWNLOAD_TILE_BLOCK, DownloadTileBlock
from sites_conformes.core.models import ContentPage

Document = get_document_model()


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
        self.assertNotIn("fr-tile--download", html)


class DownloadTileBlockRegistrationTestCase(SimpleTestCase):
    def test_block_is_registered_on_content_page_body(self):
        block_names = ContentPage._meta.get_field("body").stream_block.child_blocks
        self.assertIn(DOWNLOAD_TILE_BLOCK, block_names)
        self.assertEqual(block_names[DOWNLOAD_TILE_BLOCK].meta.group, "Agreste")
