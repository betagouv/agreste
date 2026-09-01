import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase

from publications.migrations.data_migrations.migrate_to_standard_publications import (
    EXAMPLES_DIR,
    MULTICOLUMNS_BLOCK,
    STANDARD_PUBLICATION_BLOCK,
    _migrate_page_body,
    run_migration,
    transform_body_stream,
    try_convert_multicolumns_block,
)


def _load_example(name: str) -> list:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


class FakeStreamField:
    def __init__(self, data: list):
        self._data = data

    @property
    def raw_data(self):
        return self._data


class FakePage:
    def __init__(self, stream_data: list, *, pk: int = 1, url: str = "/publications/test/"):
        self.pk = pk
        self.url = url
        self.body = FakeStreamField(stream_data)
        self.saved = False
        self.revisions = MagicMock()
        self.revisions.all.return_value.iterator.return_value = []

    def save(self, update_fields=None):
        self.saved = True


class MulticolumnsToStandardPublicationTransformTest(SimpleTestCase):
    def test_migrates_full_example_with_subtitle_and_summary(self):
        stream_data = _load_example("should_migrate.json")
        transformed, results = transform_body_stream(stream_data)

        self.assertEqual([result.action for result in results], ["migrated"])
        standard_publication = transformed[0]
        self.assertEqual(standard_publication["type"], STANDARD_PUBLICATION_BLOCK)
        self.assertEqual(standard_publication["value"]["subtitle"], "Veille technologique")
        self.assertIn("agriculture en environnement contrôlé", standard_publication["value"]["summary"])
        self.assertEqual(
            standard_publication["value"]["downloadable_documents"],
            [{"download_type": "publication", "document": 101}],
        )
        self.assertEqual(transformed[1:], stream_data[1:])

    def test_migrates_without_complement_titre(self):
        stream_data = _load_example("should_migrate_no_complement_titre.json")
        transformed, results = transform_body_stream(stream_data)

        self.assertEqual([result.action for result in results], ["migrated"])
        value = transformed[0]["value"]
        self.assertEqual(value["subtitle"], "")
        self.assertIn("Au sommaire de ce bulletin", value["summary"])
        self.assertEqual(value["downloadable_documents"], [{"download_type": "publication", "document": 102}])

    def test_migrates_without_chapeau_and_maps_both_download_types(self):
        stream_data = _load_example("should_migrate_no_chapeau.json")
        transformed, results = transform_body_stream(stream_data)

        self.assertEqual([result.action for result in results], ["migrated"])
        value = transformed[0]["value"]
        self.assertEqual(value["subtitle"], "Centre-Val de Loire")
        self.assertEqual(value["summary"], "")
        self.assertEqual(
            value["downloadable_documents"],
            [
                {"download_type": "publication", "document": 103},
                {"download_type": "data", "document": 104},
            ],
        )

    def test_skips_non_matching_multicolumns(self):
        stream_data = _load_example("should_not_migrate.json")
        transformed, results = transform_body_stream(stream_data)

        self.assertEqual(transformed, stream_data)
        self.assertEqual(results[0].action, "skipped")
        self.assertIn("non-html blocks", results[0].reason)

    def test_try_convert_returns_reason_for_invalid_block(self):
        converted, reason = try_convert_multicolumns_block({"type": "paragraph", "value": "nope"})
        self.assertIsNone(converted)
        self.assertEqual(reason, "not a multicolumns block")


class MigratePageBodyTest(SimpleTestCase):
    def test_dry_run_does_not_save(self):
        page = FakePage(_load_example("should_migrate.json"))
        result = _migrate_page_body(page, dry_run=True)

        self.assertFalse(page.saved)
        self.assertEqual(list(page.body.raw_data)[0]["type"], MULTICOLUMNS_BLOCK)
        self.assertEqual(result.migrated_count, 1)

    def test_persists_matching_page(self):
        page = FakePage(_load_example("should_migrate.json"))
        result = _migrate_page_body(page, dry_run=False)

        self.assertTrue(page.saved)
        self.assertEqual(page.body[0]["type"], STANDARD_PUBLICATION_BLOCK)
        self.assertEqual(page.body[0]["value"]["subtitle"], "Veille technologique")
        self.assertEqual(result.migrated_count, 1)

    def test_leaves_non_matching_page_unchanged(self):
        stream_data = _load_example("should_not_migrate.json")
        multicolumns_only = [block for block in stream_data if block["type"] == MULTICOLUMNS_BLOCK]
        page = FakePage(multicolumns_only)
        result = _migrate_page_body(page, dry_run=False)

        self.assertFalse(page.saved)
        self.assertEqual(list(page.body.raw_data), multicolumns_only)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.migrated_count, 0)


class RunMigrationTest(TestCase):
    def test_run_migration_aggregates_results(self):
        pages = [
            FakePage(_load_example("should_migrate.json"), pk=1, url="/one/"),
            FakePage(
                [block for block in _load_example("should_not_migrate.json") if block["type"] == MULTICOLUMNS_BLOCK],
                pk=2,
                url="/two/",
            ),
        ]

        summary = run_migration(pages, dry_run=True)

        self.assertEqual(summary.pages_scanned, 2)
        self.assertEqual(summary.pages_changed, 1)
        self.assertEqual(summary.blocks_migrated, 1)
        self.assertEqual(summary.blocks_skipped, 1)


class MigrateToStandardPublicationsCommandTest(TestCase):
    @patch("publications.management.commands.migrate_to_standard_publications.run_migration")
    def test_command_calls_run_migration_with_dry_run(self, run_migration_mock):
        from django.core.management import call_command

        run_migration_mock.return_value.pages_scanned = 0
        run_migration_mock.return_value.pages_changed = 0
        run_migration_mock.return_value.blocks_migrated = 0
        run_migration_mock.return_value.blocks_skipped = 0
        run_migration_mock.return_value.page_results = []

        call_command(
            "migrate_to_standard_publications",
            "--dry-run",
            "--no-input",
            "--no-log-file",
        )

        run_migration_mock.assert_called_once()
        self.assertTrue(run_migration_mock.call_args.kwargs["dry_run"])
