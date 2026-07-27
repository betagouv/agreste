from urllib.parse import parse_qs

from faceted_search.templatetags.faceted_search_tags import toggle_url_filter
from faceted_search.tests.test_filters import FacetedSearchFilterTestBase


class FacetedSearchToggleUrlTest(FacetedSearchFilterTestBase):
    def _assert_toggle_url_filter(
        self,
        *,
        request_params=None,
        filters_dict=None,
        expected,
        **toggle_kwargs,
    ):
        request = self.client.get(self.search_url(**(request_params or {}))).wsgi_request
        context = {"request": request}
        if filters_dict is not None:
            toggle_kwargs["filters_dict"] = filters_dict

        result = toggle_url_filter(context, **toggle_kwargs)

        self.assertEqual(parse_qs(result.removeprefix("?")), expected)

    def test_toggle_adds_filter_to_filters_dict(self):
        self._assert_toggle_url_filter(
            filters_dict={"q": "Post", "collection": [self.collection.slug]},
            collection=self.other_collection,
            expected={
                "q": ["Post"],
                "collection": [self.collection.slug, self.other_collection.slug],
            },
        )

    def test_toggle_removes_filter_from_filters_dict(self):
        self._assert_toggle_url_filter(
            filters_dict={
                "q": "Post",
                "collection": [self.collection.slug, self.other_collection.slug],
            },
            collection=self.collection,
            expected={
                "q": ["Post"],
                "collection": [self.other_collection.slug],
            },
        )

    def test_toggle_adds_filter_to_request_params(self):
        self._assert_toggle_url_filter(
            request_params={"collection": self.collection.slug},
            collection=self.other_collection,
            expected={
                "q": ["Post"],
                "collection": [self.collection.slug, self.other_collection.slug],
            },
        )

    def test_toggle_removes_filter_from_request_params(self):
        self._assert_toggle_url_filter(
            request_params={"collection": self.collection.slug},
            collection=self.collection,
            expected={"q": ["Post"]},
        )

    def test_toggle_resets_page_from_request_params(self):
        self._assert_toggle_url_filter(
            request_params={"page": 2, "collection": self.collection.slug},
            collection=self.other_collection,
            expected={
                "q": ["Post"],
                "collection": [self.collection.slug, self.other_collection.slug],
            },
        )

    def test_toggle_resets_page_from_filters_dict(self):
        self._assert_toggle_url_filter(
            filters_dict={
                "q": "Post",
                "page": "2",
                "collection": [self.collection.slug],
                # no page parameter
            },
            collection=self.other_collection,
            expected={
                "q": ["Post"],
                "collection": [self.collection.slug, self.other_collection.slug],
                # no page parameter
            },
        )
