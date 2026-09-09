from django.test import SimpleTestCase

from faceted_search.templatetags.faceted_search_tags import facet_label, facet_value, result_collections


class FacetLabelTest(SimpleTestCase):
    """``facet_label`` formats ``Name (N)`` (with ``FacetedSearchCountRenderingTest``)."""

    def test_facet_label_includes_count_when_present(self):
        self.assertEqual(facet_label("Agriculture", 3), "Agriculture (3)")

    def test_facet_label_omits_count_when_missing(self):
        self.assertEqual(facet_label("Agriculture"), "Agriculture")
        self.assertEqual(facet_label("Agriculture", None), "Agriculture")
        self.assertEqual(facet_label("Agriculture", ""), "Agriculture")


class FacetValueTest(SimpleTestCase):
    def setUp(self):
        self.item = type("Item", (), {"pk": 42, "slug": "agriculture"})()

    def test_facet_value_is_the_slug(self):
        self.assertEqual(facet_value(self.item, "theme"), "agriculture")

    def test_facet_value_is_the_pk_for_authors(self):
        self.assertEqual(facet_value(self.item, "author"), 42)


class _Collection:
    def __init__(self, parent_id=None):
        self.parent_id = parent_id


class _CollectionManager:
    def __init__(self, collections):
        self._collections = collections

    def all(self):
        return self._collections


class _Page:
    def __init__(self, collections=None):
        if collections is not None:
            self.collections = _CollectionManager(collections)


class ResultCollectionsTest(SimpleTestCase):
    def test_missing_collections_returns_empty(self):
        self.assertEqual(result_collections(_Page()), [])

    def test_returns_all_when_no_children(self):
        roots = [_Collection(), _Collection()]
        self.assertEqual(result_collections(_Page(roots)), roots)

    def test_prefers_children_when_parent_is_also_assigned(self):
        parent = _Collection()
        child = _Collection(parent_id=1)
        self.assertEqual(result_collections(_Page([parent, child])), [child])

    def test_returns_children_when_all_are_children(self):
        children = [_Collection(parent_id=1), _Collection(parent_id=2)]
        self.assertEqual(result_collections(_Page(children)), children)
