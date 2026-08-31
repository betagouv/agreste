from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.utils.translation import gettext
from wagtail.documents import get_document_model
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase

from publications.blocks.download_tile import DOWNLOAD_TILE_BLOCK
from publications.blocks.publication_subtitle import PUBLICATION_SUBTITLE_BLOCK
from publications.blocks.recent_entries import PUBLICATION_RECENT_ENTRIES_BLOCK
from publications.blocks.register_sites_conformes_blocks import BLOG_RECENT_ENTRIES_BLOCK
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

        self.assertIn(DOWNLOAD_TILE_BLOCK, child_blocks)
        self.assertEqual(child_blocks[DOWNLOAD_TILE_BLOCK].meta.group, "Agreste")

        self.assertIn(PUBLICATION_SUBTITLE_BLOCK, child_blocks)
        self.assertEqual(child_blocks[PUBLICATION_SUBTITLE_BLOCK].meta.group, "Agreste")


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
        self.assertIn(DOWNLOAD_TILE_BLOCK, stream_block.child_blocks)
        self.assertIn(PUBLICATION_SUBTITLE_BLOCK, stream_block.child_blocks)

    def _publication_block_value(self, **overrides):
        return {
            "index_page": self.index_page,
            "entries_count": 3,
            **overrides,
        }

    def _download_tile_block_value(self, **overrides):
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

    def _download_tile_nested_cases(self):
        return (
            (
                "multicolumn column",
                "download-tile-in-multicolumn-column",
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
                                                DOWNLOAD_TILE_BLOCK,
                                                self._download_tile_block_value(),
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
                "download-tile-in-item-grid",
                [
                    (
                        "item_grid",
                        {
                            "column_width": "4",
                            "items": [
                                (
                                    DOWNLOAD_TILE_BLOCK,
                                    self._download_tile_block_value(),
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

    def test_can_render_page_with_download_tile_in_nested_streams(self):
        for case_label, slug, body, title in self._download_tile_nested_cases():
            with self.subTest(stream=case_label):
                page = self._content_page_with_body(slug, body)
                self.assertPageIsRenderable(page)

                response = self.client.get(page.url)
                self.assertContains(response, title)
                self.assertContains(response, self.document.title)
                self.assertContains(response, self.document.url)

    # TODO test that the block picker offers the registered blocks (e2e test)
