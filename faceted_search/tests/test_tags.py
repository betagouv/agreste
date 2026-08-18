from urllib.parse import parse_qs, urlencode

from django.test import RequestFactory, SimpleTestCase

from faceted_search.templatetags.faceted_search_tags import facet_label, toggle_url_facet


class FacetLabelTest(SimpleTestCase):
    """``facet_label`` formats ``Name (N)`` (with ``FacetedSearchCountRenderingTest``)."""

    def test_facet_label_includes_count_when_present(self):
        self.assertEqual(facet_label("Agriculture", 3), "Agriculture (3)")

    def test_facet_label_omits_count_when_missing(self):
        self.assertEqual(facet_label("Agriculture"), "Agriculture")
        self.assertEqual(facet_label("Agriculture", None), "Agriculture")
        self.assertEqual(facet_label("Agriculture", ""), "Agriculture")


class FacetedSearchToggleUrlFacetTest(SimpleTestCase):
    def setUp(self):
        self.factory = (
            RequestFactory()
        )  # We use a dummy request rather than a real client request, to save test running time.
        self.collection = type("Collection", (), {"slug": "agriculture"})()
        self.other_collection = type("Collection", (), {"slug": "climate"})()

    def _assert_toggle_url_facet(
        self,
        *,
        request_params=None,
        expected,
        **toggle_kwargs,
    ):
        query = urlencode({"q": "Post", **(request_params or {})}, doseq=True)
        request = self.factory.get(f"/search/?{query}")
        result = toggle_url_facet({"request": request}, **toggle_kwargs)
        self.assertEqual(parse_qs(result.removeprefix("?")), expected)

    def test_toggle_adds_facet_value(self):
        self._assert_toggle_url_facet(
            request_params={"collection": self.collection.slug},
            collection=self.other_collection,
            expected={
                "q": ["Post"],
                "collection": [self.collection.slug, self.other_collection.slug],
            },
        )

    def test_toggle_removes_facet_value(self):
        self._assert_toggle_url_facet(
            request_params={"collection": self.collection.slug},
            collection=self.collection,
            expected={"q": ["Post"]},
        )

    def test_toggle_resets_pagination(self):
        self._assert_toggle_url_facet(
            request_params={"page": 2, "collection": self.collection.slug},
            collection=self.other_collection,
            expected={
                "q": ["Post"],
                "collection": [self.collection.slug, self.other_collection.slug],
            },
        )
