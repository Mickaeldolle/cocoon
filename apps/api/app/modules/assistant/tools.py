"""Allowlisted, read-only tools available to the private assistant runtime.

This registry is intentionally an internal service boundary. It is not an MCP
server, does not execute arbitrary Python or shell commands, and never accepts
a provider-supplied tool name without checking the allowlist first.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.assistant.models import CalendarEvent
from app.modules.memory.repository import MemoryRepository
from app.modules.personal.models import PersonalProject, PersonalTask

logger = logging.getLogger(__name__)
MAX_RESULTS = 20
MAX_INPUT_LENGTH = 64


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: str
    description: str
    input_schema: dict[str, object]
    access_level: str
    handler: Callable[[Session, UUID, dict[str, object]], list[dict[str, object]]]


@dataclass
class ToolBudget:
    """Small per-run guard against tool loops and unbounded local work."""

    max_calls: int
    max_duration_ms: int
    started_at: float = field(default_factory=perf_counter)
    calls: int = 0
    seen_calls: set[str] = field(default_factory=set)

    def consume(self, name: str, args: dict[str, object]) -> None:
        elapsed_ms = (perf_counter() - self.started_at) * 1000
        if self.calls >= self.max_calls or elapsed_ms >= self.max_duration_ms:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Le budget des outils de cette exécution est épuisé.",
            )
        signature = json.dumps(
            {"name": name, "args": args}, sort_keys=True, separators=(",", ":"), default=str
        )
        if signature in self.seen_calls:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Une boucle d’appel d’outil a été détectée.",
            )
        self.seen_calls.add(signature)
        self.calls += 1


def _limit(args: dict[str, object]) -> int:
    value = args.get("limit", MAX_RESULTS)
    if not isinstance(value, int) or isinstance(value, bool):
        raise HTTPException(status_code=422, detail="La limite de l’outil est invalide.")
    return max(1, min(value, MAX_RESULTS))


def _personal_tasks(
    session: Session, user_id: UUID, args: dict[str, object]
) -> list[dict[str, object]]:
    tasks = session.scalars(
        select(PersonalTask)
        .where(PersonalTask.user_id == user_id, PersonalTask.completed.is_(False))
        .order_by(PersonalTask.due_date.asc().nulls_last(), PersonalTask.created_at.desc())
        .limit(_limit(args))
    )
    return [
        {
            "id": str(task.id),
            "title": task.title,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "priority": task.priority,
        }
        for task in tasks
    ]


def _calendar_events(
    session: Session, user_id: UUID, args: dict[str, object]
) -> list[dict[str, object]]:
    now = datetime.now(UTC)
    events = session.scalars(
        select(CalendarEvent)
        .where(CalendarEvent.user_id == user_id, CalendarEvent.ends_at >= now)
        .order_by(CalendarEvent.starts_at.asc())
        .limit(_limit(args))
    )
    return [
        {
            "id": str(event.id),
            "title": event.title,
            "starts_at": event.starts_at.isoformat(),
            "ends_at": event.ends_at.isoformat(),
            "timezone": event.timezone,
        }
        for event in events
    ]


def _personal_projects(
    session: Session, user_id: UUID, args: dict[str, object]
) -> list[dict[str, object]]:
    projects = session.scalars(
        select(PersonalProject)
        .where(PersonalProject.user_id == user_id, PersonalProject.status != "completed")
        .order_by(PersonalProject.updated_at.desc())
        .limit(_limit(args))
    )
    return [
        {
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "status": project.status,
        }
        for project in projects
    ]


def _accessible_memories(
    session: Session, user_id: UUID, args: dict[str, object]
) -> list[dict[str, object]]:
    memories = MemoryRepository().active_for_user(session, user_id, limit=_limit(args))
    return [
        {
            "id": str(memory.id),
            "summary": memory.summary,
            "kind": memory.kind.value,
            "confidence": memory.confidence,
        }
        for memory in memories
    ]


class PersonalToolRegistry:
    """Registry of explicitly allowed read-only personal tools."""

    def __init__(self) -> None:
        self._definitions = {
            definition.name: definition
            for definition in (
                ToolDefinition(
                    name="personal.tasks.list",
                    version="1",
                    description="Lire les tâches personnelles ouvertes de l’utilisateur.",
                    input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
                    access_level="personal.read",
                    handler=_personal_tasks,
                ),
                ToolDefinition(
                    name="personal.calendar.list",
                    version="1",
                    description="Lire les prochains événements personnels de l’utilisateur.",
                    input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
                    access_level="personal.read",
                    handler=_calendar_events,
                ),
                ToolDefinition(
                    name="personal.projects.list",
                    version="1",
                    description="Lire les projets personnels actifs de l’utilisateur.",
                    input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
                    access_level="personal.read",
                    handler=_personal_projects,
                ),
                ToolDefinition(
                    name="personal.memory.list",
                    version="1",
                    description="Lire les mémoires personnelles actives accessibles.",
                    input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
                    access_level="personal.read",
                    handler=_accessible_memories,
                ),
            )
        }

    def definitions(self) -> list[ToolDefinition]:
        return list(self._definitions.values())

    def execute(
        self,
        name: str,
        args: dict[str, object],
        *,
        session: Session,
        user_id: UUID,
        run_id: UUID | None = None,
        budget: ToolBudget | None = None,
    ) -> list[dict[str, object]]:
        if len(name) > MAX_INPUT_LENGTH or name not in self._definitions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outil inconnu.")
        if not isinstance(args, dict):
            raise HTTPException(status_code=422, detail="Les paramètres de l’outil sont invalides.")
        if set(args) - {"limit"}:
            raise HTTPException(status_code=422, detail="Les paramètres de l’outil sont invalides.")
        if budget is not None:
            budget.consume(name, args)

        definition = self._definitions[name]
        started = perf_counter()
        try:
            result = definition.handler(session, user_id, args)
        except HTTPException:
            logger.warning(
                "assistant_tool_failed run_id=%s tool=%s status=invalid duration_ms=%.1f",
                run_id,
                name,
                (perf_counter() - started) * 1000,
            )
            raise
        logger.info(
            "assistant_tool_finished run_id=%s tool=%s status=ok count=%d duration_ms=%.1f",
            run_id,
            name,
            len(result),
            (perf_counter() - started) * 1000,
        )
        return result


tool_registry = PersonalToolRegistry()
