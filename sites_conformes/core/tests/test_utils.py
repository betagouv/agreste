from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from wagtail.blocks import BoundBlock, CharBlock, ListBlock
from wagtail.images.models import Image
from wagtail.test.utils import WagtailPageTestCase

from sites_conformes.core.abstract import SitesFacilesBasePage
from sites_conformes.core.models import ContentPage
from sites_conformes.core.utils import (
    SEARCH_DESCRIPTION_MAX_CHARS,
    get_search_description,
    get_streamblock_raw_text,
    import_image,
)


def _body(data):
    return ContentPage._meta.get_field("body").to_python(data)


def _hero(data):
    return ContentPage._meta.get_field("hero").to_python(data)


class UtilsTestCase(WagtailPageTestCase):
    def test_import_image(self):
        image_file = "sites_conformes/static/artwork/technical-error.svg"
        image = import_image(image_file, "Sample image")

        assert isinstance(image, Image)
        assert image.title == "Sample image"


class StreamfieldRawTextTestCase(SimpleTestCase):
    def test_paragraph_text_is_extracted(self):
        body = _body(
            [
                {
                    "type": "paragraph",
                    "value": "<p>A short description of this page.</p>",
                }
            ]
        )

        result = get_search_description(body)

        self.assertEqual(result, "A short description of this page.")

    def test_multicolumns_column_width_and_content_labels_are_omitted(self):
        body = _body(
            [
                {
                    "type": "multicolumns",
                    "value": {
                        "title": "",
                        "heading_tag": "h2",
                        "top_margin": 5,
                        "bottom_margin": 5,
                        "columns": [
                            {
                                "type": "column",
                                "value": {
                                    "width": "8",
                                    "content": [
                                        {
                                            "type": "text",
                                            "value": "<p>Inner column prose about agriculture.</p>",
                                        }
                                    ],
                                },
                            }
                        ],
                    },
                }
            ]
        )

        result = get_search_description(body)

        self.assertEqual(result, "Inner column prose about agriculture.")
        self.assertNotIn("width", result.lower())
        self.assertNotIn("content", result.lower())
        self.assertNotIn("8", result)

    def test_short_text_is_not_truncated(self):
        body = _body(
            [
                {
                    "type": "paragraph",
                    "value": "<p>A short description of this page.</p>",
                }
            ]
        )

        result = get_search_description(body, max_chars=SEARCH_DESCRIPTION_MAX_CHARS)

        self.assertEqual(result, "A short description of this page.")
        self.assertFalse(result.endswith("[...]"))

    def test_long_text_is_truncated_at_word_boundary(self):
        body = _body([{"type": "paragraph", "value": "<p>one two three four</p>"}])

        self.assertEqual(get_search_description(body, max_chars=10), "one two [...]")

    def test_listblock_children_are_extracted_without_error(self):
        list_block = ListBlock(CharBlock())
        bound = BoundBlock(list_block, list_block.to_python(["Hello", "world"]))

        self.assertEqual(get_streamblock_raw_text(bound), "Hello\nworld")

    def test_combined_streamfields_keep_order(self):
        first = _body([{"type": "paragraph", "value": "<p>Hero heading</p>"}])
        second = _body([{"type": "paragraph", "value": "<p>Body paragraph.</p>"}])

        result = get_search_description(first, second)

        self.assertEqual(result, "Hero heading\nBody paragraph.")

    @patch(
        "sites_conformes.core.blocks.medias.Image.objects.filter",
        return_value=MagicMock(first=MagicMock(return_value=None)),
    )
    def test_hero_text_is_extracted(self, _mock_filter):
        hero = _hero(
            [
                {
                    "type": "hero_text_image",
                    "value": {
                        "text_content": {
                            "hero_title": "Hero heading",
                            "hero_subtitle": "<p>Hero description of the organisation.</p>",
                            "position": "left",
                        },
                        "buttons": [
                            {
                                "text": "Click this button",
                                "link_type": "external_url",
                                "external_url": "https://example.com",
                            }
                        ],
                    },
                }
            ]
        )

        result = get_search_description(hero)

        self.assertEqual(result, "Hero heading\nHero description of the organisation.")
        self.assertNotIn("Click this button", result)

    @patch(
        "sites_conformes.core.blocks.medias.Image.objects.filter",
        return_value=MagicMock(first=MagicMock(return_value=None)),
    )
    def test_hero_text_comes_before_body(self, _mock_filter):
        hero = _hero(
            [
                {
                    "type": "hero_text_image",
                    "value": {
                        "text_content": {
                            "hero_title": "Hero heading",
                            "hero_subtitle": "<p>Hero description.</p>",
                            "position": "left",
                        },
                        "buttons": [],
                    },
                }
            ]
        )
        body = _body(
            [
                {
                    "type": "paragraph",
                    "value": "<p>Body paragraph.</p>",
                }
            ]
        )

        result = get_search_description(hero, body)

        self.assertEqual(result, "Hero heading\nHero description.\nBody paragraph.")

    def test_paragraphs_are_separated_by_newlines(self):
        body = _body(
            [
                {"type": "paragraph", "value": "<p>First block.</p>"},
                {"type": "paragraph", "value": "<p>Second block.</p>"},
            ]
        )

        self.assertEqual(get_search_description(body), "First block.\nSecond block.")

    def test_button_labels_are_omitted(self):
        body = _body(
            [
                {"type": "paragraph", "value": "<p>Intro text.</p>"},
                {
                    "type": "buttons_list",
                    "value": {
                        "buttons": [
                            {
                                "type": "button",
                                "value": {
                                    "link_type": "external_url",
                                    "text": "Click this button",
                                    "external_url": "https://example.com",
                                },
                            }
                        ],
                    },
                },
            ]
        )

        result = get_search_description(body)

        self.assertEqual(result, "Intro text.")
        self.assertNotIn("Click this button", result)

    def test_fill_search_description_on_unsaved_page(self):
        page = type("DummyPage", (), {})()
        page.search_description = ""
        page.hero = None
        page.body = _body([{"type": "paragraph", "value": "<p>Hello from the body.</p>"}])

        SitesFacilesBasePage._fill_search_description(page)

        self.assertEqual(page.search_description, "Hello from the body.")

    def test_fill_search_description_does_not_overwrite_existing(self):
        page = type("DummyPage", (), {})()
        page.search_description = "Custom description"
        page.hero = None
        page.body = _body([{"type": "paragraph", "value": "<p>Hello from the body.</p>"}])

        SitesFacilesBasePage._fill_search_description(page)

        self.assertEqual(page.search_description, "Custom description")
