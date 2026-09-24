from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.modules.assistant.tools import ToolBudget, tool_registry
from app.modules.auth.models import User
from app.modules.personal.models import PersonalProject, PersonalTask


def register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "A-strong-password-123",
            "display_name": email.split("@")[0],
            "installation_id": str(uuid4()),
            "name": "Test device",
            "platform": "ios",
        },
    )
    return response.json()


def test_registry_rejects_unknown_tools(client: TestClient) -> None:
    with pytest.raises(HTTPException) as error:
        tool_registry.execute(
            "shell.exec",
            {},
            session=app.state.test_session_factory(),
            user_id=uuid4(),
        )
    assert error.value.status_code == 404


def test_registry_rejects_parameters_outside_the_tool_schema(client: TestClient) -> None:
    with pytest.raises(HTTPException) as error:
        tool_registry.execute(
            "personal.tasks.list",
            {"limit": 1, "user_id": str(uuid4())},
            session=app.state.test_session_factory(),
            user_id=uuid4(),
        )
    assert error.value.status_code == 422


def test_task_tool_is_owner_filtered_and_bounded(client: TestClient) -> None:
    first = register(client, "first-tools@example.com")
    second = register(client, "second-tools@example.com")
    session = app.state.test_session_factory()
    try:
        first_user = session.query(User).filter_by(email="first-tools@example.com").one()
        second_user = session.query(User).filter_by(email="second-tools@example.com").one()
        session.add_all(
            [
                PersonalTask(user_id=first_user.id, title="Tâche visible"),
                PersonalTask(user_id=second_user.id, title="Tâche privée"),
            ]
        )
        session.commit()
        result = tool_registry.execute(
            "personal.tasks.list",
            {"limit": 1},
            session=session,
            user_id=first_user.id,
        )
        assert [item["title"] for item in result] == ["Tâche visible"]
        result_b = tool_registry.execute(
            "personal.tasks.list",
            {"limit": 1},
            session=session,
            user_id=second_user.id,
        )
        result_a_again = tool_registry.execute(
            "personal.tasks.list",
            {"limit": 1},
            session=session,
            user_id=first_user.id,
        )
        assert [item["title"] for item in result_b] == ["Tâche privée"]
        assert [item["title"] for item in result_a_again] == ["Tâche visible"]
        assert first["access_token"] and second["access_token"]
    finally:
        session.close()


def test_project_tool_is_owner_filtered_and_excludes_completed_projects(client: TestClient) -> None:
    first = register(client, "first-project-tools@example.com")
    second = register(client, "second-project-tools@example.com")
    session = app.state.test_session_factory()
    try:
        first_user = session.query(User).filter_by(email="first-project-tools@example.com").one()
        second_user = session.query(User).filter_by(email="second-project-tools@example.com").one()
        session.add_all(
            [
                PersonalProject(user_id=first_user.id, name="Projet A", status="active"),
                PersonalProject(user_id=first_user.id, name="Projet terminé", status="completed"),
                PersonalProject(user_id=second_user.id, name="Projet B", status="active"),
            ]
        )
        session.commit()
        result = tool_registry.execute(
            "personal.projects.list", {}, session=session, user_id=first_user.id
        )
        assert [item["name"] for item in result] == ["Projet A"]
        assert first["access_token"] and second["access_token"]
    finally:
        session.close()


def test_tool_budget_rejects_a_loop(client: TestClient) -> None:
    auth = register(client, "budget-tools@example.com")
    session = app.state.test_session_factory()
    try:
        user = session.query(User).filter_by(email="budget-tools@example.com").one()
        budget = ToolBudget(max_calls=1, max_duration_ms=2000)
        tool_registry.execute(
            "personal.tasks.list",
            {},
            session=session,
            user_id=user.id,
            budget=budget,
        )
        with pytest.raises(HTTPException) as error:
            tool_registry.execute(
                "personal.calendar.list",
                {},
                session=session,
                user_id=user.id,
                budget=budget,
            )
        assert error.value.status_code == 429
        assert auth["access_token"]
    finally:
        session.close()


def test_tool_budget_rejects_repeated_identical_call(client: TestClient) -> None:
    register(client, "repeat-tools@example.com")
    session = app.state.test_session_factory()
    try:
        user = session.query(User).filter_by(email="repeat-tools@example.com").one()
        budget = ToolBudget(max_calls=4, max_duration_ms=2000)
        tool_registry.execute(
            "personal.tasks.list",
            {"limit": 3},
            session=session,
            user_id=user.id,
            budget=budget,
        )
        tool_registry.execute(
            "personal.calendar.list",
            {"limit": 3},
            session=session,
            user_id=user.id,
            budget=budget,
        )
        with pytest.raises(HTTPException) as error:
            tool_registry.execute(
                "personal.tasks.list",
                {"limit": 3},
                session=session,
                user_id=user.id,
                budget=budget,
            )
        assert error.value.status_code == 429
        assert "boucle" in error.value.detail
    finally:
        session.close()
