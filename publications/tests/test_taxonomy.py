from django.test import TestCase
from wagtail.models import Locale

from publications.models import Collection
from publications.taxonomy import flatten_taxonomy_tree
from publications.tests.factories import CollectionFactory


class IterTaxonomyTreeTest(TestCase):
    def setUp(self):
        self.locale = Locale.get_default()

    def test_depth_first_order_with_siblings_sorted_by_name(self):
        theme1 = CollectionFactory(name="theme1", locale=self.locale)
        child_1b = CollectionFactory(name="childtheme1B", parent=theme1, locale=self.locale)
        child_1a = CollectionFactory(name="childtheme1A", parent=theme1, locale=self.locale)
        theme2 = CollectionFactory(name="theme2", locale=self.locale)
        child_2a = CollectionFactory(name="childtheme2A", parent=theme2, locale=self.locale)

        walked = flatten_taxonomy_tree(Collection.objects.all())

        self.assertEqual(
            [(item.name, depth) for item, depth in walked],
            [
                ("theme1", 0),
                ("childtheme1A", 1),
                ("childtheme1B", 1),
                ("theme2", 0),
                ("childtheme2A", 1),
            ],
        )

    def test_missing_parent_is_treated_as_root(self):
        parent = CollectionFactory(name="Parent", locale=self.locale)
        child = CollectionFactory(name="Child", parent=parent, locale=self.locale)

        walked = flatten_taxonomy_tree(Collection.objects.filter(pk=child.pk))

        self.assertEqual([(item.pk, depth) for item, depth in walked], [(child.pk, 0)])
