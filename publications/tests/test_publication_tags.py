from django.test import RequestFactory, SimpleTestCase

from publications.models import Collection
from publications.templatetags.publication_tags import collection_chains, toggle_url_filter


class ToggleUrlFilterTestBase(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _context(self, query_string="", **current):
        path = f"/?{query_string}" if query_string else "/"
        return {"request": self.factory.get(path), **current}


class ToggleUrlFilterPublicationSpecificTest(ToggleUrlFilterTestBase):
    def test_adds_collection_filter(self):
        collection = type("Collection", (), {"slug": "agriculture"})()
        result = toggle_url_filter(self._context(), collection=collection)
        self.assertEqual(result, "?collection=agriculture")

    def test_adds_theme_filter(self):
        theme = type("Theme", (), {"slug": "climate"})()
        result = toggle_url_filter(self._context(), theme=theme)
        self.assertEqual(result, "?theme=climate")

    def test_removes_active_collection_filter(self):
        collection = type("Collection", (), {"slug": "agriculture"})()
        result = toggle_url_filter(
            self._context("collection=agriculture", current_collection=collection),
            collection=collection,
        )
        self.assertEqual(result, "")

    def test_removes_active_collection_while_keeping_theme(self):
        collection = type("Collection", (), {"slug": "agriculture"})()
        result = toggle_url_filter(
            self._context(
                "collection=agriculture&theme=climate",
                current_collection=collection,
            ),
            collection=collection,
        )
        self.assertEqual(result, "?theme=climate")

    def test_uses_filters_dict_with_publication_filters(self):
        collection = type("Collection", (), {"slug": "agriculture"})()
        theme = type("Theme", (), {"slug": "climate"})()
        result = toggle_url_filter(
            self._context("ignored=1"),
            filters_dict={"theme": theme.slug},
            collection=collection,
        )
        self.assertEqual(result, "?theme=climate&collection=agriculture")


class CollectionChainsTest(SimpleTestCase):
    def test_child_without_assigned_parent_stays_alone(self):
        parent = Collection(pk=1, name="Parent")
        child = Collection(pk=2, name="Child", parent=parent)
        self.assertEqual(collection_chains([child]), [[child]])

    def test_parent_and_child_form_one_chain(self):
        parent = Collection(pk=1, name="Parent")
        child = Collection(pk=2, name="Child", parent=parent)
        self.assertEqual(collection_chains([parent, child]), [[parent, child]])

    def test_two_children_make_two_chains(self):
        parent = Collection(pk=1, name="Parent")
        child_a = Collection(pk=2, name="Child A", parent=parent)
        child_b = Collection(pk=3, name="Child B", parent=parent)
        self.assertEqual(
            collection_chains([parent, child_a, child_b]),
            [[parent, child_a], [parent, child_b]],
        )

    def test_three_levels_form_one_chain(self):
        grandparent = Collection(pk=1, name="Grandparent")
        parent = Collection(pk=2, name="Parent", parent=grandparent)
        child = Collection(pk=3, name="Child", parent=parent)
        self.assertEqual(collection_chains([grandparent, parent, child]), [[grandparent, parent, child]])
