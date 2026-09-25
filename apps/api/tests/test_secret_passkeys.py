"""Exercise real WebAuthn signatures and server-side challenge/session boundaries."""

import hashlib
import json

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from webauthn import base64url_to_bytes
from webauthn.helpers import bytes_to_base64url

from app.core.config import get_settings

ORIGIN = "https://cocoon-sigma-six.vercel.app"
RP_ID = "cocoon-sigma-six.vercel.app"
PASSWORD = "une-phrase-de-passe-solide"


def register(
    client: TestClient, *, email: str, name: str, password: str, installation_id: str
) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": name,
            "password": password,
            "installation_id": installation_id,
            "name": "Navigateur de test",
            "platform": "web",
        },
    )
    assert response.status_code == 201
    return response.json()


def client_data(kind: str, challenge: str, origin: str = ORIGIN) -> bytes:
    return json.dumps(
        {"type": kind, "challenge": challenge, "origin": origin}, separators=(",", ":")
    ).encode()


def registration_response(
    challenge: str, *, origin: str = ORIGIN
) -> tuple[dict, ec.EllipticCurvePrivateKey]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    numbers = private_key.public_key().public_numbers()
    credential_id = b"test-passkey-id-unique-12345"
    cose_key = cbor2.dumps(
        {1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32), -3: numbers.y.to_bytes(32)}
    )
    auth_data = (
        hashlib.sha256(RP_ID.encode()).digest()
        + b"\x45"  # user present, user verified, attested credential data
        + (0).to_bytes(4)
        + bytes(16)
        + len(credential_id).to_bytes(2)
        + credential_id
        + cose_key
    )
    attestation = cbor2.dumps({"fmt": "none", "authData": auth_data, "attStmt": {}})
    encoded_id = bytes_to_base64url(credential_id)
    return {
        "id": encoded_id,
        "rawId": encoded_id,
        "type": "public-key",
        "response": {
            "attestationObject": bytes_to_base64url(attestation),
            "clientDataJSON": bytes_to_base64url(client_data("webauthn.create", challenge, origin)),
            "transports": ["internal"],
        },
        "clientExtensionResults": {},
    }, private_key


def assertion_response(
    challenge: str,
    private_key: ec.EllipticCurvePrivateKey,
    *,
    origin: str = ORIGIN,
    user_verified: bool = True,
) -> dict:
    credential_id = b"test-passkey-id-unique-12345"
    encoded_id = bytes_to_base64url(credential_id)
    flags = b"\x05" if user_verified else b"\x01"
    auth_data = hashlib.sha256(RP_ID.encode()).digest() + flags + (1).to_bytes(4)
    data = client_data("webauthn.get", challenge, origin)
    signature = private_key.sign(
        auth_data + hashlib.sha256(data).digest(), ec.ECDSA(hashes.SHA256())
    )
    return {
        "id": encoded_id,
        "rawId": encoded_id,
        "type": "public-key",
        "response": {
            "authenticatorData": bytes_to_base64url(auth_data),
            "clientDataJSON": bytes_to_base64url(data),
            "signature": bytes_to_base64url(signature),
            "userHandle": None,
        },
        "clientExtensionResults": {},
    }


def test_web_passkey_registration_and_unlock(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("WEBAUTHN_ORIGIN", ORIGIN)
    get_settings.cache_clear()
    try:
        account = register(
            client,
            email="passkey@example.com",
            name="Lina",
            password=PASSWORD,
            installation_id="install-passkey-47d6676d-0691-4c74-b067",
        )
        headers = {"Authorization": f"Bearer {account['access_token']}"}
        status = client.get("/api/secret/passkeys/status", headers=headers)
        assert status.json() == {"available": True, "has_passkeys": False}
        assert (
            client.post(
                "/api/secret/passkeys/register/options",
                json={"password": "mauvais-mot-de-passe"},
                headers=headers,
            ).status_code
            == 401
        )

        options = client.post(
            "/api/secret/passkeys/register/options", json={"password": PASSWORD}, headers=headers
        ).json()
        assert options["options"]["rp"]["id"] == RP_ID
        assert options["options"]["authenticatorSelection"]["userVerification"] == "required"
        assert len(base64url_to_bytes(options["options"]["challenge"])) >= 32
        credential, private_key = registration_response(options["options"]["challenge"])
        payload = {"challenge_id": options["challenge_id"], "credential": credential}
        registered = client.post(
            "/api/secret/passkeys/register/verify", json=payload, headers=headers
        )
        assert registered.status_code == 200, registered.text
        assert (
            client.post(
                "/api/secret/passkeys/register/verify", json=payload, headers=headers
            ).status_code
            == 401
        )
        assert client.get("/api/secret/passkeys/status", headers=headers).json()["has_passkeys"]

        monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://nouveau-cocoon.example")
        get_settings.cache_clear()
        assert client.get("/api/secret/passkeys/status", headers=headers).json() == {
            "available": True,
            "has_passkeys": False,
        }
        monkeypatch.setenv("WEBAUTHN_ORIGIN", ORIGIN)
        get_settings.cache_clear()

        unlock_options = client.post("/api/secret/passkeys/unlock/options", headers=headers).json()
        assert unlock_options["options"]["userVerification"] == "required"
        assertion = assertion_response(unlock_options["options"]["challenge"], private_key)
        unlock_payload = {"challenge_id": unlock_options["challenge_id"], "credential": assertion}
        unlocked = client.post(
            "/api/secret/passkeys/unlock/verify", json=unlock_payload, headers=headers
        )
        assert unlocked.status_code == 200, unlocked.text
        assert (
            client.get(
                "/api/secret/conversations",
                headers={
                    **headers,
                    "X-Cocoon-Secret-Access": unlocked.json()["secret_access_token"],
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/secret/passkeys/unlock/verify", json=unlock_payload, headers=headers
            ).status_code
            == 401
        )

        wrong_origin_options = client.post(
            "/api/secret/passkeys/unlock/options", headers=headers
        ).json()
        wrong_origin = assertion_response(
            wrong_origin_options["options"]["challenge"],
            private_key,
            origin="https://attacker.example",
        )
        assert (
            client.post(
                "/api/secret/passkeys/unlock/verify",
                json={
                    "challenge_id": wrong_origin_options["challenge_id"],
                    "credential": wrong_origin,
                },
                headers=headers,
            ).status_code
            == 401
        )

        no_verification_options = client.post(
            "/api/secret/passkeys/unlock/options", headers=headers
        ).json()
        no_verification = assertion_response(
            no_verification_options["options"]["challenge"],
            private_key,
            user_verified=False,
        )
        assert (
            client.post(
                "/api/secret/passkeys/unlock/verify",
                json={
                    "challenge_id": no_verification_options["challenge_id"],
                    "credential": no_verification,
                },
                headers=headers,
            ).status_code
            == 401
        )

        second_account = register(
            client,
            email="autre-passkey@example.com",
            name="Noa",
            password=PASSWORD,
            installation_id="install-other-passkey-03a75b8e-0c70-4f46",
        )
        second_headers = {"Authorization": f"Bearer {second_account['access_token']}"}
        own_options = client.post("/api/secret/passkeys/unlock/options", headers=headers).json()
        another_session = client.post(
            "/api/auth/login",
            json={
                "email": "passkey@example.com",
                "password": PASSWORD,
                "installation_id": "install-passkey-second-session-69e294a1",
                "name": "Autre navigateur",
                "platform": "web",
            },
        )
        assert another_session.status_code == 200
        another_session_headers = {
            "Authorization": f"Bearer {another_session.json()['access_token']}"
        }
        assert (
            client.post(
                "/api/secret/passkeys/unlock/verify",
                json={
                    "challenge_id": own_options["challenge_id"],
                    "credential": assertion_response(
                        own_options["options"]["challenge"], private_key
                    ),
                },
                headers=another_session_headers,
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/secret/passkeys/unlock/verify",
                json={
                    "challenge_id": own_options["challenge_id"],
                    "credential": assertion_response(
                        own_options["options"]["challenge"], private_key
                    ),
                },
                headers=second_headers,
            ).status_code
            == 401
        )
        assert (
            client.post("/api/secret/passkeys/unlock/options", headers=second_headers).status_code
            == 404
        )

        assert (
            client.request(
                "DELETE",
                "/api/secret/passkeys",
                json={"password": "mauvais-mot-de-passe"},
                headers=headers,
            ).status_code
            == 401
        )
        assert (
            client.request(
                "DELETE", "/api/secret/passkeys", json={"password": PASSWORD}, headers=headers
            ).status_code
            == 204
        )
        assert (
            client.get("/api/secret/passkeys/status", headers=headers).json()["has_passkeys"]
            is False
        )
        assert (
            client.post("/api/secret/passkeys/unlock/options", headers=headers).status_code == 404
        )
        assert (
            client.get(
                "/api/secret/conversations",
                headers={
                    **headers,
                    "X-Cocoon-Secret-Access": unlocked.json()["secret_access_token"],
                },
            ).status_code
            == 401
        )
    finally:
        get_settings.cache_clear()


def test_web_passkeys_require_an_explicit_secure_origin(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "http://cocoon-sigma-six.vercel.app")
    get_settings.cache_clear()
    try:
        account = register(
            client,
            email="sans-https@example.com",
            name="Lina",
            password=PASSWORD,
            installation_id="install-without-https-69e294a1-c90e-47e4",
        )
        headers = {"Authorization": f"Bearer {account['access_token']}"}
        assert client.get("/api/secret/passkeys/status", headers=headers).json() == {
            "available": False,
            "has_passkeys": False,
        }
        assert (
            client.post(
                "/api/secret/passkeys/register/options",
                json={"password": PASSWORD},
                headers=headers,
            ).status_code
            == 503
        )
    finally:
        get_settings.cache_clear()
