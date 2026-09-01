from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.utils.translation import gettext, override
from wagtail.documents import get_document_model

from publications.blocks.standard_publication import StandardPublicationBlock

Document = get_document_model()


@override("fr")
class StandardPublicationBlockTestCase(TestCase):
    def setUp(self):
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
                        "document": self.document,
                    }
                ],
                **overrides,
            }
        )
        return block.render(value, context={"request": RequestFactory().get("/")})

    def test_renders_subtitle_summary_and_downloadable_documents_in_two_columns(self):
        html = self._render_block()

        self.assertIn("cmsfr-block-standard-publication", html)
        self.assertIn("fr-col-md-8", html)
        self.assertIn("fr-col-md-4", html)
        self.assertIn("<h2>Section title</h2>", html)
        self.assertIn("Publication summary text.", html)
        self.assertIn("fr-tile--download", html)
        self.assertIn(gettext("Download publication"), html)
        self.assertIn("Publication PDF", html)
        self.assertIn(self.document.url, html)
