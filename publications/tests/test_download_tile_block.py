from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils.translation import gettext
from wagtail.documents import get_document_model

from publications.blocks.download_tile import DOWNLOAD_TILE_BLOCK, DownloadTileBlock
from sites_conformes.core.models import ContentPage

Document = get_document_model()


class DownloadTileBlockTestCase(TestCase):
    def test_renders_download_tile(self):
        document = Document.objects.create(
            title="Publication PDF",
            file=SimpleUploadedFile("my-publication.pdf", b"%PDF-1.4", content_type="application/pdf"),
        )

        block = DownloadTileBlock()
        value = block.to_python({"document": document.pk})
        html = block.render(value, context={"request": RequestFactory().get("/")})

        self.assertIn("fr-tile--download", html)
        self.assertIn(gettext("Download publication"), html)
        self.assertIn("Publication PDF", html)
        self.assertIn(document.url, html)


class DownloadTileBlockRegistrationTestCase(SimpleTestCase):
    def test_block_is_registered_on_content_page_body(self):
        block_names = ContentPage._meta.get_field("body").stream_block.child_blocks
        self.assertIn(DOWNLOAD_TILE_BLOCK, block_names)
        self.assertEqual(block_names[DOWNLOAD_TILE_BLOCK].meta.group, "Agreste")
