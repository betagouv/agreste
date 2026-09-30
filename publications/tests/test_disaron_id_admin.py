from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase

from publications.models import PublicationIndexPage, PublicationPage

User = get_user_model()


class DisaronIdAdminTest(WagtailPageTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("test", "test@test.test", "pass")
        self.client.login(username="test", password="pass")
        home = Page.objects.get(slug="home")
        self.index = home.add_child(
            instance=PublicationIndexPage(title="Publications", slug="publications", owner=self.admin)
        )
        self.index.save_revision().publish()
        self.matching = self.index.add_child(
            instance=PublicationPage(
                title="Bulletin grandes cultures",
                slug="bulletin",
                owner=self.admin,
                disaron_id="IraAbo2623",
            )
        )
        self.matching.save_revision().publish()
        self.other = self.index.add_child(
            instance=PublicationPage(
                title="Autre publication",
                slug="autre",
                owner=self.admin,
                disaron_id="AutreId0001",
            )
        )
        self.other.save_revision().publish()

    def test_publication_index_lists_disaron_id(self):
        response = self.client.get(reverse("wagtailadmin_explore", args=[self.index.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Identifiant disaron")
        self.assertContains(response, "IraAbo2623")
        self.assertContains(response, "AutreId0001")

        home = Page.objects.get(slug="home")
        home_listing = self.client.get(reverse("wagtailadmin_explore", args=[home.pk]))
        self.assertEqual(home_listing.status_code, 200)
        self.assertNotContains(home_listing, "Identifiant disaron")

    def test_listing_can_be_sorted_by_disaron_id(self):
        ascending = self.client.get(
            reverse("wagtailadmin_explore", args=[self.index.pk]),
            {"ordering": "disaron_id"},
        )
        self.assertEqual(ascending.status_code, 200)
        ascending_content = ascending.content.decode()
        self.assertLess(ascending_content.index("AutreId0001"), ascending_content.index("IraAbo2623"))

        descending = self.client.get(
            reverse("wagtailadmin_explore", args=[self.index.pk]),
            {"ordering": "-disaron_id"},
        )
        self.assertEqual(descending.status_code, 200)
        descending_content = descending.content.decode()
        self.assertLess(descending_content.index("IraAbo2623"), descending_content.index("AutreId0001"))

        call_command("update_index")
        searched = self.client.get(
            reverse("wagtailadmin_explore", args=[self.index.pk]),
            {"q": "IraAbo2623", "ordering": "disaron_id"},
        )
        self.assertEqual(searched.status_code, 200)
        self.assertContains(searched, self.matching.title)
        self.assertNotContains(searched, self.other.title)

    def test_admin_search_finds_a_publication_by_disaron_id(self):
        call_command("update_index")

        response = self.client.get(reverse("wagtailadmin_explore", args=[self.index.pk]), {"q": "IraAbo2623"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.matching.title)
        self.assertNotContains(response, self.other.title)
