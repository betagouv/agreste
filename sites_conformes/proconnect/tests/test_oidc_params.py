import json

from django.test import SimpleTestCase

from sites_conformes.proconnect.oidc_params import (
    PROCONNECT_MFA_ACR_VALUES,
    oidc_auth_request_extra_params,
)


class OidcAuthRequestExtraParamsTest(SimpleTestCase):
    def test_default_uses_acr_values(self):
        self.assertEqual(
            oidc_auth_request_extra_params(require_mfa=False),
            {"acr_values": "eidas1"},
        )

    def test_mfa_sends_claims_json_string(self):
        params = oidc_auth_request_extra_params(require_mfa=True)

        self.assertNotIn("acr_values", params)
        claims = json.loads(params["claims"])
        acr = claims["id_token"]["acr"]
        self.assertTrue(acr["essential"])
        self.assertEqual(acr["values"], list(PROCONNECT_MFA_ACR_VALUES))
