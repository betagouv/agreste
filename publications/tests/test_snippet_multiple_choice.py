from bs4 import BeautifulSoup
from django.http import QueryDict
from django.test import TestCase
from wagtail.models import Locale

from publications.blocks.snippet_multiple_choice import SnippetMultipleChoiceBlock
from publications.tests.factories import CollectionFactory


class SnippetMultipleChoiceBlockTest(TestCase):
    def setUp(self):
        self.locale = Locale.get_default()
        self.theme1 = CollectionFactory(name="theme1", locale=self.locale)
        self.child_1b = CollectionFactory(name="childtheme1B", parent=self.theme1, locale=self.locale)
        self.child_1a = CollectionFactory(name="childtheme1A", parent=self.theme1, locale=self.locale)
        self.theme2 = CollectionFactory(name="theme2", locale=self.locale)
        self.child_2a = CollectionFactory(name="childtheme2A", parent=self.theme2, locale=self.locale)
        self.block = SnippetMultipleChoiceBlock("publications.Collection", hierarchical=True, required=False)

    def test_to_python_accepts_legacy_scalar_pk(self):
        self.assertEqual(self.block.to_python(self.theme1.pk), [self.theme1])

    def test_to_python_accepts_legacy_instance(self):
        self.assertEqual(self.block.to_python(self.theme1), [self.theme1])

    def test_to_python_accepts_list_of_pks(self):
        self.assertEqual(
            self.block.to_python([self.theme1.pk, self.theme2.pk]),
            [self.theme1, self.theme2],
        )

    def test_to_python_skips_missing_pks(self):
        self.assertEqual(self.block.to_python([self.theme1.pk, 999999]), [self.theme1])

    def test_value_from_datadict_keeps_checked_boxes(self):
        data = QueryDict(mutable=True)
        data.setlist("collection_filter", [str(self.theme1.pk), str(self.theme2.pk)])
        native = self.block.value_from_datadict(data, {}, "collection_filter")
        self.assertEqual(native, [self.theme1, self.theme2])
        self.assertEqual(
            self.block.get_prep_value(self.block.clean(native)),
            [self.theme1.pk, self.theme2.pk],
        )

    def test_get_prep_value_stores_list_of_pks(self):
        self.assertEqual(self.block.get_prep_value([self.theme1, self.theme2]), [self.theme1.pk, self.theme2.pk])
        self.assertEqual(self.block.get_prep_value(self.theme1), [self.theme1.pk])
        self.assertEqual(self.block.get_prep_value(None), [])

    def test_clean_empty_selection_stays_empty(self):
        self.assertEqual(self.block.clean([]), [])

    def test_widget_renders_tree_in_depth_first_order_with_indent(self):
        html = self.block.field.widget.render("collection", [self.theme1.pk])
        soup = BeautifulSoup(html, "html.parser")
        options = soup.select(".agr-snippet-multi-chooser__option")
        labels = [option.get_text(strip=True) for option in options]
        self.assertEqual(
            labels,
            ["theme1", "childtheme1A", "childtheme1B", "theme2", "childtheme2A"],
        )
        depths = [option.get("style") for option in options]
        self.assertEqual(
            depths,
            [
                "--agr-depth: 0",
                "--agr-depth: 1",
                "--agr-depth: 1",
                "--agr-depth: 0",
                "--agr-depth: 1",
            ],
        )
        checked = soup.select("input[type=checkbox][checked]")
        self.assertEqual([input_el["value"] for input_el in checked], [str(self.theme1.pk)])
