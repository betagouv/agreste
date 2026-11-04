from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils.translation import gettext as _
from wagtail.blocks.stream_block import StreamBlockValidationError
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.contrib.typed_table_block.blocks import TypedTableBlockValidationError
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase

from publications.blocks.nomenclature import NomenclatureModalitiesBlock, NomenclatureStreamBlock
from publications.models import PublicationIndexPage, PublicationPage


def modalities(*rows):
    return [{"code": code, "name": name} for code, name in rows]


def row_codes(table):
    return [row["values"][0] for row in table.row_data]


def code_message(error, index):
    return error.cell_errors[index][0].messages[0]


class NomenclatureModalitiesTest(SimpleTestCase):
    def setUp(self):
        self.block = NomenclatureModalitiesBlock()

    def test_new_table_has_code_and_name_and_no_rows(self):
        default = self.block.get_default()

        self.assertEqual([column["block"].name for column in default.columns], ["code", "name", "code_old"])
        self.assertEqual([column["heading"] for column in default.columns], [_("Code"), _("Name"), ""])
        self.assertEqual(default.row_data, [])
        self.assertEqual(default.caption, "")

    def test_posted_headings_and_caption_are_ignored(self):
        table = self.block.value_from_datadict(
            {
                "modalities-caption": "Ignore me",
                "modalities-column-count": "2",
                "modalities-column-0-type": "code",
                "modalities-column-0-order": "0",
                "modalities-column-0-heading": "Nope",
                "modalities-column-0-deleted": "",
                "modalities-column-1-type": "name",
                "modalities-column-1-order": "1",
                "modalities-column-1-heading": "Also nope",
                "modalities-column-1-deleted": "",
                "modalities-row-count": "1",
                "modalities-row-0-order": "0",
                "modalities-row-0-deleted": "",
                "modalities-cell-0-0": "1",
                "modalities-cell-0-1": "World",
            },
            {},
            "modalities",
        )

        self.assertEqual([column["heading"] for column in table.columns], [_("Code"), _("Name"), ""])
        self.assertEqual([column["block"].name for column in table.columns], ["code", "name", "code_old"])
        self.assertEqual(table.caption, "")
        self.assertEqual(table.row_data[0]["values"], ["1", "World", ""])

    def test_blank_code_old_is_valid(self):
        cleaned = self.block.clean(modalities(("1", "World")))

        self.assertEqual(cleaned.row_data[0]["values"], ["1", "World", ""])

    def test_code_old_is_kept(self):
        cleaned = self.block.clean([{"code": "1", "name": "World", "code_old": "25"}])

        self.assertEqual(cleaned.row_data[0]["values"], ["1", "World", "25"])

    def test_two_column_row_loads_with_empty_code_old(self):
        table = self.block.to_python(
            {
                "columns": [
                    {"type": "code", "heading": "Code"},
                    {"type": "name", "heading": "Name"},
                ],
                "rows": [{"values": ["1", "World"]}],
                "caption": "",
            }
        )

        self.assertEqual(table.row_data[0]["values"], ["1", "World", ""])

    def test_codes_in_numeric_order_are_valid(self):
        cleaned = self.block.clean(
            modalities(("1", "World"), ("1.1", "Europe"), ("1.2", "Asia"), ("1.10", "Oceania"), ("2", "Other"))
        )

        self.assertEqual(row_codes(cleaned), ["1", "1.1", "1.2", "1.10", "2"])

    def test_a_gap_in_numbering_is_valid(self):
        cleaned = self.block.clean(modalities(("1", "World"), ("1.2", "Asia")))

        self.assertEqual(row_codes(cleaned), ["1", "1.2"])

    def test_empty_name_points_at_that_row(self):
        for clean in (self.block.clean, self.block.clean_deferred):
            with self.assertRaises(TypedTableBlockValidationError) as caught:
                clean(modalities(("1", "World"), ("1.1", "  ")))

            self.assertEqual(caught.exception.cell_errors[1][1].messages, [_("This field is required.")])

    def test_empty_code_points_at_that_row(self):
        with self.assertRaises(TypedTableBlockValidationError) as caught:
            self.block.clean(modalities(("1", "World"), ("", "Europe")))

        self.assertEqual(caught.exception.cell_errors[1][0].messages, [_("This field is required.")])

    def test_malformed_code_points_at_that_row(self):
        with self.assertRaises(TypedTableBlockValidationError) as caught:
            self.block.clean(modalities(("1", "World"), ("1.1", "Europe"), ("1.2", "Asia"), ("1.a", "Bad")))

        self.assertEqual(
            code_message(caught.exception, 3),
            _("Line %(line)s: code “%(code)s” must be dot-separated numbers.") % {"line": 4, "code": "1.a"},
        )

    def test_duplicate_code_points_at_the_later_row(self):
        with self.assertRaises(TypedTableBlockValidationError) as caught:
            self.block.clean(
                modalities(
                    ("1", "World"),
                    ("1.1", "Europe"),
                    ("1.2", "Asia"),
                    ("1.2.1", "France"),
                    ("2", "Other"),
                    ("1.1", "Europe again"),
                )
            )

        self.assertEqual(
            code_message(caught.exception, 5),
            _("Line %(line)s: code “%(code)s” is already used on line %(earlier)s.")
            % {"line": 6, "code": "1.1", "earlier": 2},
        )

    def test_leading_zeros_are_the_same_code(self):
        with self.assertRaises(TypedTableBlockValidationError) as caught:
            self.block.clean(modalities(("1", "World"), ("01", "World again")))

        self.assertEqual(
            code_message(caught.exception, 1),
            _("Line %(line)s: code “%(code)s” is already used on line %(earlier)s.")
            % {"line": 2, "code": "01", "earlier": 1},
        )

    def test_missing_parent_points_at_that_row(self):
        with self.assertRaises(TypedTableBlockValidationError) as caught:
            self.block.clean(modalities(("1", "World"), ("1.1", "Europe"), ("1.1.1", "France"), ("1.2.1", "Japan")))

        self.assertEqual(
            code_message(caught.exception, 3),
            _("Line %(line)s: code “%(code)s” has no parent “%(parent)s” above it.")
            % {"line": 4, "code": "1.2.1", "parent": "1.2"},
        )

    def test_out_of_order_code_points_at_that_row(self):
        with self.assertRaises(TypedTableBlockValidationError) as caught:
            self.block.clean(
                modalities(("1", "World"), ("1.2", "Asia"), ("1.2.1", "Japan"), ("2", "Other"), ("1.1", "Europe"))
            )

        self.assertEqual(
            code_message(caught.exception, 4),
            _(
                "Line %(line)s: code “%(code)s” is out of order. "
                "It should come before “%(earlier_code)s” (line %(earlier)s)."
            )
            % {"line": 5, "code": "1.1", "earlier": 4, "earlier_code": "2"},
        )


class NomenclatureStreamTest(SimpleTestCase):
    def setUp(self):
        self.block = NomenclatureStreamBlock()

    def test_the_same_code_is_allowed_in_two_nomenclatures(self):
        cleaned = self.block.clean(
            [
                ("nomenclature", {"name": "Geography", "modalities": modalities(("1", "World"))}),
                ("nomenclature", {"name": "Animals", "modalities": modalities(("1", "Cattle"))}),
            ]
        )

        self.assertEqual(
            [code for child in cleaned for code in row_codes(child.value["modalities"])],
            ["1", "1"],
        )

    def test_duplicate_names_point_at_the_later_name(self):
        with self.assertRaises(StreamBlockValidationError) as caught:
            self.block.clean(
                [
                    ("nomenclature", {"name": "Geography", "modalities": modalities(("1", "World"))}),
                    ("nomenclature", {"name": "Geography", "modalities": modalities(("2", "Europe"))}),
                ]
            )

        name_error = caught.exception.block_errors[1]
        self.assertIsInstance(name_error, StructBlockValidationError)
        self.assertEqual(
            name_error.block_errors["name"].messages,
            [
                _("Line %(line)s: nomenclature name “%(name)s” is already used on line %(earlier)s.")
                % {"line": 2, "name": "Geography", "earlier": 1}
            ],
        )


class NomenclatureEditorStylesheetTest(WagtailPageTestCase):
    def test_edit_page_loads_the_nomenclature_row_stylesheet(self):
        admin = get_user_model().objects.create_superuser("test", "test@test.test", "pass")
        self.client.login(username="test", password="pass")
        home = Page.objects.get(slug="home")
        index = home.add_child(instance=PublicationIndexPage(title="Publications", slug="publications", owner=admin))
        page = index.add_child(
            instance=PublicationPage(title="Bulletin", slug="bulletin", owner=admin, disaron_id="GEO-1")
        )

        response = self.client.get(reverse("wagtailadmin_pages:edit", args=[page.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "nomenclature_entries.css")
        self.assertContains(response, "nomenclature_modalities.js")
