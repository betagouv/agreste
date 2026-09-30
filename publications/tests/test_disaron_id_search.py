from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from wagtail.models import Page
from wagtail.test.utils import WagtailPageTestCase

from publications.models import PublicationIndexPage, PublicationPage

User = get_user_model()


class DisaronIdSearchTest(WagtailPageTestCase):
    def test_search_finds_a_publication_by_disaron_id(self):
        home = Page.objects.get(slug="home")
        admin = User.objects.create_superuser("test", "test@test.test", "pass")
        index = home.add_child(instance=PublicationIndexPage(title="Publications", slug="publications", owner=admin))
        index.save_revision().publish()

        matching = index.add_child(
            instance=PublicationPage(
                title="Bulletin grandes cultures",
                slug="bulletin",
                owner=admin,
                disaron_id="TbdCpr2602",
            )
        )
        matching.save_revision().publish()
        other = index.add_child(
            instance=PublicationPage(
                title="Autre publication",
                slug="autre",
                owner=admin,
                disaron_id="AutreId0001",
            )
        )
        other.save_revision().publish()
        call_command("update_index")

        response = self.client.get(f"{reverse('cms_search')}?q=TbdCpr2602")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, matching.title)
        self.assertNotContains(response, other.title)
