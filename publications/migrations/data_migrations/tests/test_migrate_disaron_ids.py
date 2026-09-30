import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase
from wagtail.models import Page
from wagtail.rich_text import RichText
from wagtail.test.utils import WagtailPageTestCase

from publications.migrations.data_migrations.migrate_disaron_ids import (
    FOUND,
    MISSING,
    SKIPPED,
    _apply as apply_migration,
    assess_page,
    run_migration,
    transform_top_level_body,
)
from publications.models import PublicationIndexPage, PublicationPage

User = get_user_model()
EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _load_example(name: str) -> list:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def _disaron_block(disaron_id: str) -> tuple[str, str]:
    return ("html", f'<div id="disaron-nom">{disaron_id}</div>')


def _live_page(pk, title, body, disaron_id=None):
    return SimpleNamespace(
        pk=pk,
        title=title,
        alias_of_id=None,
        disaron_id=disaron_id,
        live=True,
        has_unpublished_changes=False,
        body=SimpleNamespace(raw_data=body),
    )


class TransformDisaronBlockTest(SimpleTestCase):
    def test_example_body_keeps_multicolumns_and_drops_the_html_block(self):
        stream_data = _load_example("should_migrate.json")

        extract = transform_top_level_body(stream_data)

        self.assertEqual(extract.disaron_id, "PUB-EXAMPLE-01")
        self.assertIsNone(extract.error)
        self.assertEqual(extract.removed_blocks, 1)
        self.assertEqual(len(extract.body), 1)
        self.assertEqual(extract.body[0]["type"], "multicolumns")
        self.assertNotIn("disaron-nom", json.dumps(extract.body))

    def test_whitespace_around_the_div_is_accepted(self):
        extract = transform_top_level_body(
            [{"type": "html", "value": '\n  <div id="disaron-nom">TbdCpr2602</div>\n'}]
        )

        self.assertEqual(extract.disaron_id, "TbdCpr2602")
        self.assertEqual(extract.body, [])
        self.assertIsNone(extract.error)

    def test_other_markup_is_an_error_and_the_block_stays(self):
        block = {"type": "html", "value": '<p>note</p><div id="disaron-nom">TbdCpr2602</div>'}

        extract = transform_top_level_body([block])

        self.assertEqual(extract.body, [block])
        self.assertEqual(extract.removed_blocks, 0)
        self.assertIn("other markup", extract.error)
        self.assertEqual(extract.disaron_id, "TbdCpr2602")

    def test_empty_div_is_an_error(self):
        block = {"type": "html", "value": '<div id="disaron-nom"></div>'}

        extract = transform_top_level_body([block])

        self.assertEqual(extract.body, [block])
        self.assertIn("empty", extract.error)

    def test_nested_disaron_div_is_ignored(self):
        stream_data = [
            {
                "type": "multicolumns",
                "value": {
                    "columns": [
                        {
                            "type": "column",
                            "value": {
                                "content": [
                                    {"type": "html", "value": '<div id="disaron-nom">NestedId</div>'}
                                ]
                            },
                        }
                    ]
                },
            }
        ]

        extract = transform_top_level_body(stream_data)

        self.assertIsNone(extract.disaron_id)
        self.assertIsNone(extract.error)
        self.assertEqual(extract.body, stream_data)

    def test_alias_page_is_skipped(self):
        page = SimpleNamespace(pk=4, title="Alias", alias_of_id=9)

        assessment, _payload = assess_page(page)

        self.assertEqual(assessment.action, SKIPPED)
        self.assertIn("disaron_id=''", assessment.describe())
        self.assertLess(assessment.describe().index("disaron_id="), assessment.describe().index("title="))

    def test_missing_id_is_logged_and_a_duplicate_does_not_stop_the_other_page(self):
        missing = _live_page(1, "Sans identifiant", [{"type": "paragraph", "value": "x"}])
        first = _live_page(2, "Première", [{"type": "html", "value": '<div id="disaron-nom">SameId0001</div>'}])
        second = _live_page(3, "Seconde", [{"type": "html", "value": '<div id="disaron-nom">SameId0001</div>'}])
        other = _live_page(4, "Autre", [{"type": "html", "value": '<div id="disaron-nom">OtherId0001</div>'}])
        log = StringIO()

        summary = run_migration([missing, first, second, other], dry_run=True, log_file=log)

        text = log.getvalue()
        self.assertEqual(assess_page(missing)[0].action, MISSING)
        self.assertIn("MISSING pk=1 disaron_id='' title='Sans identifiant'", text)
        self.assertIn("CONFLICT pk=3 disaron_id='SameId0001' title='Seconde' also_on pk=2", text)
        self.assertIn("FOUND pk=4 disaron_id='OtherId0001'", text)
        self.assertEqual(summary.written, 0)


class MigrateDisaronIdsTest(WagtailPageTestCase):
    def setUp(self):
        self.home = Page.objects.get(slug="home")
        self.admin = User.objects.create_superuser("test", "test@test.test", "pass")
        self.index = self.home.add_child(
            instance=PublicationIndexPage(title="Publications", slug="publications", owner=self.admin)
        )
        self.index.save_revision().publish()

    def _page(self, slug, title, body, disaron_id, *, live=True):
        page = self.index.add_child(
            instance=PublicationPage(
                title=title,
                slug=slug,
                owner=self.admin,
                body=body,
                live=live,
                disaron_id=disaron_id,
            )
        )
        if live:
            page.save_revision().publish()
        return page

    def _run(self, *args):
        stdout = StringIO()
        call_command("migrate_disaron_ids", "--no-input", "--no-log-file", *args, stdout=stdout)
        return stdout.getvalue()

    def _reload(self, page):
        return PublicationPage.objects.get(pk=page.pk)

    def _html_values(self, page):
        return [block.value for block in page.body if block.block_type == "html"]

    def test_sets_the_id_removes_the_block_and_logs_found_before_title(self):
        page = self._page(
            "with-id",
            "Bulletin",
            [("paragraph", RichText("<p>Intro</p>")), _disaron_block("TbdCpr2602")],
            "TbdCpr2602",
        )

        output = self._run()

        page = self._reload(page)
        self.assertEqual(page.disaron_id, "TbdCpr2602")
        self.assertEqual(self._html_values(page), [])
        self.assertIn("Intro", str(page.body))
        line = next(line for line in output.splitlines() if line.startswith("FOUND"))
        self.assertIn(f"pk={page.pk}", line)
        self.assertIn("disaron_id='TbdCpr2602'", line)
        self.assertIn("title='Bulletin'", line)
        self.assertLess(line.index("disaron_id="), line.index("title="))
        self.assertIn("removed_blocks=1", line)
        saved = next(line for line in output.splitlines() if line.startswith("SAVED"))
        self.assertIn(f"pk={page.pk}", saved)
        self.assertLess(saved.index("disaron_id="), saved.index("title="))
        self.assertLess(output.index("SAVING"), output.index("SAVED"))
        self.assertEqual(page.get_latest_revision().content["disaron_id"], "TbdCpr2602")

    def test_invalid_block_is_left_unchanged_while_another_page_is_written(self):
        invalid = self._page(
            "invalid",
            "Invalide",
            [("html", '<div id="disaron-nom">BadId0001</div><p>extra</p>')],
            "KeepInvalid1",
        )
        valid = self._page("valid", "Valide", [_disaron_block("GoodId0001")], "GoodId0001")

        output = self._run()

        self.assertEqual(self._reload(invalid).disaron_id, "KeepInvalid1")
        self.assertIn("extra", self._html_values(self._reload(invalid))[0])
        self.assertEqual(self._reload(valid).disaron_id, "GoodId0001")
        self.assertEqual(self._html_values(self._reload(valid)), [])
        self.assertIn(f"CONFLICT pk={invalid.pk} disaron_id='BadId0001' title='Invalide'", output)
        self.assertIn("other markup", output)

    def test_dry_run_logs_and_does_not_write(self):
        page = self._page("dry", "Brouillon sec", [_disaron_block("DryId00001")], "DryId00001")
        revision_before = page.get_latest_revision()

        output = self._run("--dry-run")

        page = self._reload(page)
        self.assertEqual(page.disaron_id, "DryId00001")
        self.assertEqual(page.get_latest_revision().pk, revision_before.pk)
        self.assertIn("disaron-nom", self._html_values(page)[0])
        self.assertIn(f"FOUND pk={page.pk} disaron_id='DryId00001'", output)
        self.assertNotIn("SAVING", output)
        self.assertNotIn("SAVED", output)
        self.assertIn("written: 0", output)

    def test_live_page_with_a_pending_draft_updates_both_and_keeps_the_draft(self):
        page = self._page("pending", "Publié", [_disaron_block("DraftId0001")], "DraftId0001")
        page.title = "Brouillon en cours"
        page.body = [("paragraph", RichText("<p>Note de brouillon</p>")), _disaron_block("DraftId0001")]
        draft_revision = page.save_revision()

        self._run()

        page = self._reload(page)
        self.assertEqual(page.disaron_id, "DraftId0001")
        self.assertEqual(self._html_values(page), [])
        self.assertEqual(page.title, "Publié")
        revision = page.get_latest_revision()
        self.assertNotEqual(revision.pk, draft_revision.pk)
        self.assertEqual(revision.content["title"], "Brouillon en cours")
        self.assertEqual(revision.content["disaron_id"], "DraftId0001")
        draft_body = str(revision.content["body"])
        self.assertNotIn("disaron-nom", draft_body)
        self.assertIn("Note de brouillon", draft_body)
        self.assertTrue(page.has_unpublished_changes)

    def test_failure_on_one_page_is_rolled_back_and_the_next_page_is_written(self):
        failing = self._page("fails", "Échec", [_disaron_block("FailId0001")], "FailId0001")
        following = self._page("follows", "Suite", [_disaron_block("NextId0001")], "NextId0001")

        def apply_then_fail(page, assessment):
            apply_migration(page, assessment)
            if page.pk == failing.pk:
                raise RuntimeError("boom")

        with patch(
            "publications.migrations.data_migrations.migrate_disaron_ids._apply",
            side_effect=apply_then_fail,
        ):
            with self.assertLogs("publications.migrations.data_migrations.migrate_disaron_ids", level="ERROR"):
                with self.assertRaises(CommandError):
                    self._run()

        self.assertEqual(self._reload(failing).disaron_id, "FailId0001")
        self.assertIn("disaron-nom", self._html_values(self._reload(failing))[0])
        self.assertEqual(self._reload(following).disaron_id, "NextId0001")
        self.assertEqual(self._html_values(self._reload(following)), [])

    def test_log_file_records_found_and_missing(self):
        self._page("logged", "Journal", [_disaron_block("LogId00001")], "LogId00001")

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "migrate.log"
            call_command(
                "migrate_disaron_ids",
                "--no-input",
                "--log-file",
                str(path),
            )
            text = path.read_text(encoding="utf-8")

        self.assertIn("disaron_id='LogId00001'", text)
        self.assertLess(text.index("disaron_id="), text.index("title="))


class RunMigrationDirectTest(WagtailPageTestCase):
    def test_run_migration_counts(self):
        home = Page.objects.get(slug="home")
        admin = User.objects.create_superuser("test", "test@test.test", "pass")
        index = home.add_child(instance=PublicationIndexPage(title="Publications", slug="pub-index", owner=admin))
        index.save_revision().publish()
        index.add_child(
            instance=PublicationPage(
                title="Une",
                slug="une",
                owner=admin,
                body=[_disaron_block("CountId0001")],
                disaron_id="CountId0001",
            )
        ).save_revision().publish()

        summary = run_migration(PublicationPage.objects.order_by("pk"), dry_run=True, log_file=StringIO())

        self.assertEqual(summary.pages_scanned, 1)
        self.assertEqual(summary.found, 1)
        self.assertEqual(summary.missing, 0)
        self.assertEqual(summary.written, 0)
        self.assertEqual(summary.assessments[0].action, FOUND)
