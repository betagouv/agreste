from urllib.parse import parse_qs

from faceted_search.templatetags.faceted_search_tags import facet_label, toggle_url_filter
from faceted_search.tests.test_filters import FacetedSearchFilterTestBase


class FacetLabelTest(FacetedSearchFilterTestBase):
    """``facet_label`` formats ``Name (N)`` (with ``FacetedSearchCountRenderingTest``)."""

    def test_facet_label_includes_count_when_present(self):
        self.assertEqual(facet_label("Agriculture", 3), "Agriculture (3)")

    def test_facet_label_omits_count_when_missing(self):
        self.assertEqual(facet_label("Agriculture"), "Agriculture")
        self.assertEqual(facet_label("Agriculture", None), "Agriculture")
        self.assertEqual(facet_label("Agriculture", ""), "Agriculture")


class FacetedSearchToggleUrlTest(FacetedSearchFilterTestBase):
    def _assert_toggle_url_filter(
        self,
        *,
        request_params=None,
        expected,
        **toggle_kwargs,
    ):
        request = self.client.get(self.search_url(**(request_params or {}))).wsgi_request
        context = {"request": request}
        result = toggle_url_filter(context, **toggle_kwargs)
        self.assertEqual(parse_qs(result.removeprefix("?")), expected)

    def test_toggle_adds_filter(self):
        self._assert_toggle_url_filter(
            request_params={"collection": self.collection.slug},
            collection=self.other_collection,
            expected={
                "q": ["Post"],
                "collection": [self.collection.slug, self.other_collection.slug],
            },
        )

    def test_toggle_removes_filter(self):
        self._assert_toggle_url_filter(
            request_params={"collection": self.collection.slug},
            collection=self.collection,
            expected={"q": ["Post"]},
        )

    def test_toggle_resets_pagination(self):
        self._assert_toggle_url_filter(
            request_params={"page": 2, "collection": self.collection.slug},
            collection=self.other_collection,
            expected={
                "q": ["Post"],
                "collection": [self.collection.slug, self.other_collection.slug],
            },
        )
