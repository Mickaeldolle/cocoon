from fastapi.testclient import TestClient


def registration(email: str, name: str, installation: str) -> dict[str, object]:
    return {
        "email": email,
        "password": "A-strong-password-123",
        "display_name": name,
        "installation_id": installation,
        "name": "Test device",
        "platform": "ios",
    }


def headers(client: TestClient, email: str, name: str, installation: str) -> dict[str, str]:
    response = client.post("/api/auth/register", json=registration(email, name, installation))
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_profile_and_personal_items_are_private_and_persisted(client: TestClient) -> None:
    marie = headers(client, "marie@example.com", "Marie Dupont", "profile-test-marie")
    paul = headers(client, "paul@example.com", "Paul Durand", "profile-test-paul")

    response = client.put(
        "/api/personal/profile",
        headers=marie,
        json={
            "display_name": "Marie D.",
            "birth_date": "1990-03-04",
            "height_cm": 170,
            "weight_kg": 71.5,
            "target_weight_kg": 66,
        },
    )
    assert response.status_code == 200
    assert response.json()["weight_kg"] == 71.5

    task = client.post("/api/personal/tasks", headers=marie, json={"title": "Appeler le dentiste"})
    grocery = client.post("/api/personal/groceries", headers=marie, json={"label": "Lait"})
    assert task.status_code == 201 and grocery.status_code == 201

    checked = client.patch(
        f"/api/personal/groceries/{grocery.json()['id']}", headers=marie, json={"checked": True}
    )
    assert checked.status_code == 200 and checked.json()["checked"] is True
    assert client.get("/api/personal/tasks", headers=paul).json() == []
    assert client.get("/api/personal/groceries", headers=paul).json() == []
    assert client.get("/api/personal/profile", headers=paul).json()["weight_kg"] is None


def test_personal_projects_are_owner_scoped_and_updateable(client: TestClient) -> None:
    marie = headers(client, "project-marie@example.com", "Marie Dupont", "project-marie")
    paul = headers(client, "project-paul@example.com", "Paul Durand", "project-paul")

    created = client.post(
        "/api/personal/projects",
        headers=marie,
        json={"name": "Refonte Cocoon", "description": "Préparer le MVP"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    assert created.json()["status"] == "active"
    assert client.get("/api/personal/projects", headers=paul).json() == []

    updated = client.patch(
        f"/api/personal/projects/{project_id}",
        headers=marie,
        json={"status": "paused", "description": "Revoir la validation"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "paused"
    assert client.patch(
        f"/api/personal/projects/{project_id}",
        headers=paul,
        json={"status": "completed"},
    ).status_code == 404


def test_assistant_legacy_organize_never_saves_without_confirmation(client: TestClient) -> None:
    marie = headers(client, "marie@example.com", "Marie Dupont", "personal-assistant-test")
    response = client.post(
        "/api/assistant/organize",
        headers=marie,
        json={"thought": "Appeler le dentiste demain", "reference_date": "2026-09-15"},
    )
    assert response.status_code == 200
    tasks = client.get("/api/personal/tasks", headers=marie).json()
    assert tasks == []
