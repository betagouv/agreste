from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.utils.translation import gettext
from wagtail.documents import get_document_model
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase

from publications.blocks.downloadable_document import DOWNLOADABLE_DOCUMENT_BLOCK
from publications.blocks.publication_subtitle import PUBLICATION_SUBTITLE_BLOCK
from publications.blocks.publication_summary import PUBLICATION_SUMMARY_BLOCK
from publications.blocks.recent_entries import PUBLICATION_RECENT_ENTRIES_BLOCK
from publications.blocks.register_sites_conformes_blocks import BLOG_RECENT_ENTRIES_BLOCK
from publications.blocks.standard_publication import STANDARD_PUBLICATION_BLOCK
from publications.models import PublicationIndexPage
from sites_conformes.core.models import ContentPage

User = get_user_model()
Document = get_document_model()


class PublicationsBlockRegistrationTestCase(SimpleTestCase):
    """Publications blocks are injected at startup wherever blog_recent_entries exists."""

    def test_blocks_are_registered_on_content_page_body(self):
        child_blocks = ContentPage._meta.get_field("body").stream_block.child_blocks
        blog_group = child_blocks[BLOG_RECENT_ENTRIES_BLOCK].meta.group

        self.assertIn(PUBLICATION_RECENT_ENTRIES_BLOCK, child_blocks)
        self.assertEqual(child_blocks[PUBLICATION_RECENT_ENTRIES_BLOCK].meta.group, blog_group)

        self.assertIn(DOWNLOADABLE_DOCUMENT_BLOCK, child_blocks)
        self.assertEqual(child_blocks[DOWNLOADABLE_DOCUMENT_BLOCK].meta.group, "Agreste")

        self.assertIn(PUBLICATION_SUBTITLE_BLOCK, child_blocks)
        self.assertEqual(child_blocks[PUBLICATION_SUBTITLE_BLOCK].meta.group, "Agreste")

        self.assertIn(PUBLICATION_SUMMARY_BLOCK, child_blocks)
        self.assertEqual(child_blocks[PUBLICATION_SUMMARY_BLOCK].meta.group, "Agreste")

        self.assertIn(STANDARD_PUBLICATION_BLOCK, child_blocks)
        self.assertEqual(child_blocks[STANDARD_PUBLICATION_BLOCK].meta.group, "Agreste")


class PublicationsBlockAvailabilityTestCase(WagtailPageTestCase):
    """Blocks are available in nested streams, not only at the top level of body."""

    NESTED_STREAM_PATHS = (
        ("multicolumn column", ("multicolumns", "columns", "column", "content")),
        ("item grid", ("item_grid", "items")),
    )

    def setUp(self):
        self.home = Page.objects.get(slug="home")
        self.admin = User.objects.create_superuser("test", "test@test.test", "pass")
        self.index_page = self.home.add_child(
            instance=PublicationIndexPage(title="Publications", slug="publications-availability"),
        )
        self.document = Document.objects.create(
            title="Nested publication PDF",
            file=SimpleUploadedFile("nested.pdf", b"%PDF-1.4", content_type="application/pdf"),
        )

    def _body_stream_block(self):
        return ContentPage._meta.get_field("body").stream_block

    def _stream_block_at(self, *path):
        block = self._body_stream_block()
        for segment in path:
            block = block.child_blocks[segment]
        return block

    def _assert_blocks_registered_in_stream(self, *path):
        stream_block = self._body_stream_block() if not path else self._stream_block_at(*path)
        self.assertIn(PUBLICATION_RECENT_ENTRIES_BLOCK, stream_block.child_blocks)
        self.assertIn(DOWNLOADABLE_DOCUMENT_BLOCK, stream_block.child_blocks)
        self.assertIn(PUBLICATION_SUBTITLE_BLOCK, stream_block.child_blocks)
        self.assertIn(PUBLICATION_SUMMARY_BLOCK, stream_block.child_blocks)
        self.assertIn(STANDARD_PUBLICATION_BLOCK, stream_block.child_blocks)

    def _publication_block_value(self, **overrides):
        return {
            "index_page": self.index_page,
            "entries_count": 3,
            **overrides,
        }

    def _downloadable_document_block_value(self, **overrides):
        return {
            "download_type": "publication",
            "document": self.document,
            **overrides,
        }

    def _content_page_with_body(self, slug, body):
        return self.home.add_child(
            instance=ContentPage(title="Availability page", slug=slug, owner=self.admin, body=body),
        )

    def _publication_recent_entries_nested_cases(self):
        return (
            (
                "multicolumn column",
                "publication-in-multicolumn-column",
                [
                    (
                        "multicolumns",
                        {
                            "columns": [
                                (
                                    "column",
                                    {
                                        "width": "6",
                                        "content": [
                                            (
                                                PUBLICATION_RECENT_ENTRIES_BLOCK,
                                                self._publication_block_value(title="In a column"),
                                            ),
                                        ],
                                    },
                                ),
                            ],
                        },
                    ),
                ],
                "In a column",
            ),
            (
                "item grid",
                "publication-in-item-grid",
                [
                    (
                        "item_grid",
                        {
                            "column_width": "4",
                            "items": [
                                (
                                    PUBLICATION_RECENT_ENTRIES_BLOCK,
                                    self._publication_block_value(title="In item grid"),
                                ),
                            ],
                        },
                    ),
                ],
                "In item grid",
            ),
        )

    def _downloadable_document_nested_cases(self):
        return (
            (
                "multicolumn column",
                "downloadable-document-in-multicolumn-column",
                [
                    (
                        "multicolumns",
                        {
                            "columns": [
                                (
                                    "column",
                                    {
                                        "width": "6",
                                        "content": [
                                            (
                                                DOWNLOADABLE_DOCUMENT_BLOCK,
                                                self._downloadable_document_block_value(),
                                            ),
                                        ],
                                    },
                                ),
                            ],
                        },
                    ),
                ],
                gettext("Download publication"),
            ),
            (
                "item grid",
                "downloadable-document-in-item-grid",
                [
                    (
                        "item_grid",
                        {
                            "column_width": "4",
                            "items": [
                                (
                                    DOWNLOADABLE_DOCUMENT_BLOCK,
                                    self._downloadable_document_block_value(),
                                ),
                            ],
                        },
                    ),
                ],
                gettext("Download publication"),
            ),
        )

    def test_blocks_are_registered_in_nested_streams(self):
        for case_label, stream_path in self.NESTED_STREAM_PATHS:
            with self.subTest(stream=case_label):
                self._assert_blocks_registered_in_stream(*stream_path)

    def test_can_render_page_with_publication_recent_entries_in_nested_streams(self):
        for case_label, slug, body, title in self._publication_recent_entries_nested_cases():
            with self.subTest(stream=case_label):
                page = self._content_page_with_body(slug, body)
                self.assertPageIsRenderable(page)

                response = self.client.get(page.url)
                block = BeautifulSoup(response.content, "html.parser").select_one(
                    ".cmsfr-block-publication-recent-entries",
                )
                self.assertIsNotNone(block)
                self.assertIn(title, block.get_text())

    def _standard_publication_block_value(self, **overrides):
        return {
            "subtitle": "Standard publication subtitle",
            "summary": "<p>Standard publication summary.</p>",
            "downloadable_documents": [
                {
                    "download_type": "publication",
                    "document": self.document,
                }
            ],
            **overrides,
        }

    def _standard_publication_nested_cases(self):
        return (
            (
                "multicolumn column",
                "standard-publication-in-multicolumn-column",
                [
                    (
                        "multicolumns",
                        {
                            "columns": [
                                (
                                    "column",
                                    {
                                        "width": "6",
                                        "content": [
                                            (
                                                STANDARD_PUBLICATION_BLOCK,
                                                self._standard_publication_block_value(),
                                            ),
                                        ],
                                    },
                                ),
                            ],
                        },
                    ),
                ],
                "Standard publication subtitle",
            ),
        )

    def test_can_render_page_with_downloadable_document_in_nested_streams(self):
        for case_label, slug, body, title in self._downloadable_document_nested_cases():
            with self.subTest(stream=case_label):
                page = self._content_page_with_body(slug, body)
                self.assertPageIsRenderable(page)

                response = self.client.get(page.url)
                self.assertContains(response, title)
                self.assertContains(response, self.document.title)
                self.assertContains(response, self.document.url)

    def test_can_render_page_with_standard_publication_in_nested_streams(self):
        for case_label, slug, body, subtitle in self._standard_publication_nested_cases():
            with self.subTest(stream=case_label):
                page = self._content_page_with_body(slug, body)
                self.assertPageIsRenderable(page)

                response = self.client.get(page.url)
                block = BeautifulSoup(response.content, "html.parser").select_one(
                    ".cmsfr-block-standard-publication",
                )
                self.assertIsNotNone(block)
                self.assertIn(subtitle, block.get_text())
                self.assertIn(self.document.title, block.get_text())

    # TODO test that the block picker offers the registered blocks (e2e test)
