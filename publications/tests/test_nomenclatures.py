from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils.translation import gettext as _
from wagtail.blocks.list_block import ListBlockValidationError
from wagtail.blocks.stream_block import StreamBlockValidationError
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase

from publications.blocks.nomenclature import (
    NomenclatureEntryBlock,
    NomenclatureEntryListBlock,
    NomenclatureStreamBlock,
)
from publications.models import PublicationIndexPage, PublicationPage


def modalities(*rows):
    return [{"code": code, "name": name} for code, name in rows]


def code_message(error, index):
    row_error = error.block_errors[index]
    if not isinstance(row_error, StructBlockValidationError):
        raise AssertionError(row_error)
    return row_error.block_errors["code"].messages[0]


class NomenclatureEntryListTest(SimpleTestCase):
    def setUp(self):
        self.block = NomenclatureEntryListBlock(NomenclatureEntryBlock())

    def test_new_entry_list_starts_empty(self):
        self.assertEqual(len(self.block.get_default()), 0)

    def test_codes_in_numeric_order_are_valid(self):
        cleaned = self.block.clean(
            modalities(("1", "World"), ("1.1", "Europe"), ("1.2", "Asia"), ("1.10", "Oceania"), ("2", "Other"))
        )

        self.assertEqual([row["code"] for row in cleaned], ["1", "1.1", "1.2", "1.10", "2"])

    def test_a_gap_in_numbering_is_valid(self):
        cleaned = self.block.clean(modalities(("1", "World"), ("1.2", "Asia")))

        self.assertEqual([row["code"] for row in cleaned], ["1", "1.2"])

    def test_empty_code_points_at_that_row(self):
        with self.assertRaises(ListBlockValidationError) as caught:
            self.block.clean(modalities(("1", "World"), ("", "Europe")))

        self.assertIn("code", caught.exception.block_errors[1].block_errors)
        self.assertEqual(
            caught.exception.block_errors[1].block_errors["code"].messages,
            [_("This field is required.")],
        )

    def test_malformed_code_points_at_that_row(self):
        with self.assertRaises(ListBlockValidationError) as caught:
            self.block.clean(modalities(("1", "World"), ("1.1", "Europe"), ("1.2", "Asia"), ("1.a", "Bad")))

        self.assertEqual(
            code_message(caught.exception, 3),
            _("Line %(line)s: code “%(code)s” must be dot-separated numbers.") % {"line": 4, "code": "1.a"},
        )

    def test_duplicate_code_points_at_the_later_row(self):
        with self.assertRaises(ListBlockValidationError) as caught:
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
        with self.assertRaises(ListBlockValidationError) as caught:
            self.block.clean(modalities(("1", "World"), ("01", "World again")))

        self.assertEqual(
            code_message(caught.exception, 1),
            _("Line %(line)s: code “%(code)s” is already used on line %(earlier)s.")
            % {"line": 2, "code": "01", "earlier": 1},
        )

    def test_missing_parent_points_at_that_row(self):
        with self.assertRaises(ListBlockValidationError) as caught:
            self.block.clean(modalities(("1", "World"), ("1.1", "Europe"), ("1.1.1", "France"), ("1.2.1", "Japan")))

        self.assertEqual(
            code_message(caught.exception, 3),
            _("Line %(line)s: code “%(code)s” has no parent “%(parent)s” above it.")
            % {"line": 4, "code": "1.2.1", "parent": "1.2"},
        )

    def test_out_of_order_code_points_at_that_row(self):
        with self.assertRaises(ListBlockValidationError) as caught:
            self.block.clean(
                modalities(("1", "World"), ("1.2", "Asia"), ("1.2.1", "Japan"), ("2", "Other"), ("1.1", "Europe"))
            )

        self.assertEqual(
            code_message(caught.exception, 4),
            _(
                "Line %(line)s: code “%(code)s” is out of order. "
                "It should come before line %(earlier)s (“%(earlier_code)s”)."
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
            [row["code"] for child in cleaned for row in child.value["modalities"]],
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
