"""OIDC authorize parameters for ProConnect."""

import json

PROCONNECT_MFA_ACR_VALUES = ("eidas0-mfa", "eidas1-mfa", "eidas2", "eidas3")


def oidc_auth_request_extra_params(*, require_mfa: bool) -> dict[str, str]:
    """Extra query parameters for the ProConnect authorization request.

    When MFA is required, ``claims`` must be a JSON string: mozilla-django-oidc
    urlencodes ``OIDC_AUTH_REQUEST_EXTRA_PARAMS`` as-is. Nested dicts would not
    produce the URI-encoded JSON ProConnect expects.
    """
    if require_mfa:
        return {
            "claims": json.dumps(
                {
                    "id_token": {
                        "acr": {
                            "essential": True,
                            "values": list(PROCONNECT_MFA_ACR_VALUES),
                        }
                    }
                },
                separators=(",", ":"),
            )
        }
    return {"acr_values": "eidas1"}
