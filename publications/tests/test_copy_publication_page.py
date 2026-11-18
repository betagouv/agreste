from django.contrib.auth import get_user_model
from django.urls import reverse
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase

from publications.models import PublicationIndexPage, PublicationPage

User = get_user_model()


class CopyPublicationPageTest(WagtailPageTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("test", "test@test.test", "pass")
        self.client.login(username="test", password="pass")
        home = Page.objects.get(slug="home")
        self.index = home.add_child(
            instance=PublicationIndexPage(title="Publications", slug="publications", owner=self.admin)
        )
        self.index.save_revision().publish()
        self.page = self.index.add_child(
            instance=PublicationPage(
                title="Bulletin grandes cultures",
                slug="bulletin",
                owner=self.admin,
                disaron_id="IraAbo2623",
            )
        )
        self.page.save_revision().publish()
        self.page.title = "Bulletin revised"
        self.page.save_revision()
        self.other = self.index.add_child(
            instance=PublicationPage(
                title="Autre publication",
                slug="autre",
                owner=self.admin,
                disaron_id="AutreId0001",
            )
        )
        self.other.save_revision().publish()

    def copy_url(self):
        return reverse("wagtailadmin_pages:copy", args=[self.page.pk])

    def post_copy(self, disaron_id, slug="bulletin-copie"):
        return self.client.post(
            self.copy_url(),
            {
                "new_title": "Bulletin copié",
                "new_slug": slug,
                "new_parent_page": self.index.pk,
                "new_disaron_id": disaron_id,
            },
        )

    def test_copy_form_asks_for_a_new_disaron_id(self):
        response = self.client.get(self.copy_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nouvel identifiant Disaron")
        self.assertContains(response, 'name="new_disaron_id"')
        self.assertContains(response, 'value="IraAbo2623"')

    def test_copy_saves_the_submitted_disaron_id_on_the_page_and_its_revisions(self):
        response = self.post_copy("  CopiedId0001  ")

        self.assertEqual(response.status_code, 302)
        copy = PublicationPage.objects.get(slug="bulletin-copie")
        self.assertEqual(copy.disaron_id, "CopiedId0001")
        self.page.refresh_from_db()
        self.assertEqual(self.page.disaron_id, "IraAbo2623")

        copied_revisions = list(copy.revisions.all())
        self.assertGreaterEqual(len(copied_revisions), 2)
        for revision in copied_revisions:
            self.assertEqual(revision.content["disaron_id"], "CopiedId0001")
        for revision in self.page.revisions.all():
            self.assertEqual(revision.content["disaron_id"], "IraAbo2623")

    def test_copy_rejects_a_disaron_id_that_already_exists(self):
        cases = [
            ("IraAbo2623", "copie-identique", "Une publication avec cet identifiant Disaron existe déjà."),
            ("AutreId0001", "copie-autre", "Une publication avec cet identifiant Disaron existe déjà."),
            ("   ", "copie-vide", "Ce champ ne peut pas être vide."),
        ]
        for disaron_id, slug, message in cases:
            with self.subTest(disaron_id=disaron_id):
                before = PublicationPage.objects.count()
                response = self.post_copy(disaron_id, slug=slug)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.assertEqual(PublicationPage.objects.count(), before)
