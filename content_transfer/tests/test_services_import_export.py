import copy
import json
import tempfile
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.files.base import File
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from wagtail.documents import get_document_model
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase
from wagtail.utils.file import hash_filelike

from content_transfer.import_export import (
    DocumentTransferError,
    ExportPage,
    ImportExportDocuments,
    ImportExportImages,
    ImportPages,
    locate_document_ids,
    locate_page_ids,
    remove_block_ids,
    update_streamfield_document_ids,
    update_streamfield_image_ids,
    update_streamfield_page_ids,
)
from sites_conformes.core.models import ContentPage

Document = get_document_model()


class ImportPagesTestCase(WagtailPageTestCase):
    def setUp(self):
        call_command("create_starter_pages")
        call_command("import_page_templates")
        self.templates_index = ContentPage.objects.get(slug="page_templates_index")
        self.home_page = ContentPage.objects.get(slug="home")

    def test_copied_template_is_correctly_updated(self):
        template = ContentPage.objects.child_of(self.templates_index).first()
        new_page = template.copy(to=self.home_page)

        self.assertEqual(new_page.get_parent(), self.home_page)
        self.assertEqual(new_page.source_url, None)

        find_template = (
            ContentPage.objects.child_of(self.templates_index).filter(source_url=template.source_url).first()
        )
        self.assertEqual(template.id, find_template.id)


def page_api_response():
    """Minimal copy of a page as returned by the Wagtail API of the source site"""
    return {
        "id": 32,
        "meta": {
            "type": "sites_conformes_core.ContentPage",
            "html_url": "https://source.example.com/modele/",
            "slug": "modele",
            "parent": {"id": 1},
            "seo_title": "SEO",
            "search_description": "Description",
        },
        "title": "Modèle",
        "body": [
            {"type": "paragraph", "value": "<p>Bonjour</p>", "id": "block-1"},
            {
                "type": "imageandtext",
                "id": "block-2",
                "value": {"image": 7, "text": "<p>Texte</p>", "items": [{"bg_image": {"image": 8}, "id": "x"}]},
            },
            {"type": "image", "id": "block-3", "value": {"image": 7}},
            {
                "type": "fullwidthbackgroundwithsidemenu",
                "id": "block-4",
                "value": {"image": {"image": None, "alt_text": None, "decorative": None}},
            },
            {
                "type": "link",
                "id": "block-5",
                "value": {"page": None, "document": 11},
            },
            {
                "type": "paragraph",
                "id": "block-6",
                "value": '<p><a linktype="document" id="12">Doc</a></p>',
            },
        ],
        "header_cta_buttons": [{"type": "button", "value": {"document": 11, "page": None}}],
        "tags": ["tag"],
        "header_image": {"id": 5, "meta": {"download_url": "https://source.example.com/media/header.png"}},
        "header_image_render": {"url": "render"},
        "header_image_thumbnail": {"url": "thumbnail"},
    }


class StreamfieldHelpersTestCase(SimpleTestCase):
    def test_remove_block_ids(self):
        value = [{"id": "a", "type": "paragraph", "value": {"id": "b", "items": [{"id": "c", "text": "t"}]}}, 3]

        self.assertEqual(
            remove_block_ids(value),
            [{"type": "paragraph", "value": {"items": [{"text": "t"}]}}, 3],
        )

    def test_update_streamfield_image_ids(self):
        image_data = {"7": {"local_id": 70}, "8": {"local_id": 80}}
        value = [{"type": "image", "value": {"image": 7}}, {"value": {"bg_image": 8, "other": 7}}, {"image": 9}]

        self.assertEqual(
            update_streamfield_image_ids(value, image_data),
            [{"type": "image", "value": {"image": 70}}, {"value": {"bg_image": 80, "other": 7}}, {"image": 9}],
        )

    def test_locate_page_ids(self):
        value = [
            {"type": "link", "value": {"page": 20, "document": None}},
            {"type": "tile", "value": {"link": {"page": None}}},
            {"type": "paragraph", "value": '<p><a linktype="page" id="30">x</a></p>'},
            {"blog": 40, "index_page": "50"},
        ]

        self.assertEqual(locate_page_ids(value), {20, 30, 40, 50})

    def test_locate_document_ids(self):
        value = [
            {"type": "link", "value": {"page": 20, "document": 11}},
            {"type": "link", "value": {"document": None}},
            {"type": "paragraph", "value": '<p><a linktype="document" id="12">x</a></p>'},
            {"document": "13"},
        ]

        self.assertEqual(locate_document_ids(value), {11, 12, 13})

    def test_update_streamfield_page_ids(self):
        page_id_map = {"20": 200, "30": 300}
        value = [
            {"type": "link", "value": {"page": 20}},
            {"type": "link", "value": {"page": 99}},
            {"type": "paragraph", "value": '<p><a linktype="page" id="30">x</a></p>'},
        ]

        self.assertEqual(
            update_streamfield_page_ids(value, page_id_map),
            [
                {"type": "link", "value": {"page": 200}},
                {"type": "link", "value": {"page": 99}},
                {"type": "paragraph", "value": '<p><a linktype="page" id="300">x</a></p>'},
            ],
        )

    def test_update_streamfield_document_ids(self):
        document_data = {"11": {"local_id": 110}, "12": {"local_id": 120}}
        value = [
            {"type": "link", "value": {"document": 11}},
            {"type": "link", "value": {"document": 99}},
            {"type": "paragraph", "value": '<p><a linktype="document" id="12">x</a></p>'},
        ]

        self.assertEqual(
            update_streamfield_document_ids(value, document_data),
            [
                {"type": "link", "value": {"document": 110}},
                {"type": "link", "value": {"document": 99}},
                {"type": "paragraph", "value": '<p><a linktype="document" id="120">x</a></p>'},
            ],
        )

    def test_publications_contentpage_blocks_locate_and_update(self):
        """Publications-registered ContentPage blocks nest the same chooser keys."""
        body = [
            {
                "type": "downloadable_document",
                "value": {"download_type": "publication", "document": 11},
            },
            {
                "type": "standard_publication",
                "value": {
                    "subtitle": "Titre",
                    "summary": '<p><a linktype="document" id="12">Doc</a> ' '<a linktype="page" id="30">Page</a></p>',
                    "notes": "<p>Notes</p>",
                    "downloadable_documents": [
                        {"download_type": "data", "document": 13},
                    ],
                },
            },
            {
                "type": "freeform_publication",
                "value": {
                    "content": [
                        {
                            "type": "image",
                            "value": {"image": {"image": 7, "alt_text": "", "decorative": False}},
                        },
                        {"type": "paragraph", "value": '<p><a linktype="page" id="31">x</a></p>'},
                    ],
                    "downloadable_documents": [
                        {"download_type": "publication", "document": 14},
                    ],
                },
            },
            {
                "type": "publication_recent_entries",
                "value": {"index_page": 50, "collection_filter": 3},
            },
        ]

        self.assertEqual(locate_document_ids(body), {11, 12, 13, 14})
        self.assertEqual(locate_page_ids(body), {30, 31, 50})

        export = ExportPage.__new__(ExportPage)
        export.image_ids = []
        export.locate_image_ids(body)
        self.assertEqual(export.image_ids, [7])

        remapped = update_streamfield_document_ids(
            copy.deepcopy(body),
            {"11": {"local_id": 110}, "12": {"local_id": 120}, "13": {"local_id": 130}, "14": {"local_id": 140}},
        )
        remapped = update_streamfield_page_ids(remapped, {"30": 300, "31": 310, "50": 500})
        remapped = update_streamfield_image_ids(remapped, {"7": {"local_id": 70}})

        self.assertEqual(remapped[0]["value"]["document"], 110)
        self.assertEqual(remapped[1]["value"]["downloadable_documents"][0]["document"], 130)
        self.assertIn('linktype="document" id="120"', remapped[1]["value"]["summary"])
        self.assertIn('linktype="page" id="300"', remapped[1]["value"]["summary"])
        self.assertEqual(remapped[2]["value"]["content"][0]["value"]["image"]["image"], 70)
        self.assertIn('linktype="page" id="310"', remapped[2]["value"]["content"][1]["value"])
        self.assertEqual(remapped[2]["value"]["downloadable_documents"][0]["document"], 140)
        self.assertEqual(remapped[3]["value"]["index_page"], 500)
        # Snippet filters are left unchanged (out of scope for image/page/document transfer)
        self.assertEqual(remapped[3]["value"]["collection_filter"], 3)


class ExportPageTestCase(TestCase):
    @patch("content_transfer.import_export.requests.get")
    def test_export_page(self, mock_get):
        mock_get.return_value.json.return_value = page_api_response()

        export = ExportPage(32, "https://source.example.com/")

        mock_get.assert_called_once_with("https://source.example.com/api/v2/pages/32/", timeout=5)
        content = export.json_export
        self.assertEqual(content["title"], "Modèle")
        self.assertNotIn("id", content["body"][0])
        self.assertNotIn("id", content["body"][1]["value"]["items"][0])
        for key in ["tags", "header_image_render", "header_image_thumbnail"]:
            self.assertNotIn(key, content)
        for key in ["parent", "seo_title", "search_description"]:
            self.assertNotIn(key, content["meta"])
        self.assertEqual(content["meta"]["slug"], "modele")
        self.assertNotIn("download_url", content["header_image"]["meta"])

        # Header image, body images (plain and with alt), no duplicate, and no null id
        self.assertEqual(sorted(export.image_ids), [5, 7, 8])
        # Document chooser in body and header CTA, plus rich-text document link
        self.assertEqual(sorted(export.document_ids), [11, 12])


class ImportExportImagesTestCase(TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.image_folder = Path(tmp_dir.name)

    @patch("content_transfer.import_export.requests.get")
    def test_download_images(self, mock_get):
        api_responses = {
            "https://source.example.com/api/v2/images/1/": {
                "title": "Photo",
                "meta": {"download_url": "https://source.example.com/media/photo.png?v=1"},
            },
            "https://source.example.com/api/v2/images/2/": {
                "title": "Pictogramme",
                "meta": {"download_url": "https://source.example.com/media/Pictogrammes_DSFR__Digital_Mail.svg"},
            },
        }

        def fake_get(url, **kwargs):
            response = MagicMock()
            if kwargs.get("stream"):
                response.__enter__.return_value.iter_content.return_value = [b"PNG", b"DATA"]
            else:
                response.json.return_value = copy.deepcopy(api_responses[url])
            return response

        mock_get.side_effect = fake_get

        exporter = ImportExportImages([1, 2, 1], "https://source.example.com/", image_folder=self.image_folder)
        self.assertEqual(exporter.image_data, {})
        exporter.download_images()

        self.assertEqual((self.image_folder / "photo.png").read_bytes(), b"PNGDATA")
        self.assertEqual(len([c for c in mock_get.call_args_list if c.kwargs.get("stream")]), 1)

        image_data = json.loads((self.image_folder / "image_data.json").read_text())
        self.assertEqual(image_data["1"]["filename"], "photo.png")
        self.assertFalse(image_data["1"]["is_pictogram"])
        self.assertEqual(image_data["1"]["title"], "Photo")
        self.assertNotIn("download_url", image_data["1"]["meta"])
        self.assertEqual(image_data["2"]["filename"], "Pictogrammes DSFR — Digital Mail.svg")
        self.assertTrue(image_data["2"]["is_pictogram"])

        # The saved data is reloaded by a new instance
        reloaded = ImportExportImages([1], image_folder=self.image_folder)
        self.assertEqual(reloaded.image_data, image_data)


class ImportExportDocumentsTestCase(TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.document_folder = Path(tmp_dir.name)

    def _write_source_file(self, filename, content):
        path = self.document_folder / filename
        path.write_bytes(content)
        return path

    def _prepare_importer(self, source_id, title, filename, content):
        self._write_source_file(filename, content)
        importer = ImportExportDocuments([source_id], document_folder=self.document_folder)
        importer.document_data = {
            str(source_id): {
                "title": title,
                "filename": filename,
                "meta": {},
            }
        }
        return importer

    @patch("content_transfer.import_export.requests.get")
    def test_download_documents(self, mock_get):
        def fake_get(url, **kwargs):
            response = MagicMock()
            if kwargs.get("stream"):
                response.__enter__.return_value.iter_content.return_value = [b"%PDF", b"-data"]
            else:
                response.json.return_value = {
                    "title": "Rapport",
                    "meta": {"download_url": "https://source.example.com/media/documents/rapport.pdf?v=1"},
                }
            return response

        mock_get.side_effect = fake_get

        exporter = ImportExportDocuments([9], "https://source.example.com/", document_folder=self.document_folder)
        exporter.download_documents()

        self.assertEqual((self.document_folder / "rapport.pdf").read_bytes(), b"%PDF-data")
        document_data = json.loads((self.document_folder / "document_data.json").read_text())
        self.assertEqual(document_data["9"]["filename"], "rapport.pdf")
        self.assertEqual(document_data["9"]["title"], "Rapport")
        self.assertNotIn("download_url", document_data["9"]["meta"])

    def test_import_reuses_triple_match(self):
        content = b"%PDF-same"
        digest = hash_filelike(BytesIO(content))
        existing = Document(title="Rapport", file=File(BytesIO(content), name="rapport.pdf"))
        existing.save()
        # Keep basename + hash stable (storage may rename the uploaded file)
        Document.objects.filter(pk=existing.pk).update(file="documents/rapport.pdf", file_hash=digest)

        importer = self._prepare_importer(9, "Rapport", "rapport.pdf", content)
        stdout = StringIO()
        with redirect_stdout(stdout):
            importer.import_documents()

        self.assertEqual(importer.document_data["9"]["local_id"], existing.pk)
        self.assertEqual(Document.objects.filter(title="Rapport").count(), 1)
        self.assertIn("Document already present: source id 9", stdout.getvalue())
        self.assertIn(f"local id {existing.pk}", stdout.getvalue())

    def test_import_creates_when_no_name_match(self):
        content = b"%PDF-new"
        filename = "rapport-neuf-create.pdf"
        importer = self._prepare_importer(9, "Rapport neuf create", filename, content)
        stdout = StringIO()
        with redirect_stdout(stdout):
            importer.import_documents()

        created = Document.objects.get(title="Rapport neuf create")
        self.assertEqual(importer.document_data["9"]["local_id"], created.pk)
        self.assertTrue(Path(created.file.name).name.startswith("rapport-neuf-create"))
        self.assertEqual(created.file_hash, hash_filelike(BytesIO(content)))
        self.assertEqual(created.file_size, len(content))
        self.assertIn("Document created: source id 9", stdout.getvalue())
        self.assertIn(f"local id {created.pk}", stdout.getvalue())

    def test_import_errors_on_title_without_matching_hash(self):
        Document(
            title="Rapport",
            file=File(BytesIO(b"%PDF-old"), name="rapport.pdf"),
        ).save()

        importer = self._prepare_importer(9, "Rapport", "rapport.pdf", b"%PDF-new")
        with self.assertRaises(DocumentTransferError) as ctx:
            importer.import_documents()
        self.assertIn("same title or filename", str(ctx.exception))

    def test_import_errors_on_multiple_full_matches(self):
        content = b"%PDF-dup"
        digest = hash_filelike(BytesIO(content))
        for _ in range(2):
            doc = Document(title="Rapport", file=File(BytesIO(content), name="rapport.pdf"))
            doc.save()
            # Force identical basename + hash so both count as full triple matches
            Document.objects.filter(pk=doc.pk).update(file="documents/rapport.pdf", file_hash=digest)

        importer = self._prepare_importer(9, "Rapport", "rapport.pdf", content)
        with self.assertRaises(DocumentTransferError) as ctx:
            importer.import_documents()
        self.assertIn("Ambiguous", str(ctx.exception))


class ImportPagesWithParentTestCase(WagtailPageTestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.image_folder = Path(tmp_dir.name)
        self.document_folder = Path(tmp_dir.name) / "docs"
        self.document_folder.mkdir()

        home = Page.objects.get(slug="home")
        self.parent = home.add_child(instance=ContentPage(title="Parent", slug="parent"))

    def pages_data(self, title):
        page = {
            "meta": {"html_url": "https://source.example.com/modele/", "slug": "modele"},
            "title": title,
            "body": [{"type": "paragraph", "value": "<p>Bonjour</p>"}],
            "header_image": None,
            "header_with_title": True,
            "header_color_class": None,
            "header_large": False,
            "header_darken": False,
            "header_cta_text": "",
            "header_cta_buttons": [],
        }
        return {"image_ids": [], "document_ids": [], "pages": {"32": page}}

    def import_pages(self, title):
        importer = ImportPages(
            pages_data=self.pages_data(title),
            parent_page_slug="parent",
            image_folder=self.image_folder,
            document_folder=self.document_folder,
        )
        with redirect_stdout(StringIO()):
            importer.import_pages()

    def test_pages_are_imported_then_updated(self):
        self.import_pages("Modèle")

        page = ContentPage.objects.child_of(self.parent).get()
        self.assertEqual(page.title, "Modèle")
        self.assertEqual(page.source_url, "https://source.example.com/modele/")
        self.assertTrue(page.header_with_title)

        self.import_pages("Modèle mis à jour")

        updated_page = ContentPage.objects.child_of(self.parent).get()
        self.assertEqual(updated_page.pk, page.pk)
        self.assertEqual(updated_page.title, "Modèle mis à jour")
        self.assertFalse(ContentPage.objects.filter(slug="page_templates_index").exists())

    def test_page_links_are_remapped_after_import(self):
        pages_data = {
            "image_ids": [],
            "document_ids": [],
            "pages": {
                "10": {
                    "meta": {"html_url": "https://source.example.com/source/", "slug": "source"},
                    "title": "Source",
                    "body": [
                        {
                            "type": "link",
                            "value": {
                                "text": "Cible",
                                "link_type": "page",
                                "page": 20,
                                "document": None,
                                "external_url": "",
                                "anchor": "",
                                "query_string": "",
                                "icon": "",
                                "size": "",
                            },
                        }
                    ],
                    "header_image": None,
                    "header_with_title": False,
                    "header_color_class": None,
                    "header_large": False,
                    "header_darken": False,
                    "header_cta_text": "",
                    "header_cta_buttons": [],
                },
                "20": {
                    "meta": {"html_url": "https://source.example.com/target/", "slug": "target"},
                    "title": "Target",
                    "body": [{"type": "paragraph", "value": "<p>Cible</p>"}],
                    "header_image": None,
                    "header_with_title": False,
                    "header_color_class": None,
                    "header_large": False,
                    "header_darken": False,
                    "header_cta_text": "",
                    "header_cta_buttons": [],
                },
            },
        }

        importer = ImportPages(
            pages_data=pages_data,
            parent_page_slug="parent",
            image_folder=self.image_folder,
            document_folder=self.document_folder,
        )
        with redirect_stdout(StringIO()):
            importer.import_pages()
            importer.fix_page_links("https://source.example.com/")

        source_page = ContentPage.objects.child_of(self.parent).get(slug="source")
        target_page = ContentPage.objects.child_of(self.parent).get(slug="target")
        self.assertEqual(source_page.body.raw_data[0]["value"]["page"], target_page.pk)

    def test_document_links_are_remapped_on_import(self):
        content = b"%PDF-linked"
        (self.document_folder / "rapport.pdf").write_bytes(content)
        document_data = {
            "11": {
                "title": "Rapport",
                "filename": "rapport.pdf",
                "meta": {},
            }
        }
        pages_data = {
            "image_ids": [],
            "document_ids": [11],
            "pages": {
                "10": {
                    "meta": {"html_url": "https://source.example.com/with-doc/", "slug": "with-doc"},
                    "title": "With doc",
                    "body": [
                        {
                            "type": "link",
                            "value": {
                                "text": "PDF",
                                "link_type": "document",
                                "page": None,
                                "document": 11,
                                "external_url": "",
                                "anchor": "",
                                "query_string": "",
                                "icon": "",
                                "size": "",
                            },
                        },
                        {
                            "type": "paragraph",
                            "value": '<p><a linktype="document" id="11">PDF</a></p>',
                        },
                    ],
                    "header_image": None,
                    "header_with_title": False,
                    "header_color_class": None,
                    "header_large": False,
                    "header_darken": False,
                    "header_cta_text": "",
                    "header_cta_buttons": [],
                },
            },
        }

        importer = ImportPages(
            pages_data=pages_data,
            parent_page_slug="parent",
            image_folder=self.image_folder,
            document_folder=self.document_folder,
        )
        importer.document_importer.document_data = document_data
        with redirect_stdout(StringIO()):
            importer.import_pages()

        page = ContentPage.objects.child_of(self.parent).get(slug="with-doc")
        local_document = Document.objects.get(title="Rapport")
        self.assertEqual(page.body.raw_data[0]["value"]["document"], local_document.pk)
        self.assertIn(f'linktype="document" id="{local_document.pk}"', page.body.raw_data[1]["value"])
