from io import StringIO

from django.core.management import call_command
from wagtail.models import Locale, Page
from wagtail.test.utils import WagtailPageTestCase

from publications.models import PublicationPage
from publications.tests.factories import PublicationIndexPageFactory, PublicationPageFactory, ThemeFactory


class AddParentThemesTest(WagtailPageTestCase):
    def setUp(self):
        self.home = Page.objects.get(slug="home")
        self.index = PublicationIndexPageFactory(parent=self.home)
        self.locale = Locale.get_default()

    def _theme(self, name, parent=None):
        return ThemeFactory(locale=self.locale, name=name, parent=parent)

    def _page(self, slug, themes, **kwargs):
        page = PublicationPageFactory(parent=self.index, slug=slug, title=slug, themes=themes, **kwargs)
        page.save_revision().publish()
        return page

    def _run(self, *args):
        stdout = StringIO()
        call_command("add_parent_themes", "--no-input", *args, stdout=stdout)
        return stdout.getvalue()

    def _theme_pks(self, page):
        return set(PublicationPage.objects.get(pk=page.pk).themes.values_list("pk", flat=True))

    def test_grandchild_gets_parent_and_grandparent(self):
        root = self._theme("Environment")
        parent = self._theme("Climate", parent=root)
        child = self._theme("Drought", parent=parent)
        page = self._page("drought-page", [child])

        output = self._run()

        self.assertEqual(self._theme_pks(page), {child.pk, parent.pk, root.pk})
        self.assertFalse(PublicationPage.objects.get(pk=page.pk).has_unpublished_changes)
        self.assertIn("themes=Drought", output)
        self.assertIn("Climate, Environment", output)
        self.assertIn("published=1", output)

    def test_root_theme_is_unchanged(self):
        root = self._theme("Environment")
        page = self._page("root-page", [root])
        revision_before = page.get_latest_revision()

        output = self._run()

        self.assertEqual(self._theme_pks(page), {root.pk})
        self.assertEqual(PublicationPage.objects.get(pk=page.pk).get_latest_revision().pk, revision_before.pk)
        self.assertIn("unchanged=1", output)

    def test_page_that_already_has_its_parent_is_unchanged(self):
        root = self._theme("Environment")
        parent = self._theme("Climate", parent=root)
        child = self._theme("Drought", parent=parent)
        page = self._page("already-tagged", [child, parent, root])
        revision_before = page.get_latest_revision()

        self._run()

        self.assertEqual(self._theme_pks(page), {child.pk, parent.pk, root.pk})
        self.assertEqual(PublicationPage.objects.get(pk=page.pk).get_latest_revision().pk, revision_before.pk)

    def test_shared_ancestor_is_added_once(self):
        parent = self._theme("Climate")
        child_a = self._theme("Drought", parent=parent)
        child_b = self._theme("Flood", parent=parent)
        page = self._page("shared-parent", [child_a, child_b])

        self._run()

        self.assertEqual(self._theme_pks(page), {child_a.pk, child_b.pk, parent.pk})
        self.assertEqual(page.themes.through.objects.filter(page_id=page.pk, theme=parent).count(), 1)

    def test_dry_run_does_not_write(self):
        root = self._theme("Environment")
        child = self._theme("Drought", parent=root)
        page = self._page("dry-run-page", [child])
        revision_before = page.get_latest_revision()

        output = self._run("--dry-run")

        self.assertEqual(self._theme_pks(page), {child.pk})
        self.assertEqual(PublicationPage.objects.get(pk=page.pk).get_latest_revision().pk, revision_before.pk)
        self.assertIn("[dry-run] PUBLISHED", output)
        self.assertIn("Environment", output)

    def test_pending_draft_is_saved_and_not_published(self):
        root = self._theme("Environment")
        child = self._theme("Drought", parent=root)
        page = self._page("pending-draft", [child])
        page.title = "Titre en cours"
        draft_revision = page.save_revision()

        output = self._run()

        page = PublicationPage.objects.get(pk=page.pk)
        revision = page.get_latest_revision()
        self.assertNotEqual(revision.pk, draft_revision.pk)
        self.assertEqual(revision.as_object().title, "Titre en cours")
        # modelcluster's in-memory queryset has `id`, not `pk`.
        self.assertEqual(set(revision.as_object().themes.values_list("id", flat=True)), {child.pk, root.pk})
        self.assertEqual(self._theme_pks(page), {child.pk})
        self.assertTrue(page.live)
        self.assertTrue(page.has_unpublished_changes)
        self.assertIn("reason=draft_saved_pending", output)

    def test_second_run_adds_nothing(self):
        root = self._theme("Environment")
        child = self._theme("Drought", parent=root)
        page = self._page("twice", [child])

        self._run()
        revision_after_first_run = PublicationPage.objects.get(pk=page.pk).get_latest_revision()
        output = self._run()

        self.assertEqual(
            PublicationPage.objects.get(pk=page.pk).get_latest_revision().pk,
            revision_after_first_run.pk,
        )
        self.assertIn("published=0", output)
        self.assertIn("unchanged=1", output)


class MissingAncestorsTest(WagtailPageTestCase):
    def test_locale_mismatch_stops_the_chain(self):
        from publications.migrations.batch_commands.batch_add_parent_themes import missing_ancestors

        default = Locale.get_default()
        other = Locale.objects.create(language_code="en")
        foreign = ThemeFactory(locale=other, name="Foreign root")
        parent = ThemeFactory(locale=default, name="Climate", parent=foreign)
        child = ThemeFactory(locale=default, name="Drought", parent=parent)

        self.assertEqual(missing_ancestors([child]), [parent])

    def test_cycle_stops_the_walk(self):
        from publications.migrations.batch_commands.batch_add_parent_themes import missing_ancestors

        locale = Locale.get_default()
        parent = ThemeFactory(locale=locale, name="Climate")
        child = ThemeFactory(locale=locale, name="Drought", parent=parent)
        parent.parent = child
        parent.save(update_fields=["parent"])
        child.refresh_from_db()

        self.assertEqual(missing_ancestors([child]), [parent])
