from fastapi.testclient import TestClient


def register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": "Camille",
            "password": "une-phrase-de-passe-solide",
            "installation_id": f"install-{email}",
            "name": "Téléphone",
            "platform": "ios",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_welcome_name_is_optional_persistent_and_account_scoped(client: TestClient) -> None:
    first = register(client, "first@example.com")
    second = register(client, "second@example.com")
    initial = client.get("/api/auth/me", headers=first).json()
    assert initial["assistant_name"] is None
    assert initial["welcome_completed_at"] is None

    invalid = client.put(
        "/api/auth/assistant-name", json={"assistant_name": "   "}, headers=first
    )
    assert invalid.status_code == 422
    named = client.put(
        "/api/auth/assistant-name", json={"assistant_name": "  Mon   Astro  "}, headers=first
    )
    assert named.status_code == 200
    assert named.json()["assistant_name"] == "Mon Astro"
    completed = client.post("/api/auth/welcome/complete", headers=first)
    assert completed.status_code == 200
    assert completed.json()["welcome_completed_at"] is not None
    assert client.post("/api/auth/welcome/complete", headers=first).json()[
        "welcome_completed_at"
    ] == completed.json()["welcome_completed_at"]
    assert client.get("/api/auth/me", headers=second).json()["assistant_name"] is None
    assert client.get("/api/auth/me", headers=second).json()["welcome_completed_at"] is None

    reset = client.put("/api/auth/assistant-name", json={"assistant_name": None}, headers=first)
    assert reset.status_code == 200
    assert reset.json()["assistant_name"] is None


def test_welcome_endpoints_require_authentication(client: TestClient) -> None:
    unnamed = client.put("/api/auth/assistant-name", json={"assistant_name": "Nova"})
    assert unnamed.status_code == 401
    assert client.post("/api/auth/welcome/complete").status_code == 401
