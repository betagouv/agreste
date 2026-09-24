from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from wagtail.log_actions import registry as log_registry
from wagtail.models import Page
from wagtail.rich_text import RichText
from wagtail.test.utils import WagtailPageTestCase

from publications.migrations.batch_commands.search_description_backfill import (
    _iter_pages,
    _publish_description,
    pages_to_process,
)
from publications.models import PublicationIndexPage, PublicationPage
from sites_conformes.core.models import ContentPage

User = get_user_model()

LONG_TEXT = (
    "Le service de la statistique et de la prospective publie chaque année des données "
    "détaillées sur les productions agricoles françaises et leurs évolutions récentes."
)
DRAFT_TEXT = "Texte du brouillon, différent de la version publiée."


def _body(text=LONG_TEXT):
    return [("paragraph", RichText(f"<p>{text}</p>"))]


class RegenerateSearchDescriptionsTest(WagtailPageTestCase):
    def setUp(self):
        self.home = Page.objects.get(slug="home")
        self.admin = User.objects.create_superuser("test", "test@test.test", "pass")

    def _content_page(self, slug, *, live=True, **kwargs):
        kwargs.setdefault("body", _body())
        page = self.home.add_child(
            instance=ContentPage(
                title=slug.replace("-", " ").capitalize(),
                slug=slug,
                owner=self.admin,
                live=live,
                **kwargs,
            )
        )
        if live:
            page.save_revision().publish()
        return page.specific

    def _run(self, *args):
        stdout = StringIO()
        call_command("regenerate_search_descriptions", "--no-input", *args, stdout=stdout)
        return stdout.getvalue()

    def _reload(self, page):
        return type(page).objects.get(pk=page.pk)

    def _assert_shows_in_history(self, page, revision):
        # The History tab lists log entries, not revisions.
        self.assertTrue(log_registry.get_logs_for_instance(page).filter(revision=revision).exists())

    def test_existing_description_of_a_live_page_is_overwritten(self):
        page = self._content_page("live-page", search_description="Description à remplacer")

        output = self._run()

        self.assertEqual(self._reload(page).search_description, LONG_TEXT)
        self.assertIn(f"PUBLISHED: pk={page.pk}", output)

    def test_live_page_is_republished_with_a_new_revision(self):
        page = self._content_page("republished-page")
        revision_before = page.get_latest_revision()

        self._run()

        page = self._reload(page)
        self.assertNotEqual(page.get_latest_revision().pk, revision_before.pk)
        self.assertEqual(page.get_latest_revision().content["search_description"], LONG_TEXT)
        self.assertTrue(page.live)
        self.assertFalse(page.has_unpublished_changes)

    def test_generated_description_survives_the_legacy_save_hook(self):
        # ContentPage.save() still runs the legacy 20-word extractor, which must
        # not replace the description we just generated.
        page = self._content_page("content-page")
        self.assertIn("[…]", page.search_description)

        self._run()

        description = self._reload(page).search_description
        self.assertEqual(description, LONG_TEXT)
        self.assertNotIn("[…]", description)

    def test_publication_page_is_regenerated(self):
        index = self.home.add_child(
            instance=PublicationIndexPage(title="Publications", slug="publications", owner=self.admin)
        )
        index.save_revision().publish()
        page = index.add_child(
            instance=PublicationPage(
                title="Publication",
                slug="publication",
                owner=self.admin,
                body=_body(),
                search_description="Description à remplacer",
            )
        )
        page.save_revision().publish()

        self._run()

        self.assertEqual(PublicationPage.objects.get(pk=page.pk).search_description, LONG_TEXT)

    def test_not_live_page_without_revision_gets_a_first_revision_and_the_row(self):
        page = self._content_page("draft-page", live=False, search_description="Description à remplacer")
        self.assertIsNone(page.get_latest_revision())

        output = self._run()

        page = self._reload(page)
        revision = page.get_latest_revision()
        self.assertEqual(revision.content["search_description"], LONG_TEXT)
        self.assertEqual(page.search_description, LONG_TEXT)
        self.assertFalse(page.live)
        self._assert_shows_in_history(page, revision)
        self.assertIn(f"pk={page.pk} title='Draft page' type=sites_conformes_core.ContentPage", output)
        self.assertIn("reason=draft_saved_not_live", output)
        self.assertIn("draft_saved_not_live=1", output)

    def test_not_live_page_with_a_revision_uses_the_draft_content(self):
        page = self._content_page("draft-with-revision", live=False, search_description="Description à remplacer")
        page.title = "Brouillon en cours"
        page.body = _body(DRAFT_TEXT)
        draft_revision = page.save_revision()

        self._run()

        page = self._reload(page)
        revision = page.get_latest_revision()
        self.assertNotEqual(revision.pk, draft_revision.pk)
        self.assertEqual(revision.content["title"], "Brouillon en cours")
        self.assertEqual(revision.content["search_description"], DRAFT_TEXT)
        self.assertEqual(page.search_description, DRAFT_TEXT)
        # Only the description reaches the row, the rest of the draft stays in the revision.
        self.assertEqual(page.title, "Draft with revision")

    def test_live_page_with_a_pending_draft_keeps_its_draft(self):
        page = self._content_page("pending-draft-page", search_description="Description à remplacer")
        page.title = "Titre en cours de rédaction"
        draft_revision = page.save_revision()

        output = self._run()

        page = self._reload(page)
        revision = page.get_latest_revision()
        self.assertNotEqual(revision.pk, draft_revision.pk)
        self.assertEqual(revision.content["title"], "Titre en cours de rédaction")
        self.assertEqual(revision.content["search_description"], LONG_TEXT)
        # Nothing is published, so the live row keeps its description.
        self.assertEqual(page.search_description, "Description à remplacer")
        self.assertTrue(page.live)
        self.assertTrue(page.has_unpublished_changes)
        self._assert_shows_in_history(page, revision)
        self.assertIn("reason=draft_saved_pending", output)
        self.assertIn("draft_saved_pending=1", output)

    def test_pending_draft_description_comes_from_the_draft_body(self):
        page = self._content_page("draft-body-page", search_description="Description à remplacer")
        page.body = _body(DRAFT_TEXT)
        page.save_revision()

        self._run()

        page = self._reload(page)
        self.assertEqual(page.get_latest_revision().content["search_description"], DRAFT_TEXT)

    def test_a_second_run_does_not_add_another_revision_to_a_draft(self):
        page = self._content_page("twice-page", search_description="Description à remplacer")
        page.title = "Titre en cours de rédaction"
        page.save_revision()

        self._run()
        revision_after_first_run = self._reload(page).get_latest_revision()
        output = self._run()

        self.assertEqual(self._reload(page).get_latest_revision().pk, revision_after_first_run.pk)
        self.assertIn("draft_saved_pending=0", output)

    def test_alias_page_is_skipped(self):
        source = self._content_page("aliased-page")
        alias = source.create_alias(parent=self.home, update_slug="alias-page")

        output = self._run()

        self.assertIn(f"pk={alias.pk}", output)
        self.assertIn("reason=alias", output)
        self.assertIn("skipped_alias=1", output)

    def test_page_without_extractable_text_is_skipped(self):
        page = self._content_page("empty-page", body=[], search_description="Description à garder")

        output = self._run()

        self.assertEqual(self._reload(page).search_description, "Description à garder")
        self.assertIn("reason=empty", output)

    def test_dry_run_does_not_write(self):
        page = self._content_page("dry-run-page", search_description="Description à remplacer")
        revision_before = page.get_latest_revision()

        output = self._run("--dry-run")

        page = self._reload(page)
        self.assertEqual(page.search_description, "Description à remplacer")
        self.assertEqual(page.get_latest_revision().pk, revision_before.pk)
        self.assertIn("[dry-run] PUBLISHED", output)

    def test_failure_on_one_page_is_rolled_back_and_the_run_continues(self):
        failing = self._content_page("failing-page", search_description="Description à remplacer")
        following = self._content_page("following-page", search_description="Description à remplacer")

        def publish_then_fail(page, description):
            _publish_description(page, description)
            if page.pk == failing.pk:
                raise RuntimeError("boom")

        with patch(
            "publications.migrations.batch_commands.search_description_backfill._publish_description",
            side_effect=publish_then_fail,
        ):
            with self.assertLogs("publications.migrations.batch_commands.search_description_backfill", level="ERROR"):
                with self.assertRaises(CommandError):
                    self._run()

        self.assertEqual(self._reload(failing).search_description, "Description à remplacer")
        self.assertEqual(self._reload(following).search_description, LONG_TEXT)

    def test_page_type_filter_limits_the_run(self):
        content_page = self._content_page("filtered-out-page", search_description="Description à remplacer")

        self._run("--page-type", "publications.PublicationPage")

        self.assertEqual(self._reload(content_page).search_description, "Description à remplacer")

    def test_unknown_page_type_is_rejected(self):
        with self.assertRaises(CommandError):
            self._run("--page-type", "core.NoSuchPage")

    def test_pages_are_walked_once_across_chunks(self):
        expected = [self._content_page(f"chunked-page-{index}").pk for index in range(3)]

        walked = [page.pk for page in _iter_pages(pages_to_process(), chunk_size=1)]

        self.assertEqual(len(walked), len(set(walked)))
        for pk in expected:
            self.assertIn(pk, walked)
