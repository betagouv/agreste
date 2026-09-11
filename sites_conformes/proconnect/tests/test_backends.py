from unittest.mock import MagicMock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import SuspiciousOperation
from django.test import RequestFactory, TestCase, override_settings

from sites_conformes.proconnect.backends import OIDCAuthenticationBackend
from sites_conformes.proconnect.oidc_params import PROCONNECT_MFA_ACR_VALUES


class VerifyMfaAcrTest(TestCase):
    def setUp(self):
        self.backend = OIDCAuthenticationBackend()
        request = RequestFactory().get("/")
        request.session = {}
        request._messages = FallbackStorage(request)
        self.backend.request = request

    @override_settings(PROCONNECT_REQUIRE_MFA=False)
    def test_skipped_when_mfa_not_required(self):
        self.backend.verify_mfa_acr({"acr": "eidas1"})

    @override_settings(PROCONNECT_REQUIRE_MFA=True, PROCONNECT_MFA_ACR_VALUES=PROCONNECT_MFA_ACR_VALUES)
    def test_accepts_mfa_acr(self):
        self.backend.verify_mfa_acr({"acr": "eidas1-mfa"})

    @override_settings(PROCONNECT_REQUIRE_MFA=True, PROCONNECT_MFA_ACR_VALUES=PROCONNECT_MFA_ACR_VALUES)
    def test_rejects_password_only_acr(self):
        with self.assertRaises(SuspiciousOperation):
            self.backend.verify_mfa_acr({"acr": "eidas1"})

    @override_settings(PROCONNECT_REQUIRE_MFA=True, PROCONNECT_MFA_ACR_VALUES=PROCONNECT_MFA_ACR_VALUES)
    def test_rejects_missing_acr(self):
        with self.assertRaises(SuspiciousOperation):
            self.backend.verify_mfa_acr({})

    @override_settings(PROCONNECT_REQUIRE_MFA=True, PROCONNECT_MFA_ACR_VALUES=PROCONNECT_MFA_ACR_VALUES)
    def test_get_or_create_user_does_not_call_userinfo_when_acr_is_rejected(self):
        with patch.object(self.backend, "get_userinfo") as get_userinfo:
            with self.assertRaises(SuspiciousOperation):
                self.backend.get_or_create_user("access", "id", {"acr": "eidas1"})
        get_userinfo.assert_not_called()

    @override_settings(PROCONNECT_REQUIRE_MFA=True, PROCONNECT_MFA_ACR_VALUES=PROCONNECT_MFA_ACR_VALUES)
    def test_get_or_create_user_continues_when_acr_is_mfa(self):
        self.backend.get_userinfo = MagicMock(
            return_value={
                "sub": "sub-1",
                "email": "agent@example.com",
                "given_name": "Agent",
                "usual_name": "Test",
            }
        )
        user = self.backend.get_or_create_user("access", "id", {"acr": "eidas1-mfa"})
        self.assertEqual(user.email, "agent@example.com")
        self.backend.get_userinfo.assert_called_once()
