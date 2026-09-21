from django.test import TestCase
from wagtail.models import Locale

from publications.tests.factories import CollectionFactory


class SelfAndDescendantsTest(TestCase):
    def setUp(self):
        self.locale = Locale.get_default()

    def test_leaf_returns_only_self(self):
        leaf = CollectionFactory(locale=self.locale, name="Leaf")
        self.assertCountEqual(leaf.self_and_descendants(), [leaf])

    def test_parent_includes_children_and_grandchildren(self):
        parent = CollectionFactory(locale=self.locale, name="Parent")
        child = CollectionFactory(locale=self.locale, name="Child", parent=parent)
        grandchild = CollectionFactory(locale=self.locale, name="Grandchild", parent=child)
        sibling = CollectionFactory(locale=self.locale, name="Sibling")

        self.assertCountEqual(parent.self_and_descendants(), [parent, child, grandchild])
        self.assertCountEqual(child.self_and_descendants(), [child, grandchild])
        self.assertNotIn(sibling, parent.self_and_descendants())
