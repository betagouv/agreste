import re
import unittest
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse


@unittest.skipUnless(
    settings.PROCONNECT_ACTIVATED,
    "ProConnect URLs are only registered when PROCONNECT_ACTIVATED is True.",
)
@override_settings(PROCONNECT_ACTIVATED=True)
class ProConnectLoginNextTest(TestCase):
    def _proconnect_href(self, response):
        match = re.search(r'<a class="fr-connect" href="([^"]+)"', response.content.decode())
        self.assertIsNotNone(match, "ProConnect login link was not found")
        return match.group(1)

    def test_proconnect_link_preserves_next(self):
        next_url = "/cms-admin/pages/"
        response = self.client.get(reverse("wagtailadmin_login"), {"next": next_url})

        self.assertEqual(response.status_code, 200)
        parsed = urlparse(self._proconnect_href(response))
        self.assertEqual(parsed.path, reverse("oidc_authentication_init"))
        self.assertEqual(parse_qs(parsed.query)["next"], [next_url])

    def test_proconnect_link_defaults_to_admin_home(self):
        response = self.client.get(reverse("wagtailadmin_login"))

        self.assertEqual(response.status_code, 200)
        parsed = urlparse(self._proconnect_href(response))
        self.assertEqual(parse_qs(parsed.query)["next"], [reverse("wagtailadmin_home")])
