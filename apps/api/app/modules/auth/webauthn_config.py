"""WebAuthn trust boundary shared by account login and secret step-up."""

import json
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.core.config import get_settings


def webauthn_relying_party() -> tuple[str, str] | None:
    configured = get_settings().webauthn_origin
    if not configured:
        return None
    try:
        parsed = urlsplit(configured)
    except ValueError:
        return None
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in ("http", "https")
        or (
            parsed.scheme == "http"
            and not (get_settings().app_env == "development" and parsed.hostname == "localhost")
        )
    ):
        return None
    try:
        if parsed.port == 0:
            return None
    except ValueError:
        return None
    return f"{parsed.scheme}://{parsed.netloc.lower()}", parsed.hostname.lower()


def require_webauthn_relying_party() -> tuple[str, str]:
    relying_party = webauthn_relying_party()
    if relying_party is None:
        raise HTTPException(status_code=503, detail="Les passkeys ne sont pas configurées.")
    return relying_party


def checked_credential(credential: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(credential)) > 32_768:
        raise HTTPException(status_code=413, detail="Réponse passkey trop volumineuse.")
    return credential
