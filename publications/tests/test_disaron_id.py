import zoneinfo
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase

from publications.migrations.data_migrations.extract_disaron_id import (
    extract_disaron_id_from_html,
    extract_disaron_id_from_stream_data,
)
from publications.models import PublicationIndexPage, PublicationPage
from publications.tests.factories import PublicationPageFactory

User = get_user_model()


class ExtractDisaronIdTest(WagtailPageTestCase):
    def test_extract_from_html(self):
        html = '<p>Intro</p><div id="disaron-nom">TbdBoi2602</div><p>Outro</p>'
        self.assertEqual(extract_disaron_id_from_html(html), "TbdBoi2602")

    def test_extract_from_html_missing(self):
        self.assertIsNone(extract_disaron_id_from_html("<p>No identifier</p>"))
        self.assertIsNone(extract_disaron_id_from_html(""))

    def test_extract_from_stream_data_html_block(self):
        stream = [
            {
                "type": "html",
                "value": '<div id="disaron-nom">TbdBoi2602</div>',
                "id": "block-1",
            }
        ]
        self.assertEqual(extract_disaron_id_from_stream_data(stream), "TbdBoi2602")

    def test_extract_from_stream_data_nested_multicolumns(self):
        stream = [
            {
                "type": "multicolumns",
                "value": {
                    "columns": [
                        {
                            "type": "column",
                            "value": {
                                "content": [
                                    {
                                        "type": "html",
                                        "value": '<div id="disaron-nom">NestedId99</div>',
                                    }
                                ]
                            },
                        }
                    ]
                },
                "id": "block-2",
            }
        ]
        self.assertEqual(extract_disaron_id_from_stream_data(stream), "NestedId99")

    def test_extract_from_stream_data_absent(self):
        stream = [{"type": "paragraph", "value": "<p>Hello</p>", "id": "block-3"}]
        self.assertIsNone(extract_disaron_id_from_stream_data(stream))


class PublicationPageDisaronIdTest(WagtailPageTestCase):
    def setUp(self):
        self.home = Page.objects.get(slug="home")
        self.admin = User.objects.create_superuser("test", "test@test.test", "pass")
        self.paris_tz = zoneinfo.ZoneInfo("Europe/Paris")
        self.index = self.home.add_child(
            instance=PublicationIndexPage(
                title="Publications",
                slug="publications-disaron",
                owner=self.admin,
            )
        )
        self.index.save_revision().publish()

    def test_settings_panels_include_disaron_id(self):
        def list_field_names(panels):
            names = []
            for panel in panels:
                if hasattr(panel, "field_name"):
                    names.append(panel.field_name)
                if hasattr(panel, "children"):
                    names.extend(list_field_names(panel.children))
            return names

        self.assertIn("disaron_id", list_field_names(PublicationPage.settings_panels))

    def test_empty_disaron_id_fails_full_clean(self):
        page = PublicationPage(
            title="Missing id",
            date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=self.paris_tz),
            owner=self.admin,
            disaron_id="",
        )
        self.index.add_child(instance=page)
        with self.assertRaises(ValidationError) as ctx:
            page.full_clean()
        self.assertIn("disaron_id", ctx.exception.message_dict)

    def test_duplicate_disaron_id_fails_full_clean(self):
        PublicationPageFactory(
            parent=self.index,
            owner=self.admin,
            disaron_id="shared-id",
        )
        duplicate = PublicationPage(
            title="Duplicate id",
            date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=self.paris_tz),
            owner=self.admin,
            disaron_id="shared-id",
        )
        self.index.add_child(instance=duplicate)
        with self.assertRaises(ValidationError) as ctx:
            duplicate.full_clean()
        self.assertIn("disaron_id", ctx.exception.message_dict)

    def test_valid_disaron_id_can_publish(self):
        page = PublicationPageFactory(
            parent=self.index,
            owner=self.admin,
            disaron_id="valid-disaron-id",
            publish=False,
        )
        page.save_revision().publish()
        page.refresh_from_db()
        self.assertTrue(page.live)
        self.assertEqual(page.disaron_id, "valid-disaron-id")
