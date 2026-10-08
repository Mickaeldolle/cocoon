"""Transactional execution of already-authorized assistant proposals."""

import calendar
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.assistant.models import (
    AssistantMessage,
    AssistantMessageRole,
    AssistantProposal,
    AssistantProposalKind,
    AssistantThread,
    CalendarEvent,
    RecurringReminder,
)
from app.modules.assistant.schemas import (
    CalendarEventProposalPayload,
    DeadlineReminderProposalPayload,
    GroceryProposalPayload,
    NoteProposalPayload,
    RecurringReminderProposalPayload,
    TaskProposalPayload,
    TrainingProposalPayload,
)
from app.modules.auth.consents import require_active_consent
from app.modules.memory.conflicts import supersede_conflicting_preference
from app.modules.memory.service import assert_source_available
from app.modules.memory.typing import classify_memory, layer_for_memory_type
from app.modules.memory.working import current_projects
from app.modules.neural.models import (
    Capture,
    CaptureRun,
    CaptureSource,
    MemoryItem,
    MemoryKind,
    NeuralProposal,
)
from app.modules.personal.models import GroceryItem, GroceryList, PersonalTask, TrainingSession


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def recurring_schedule(data: RecurringReminderProposalPayload) -> tuple[date, datetime]:
    due_date = add_months(data.anchor_date, data.recurrence_months)
    timezone = ZoneInfo(data.timezone)
    reminder_local = datetime.combine(
        due_date - timedelta(days=data.lead_days), time(9, 0), timezone
    )
    return due_date, reminder_local.astimezone(UTC)


def deadline_schedule(data: DeadlineReminderProposalPayload) -> datetime:
    timezone = ZoneInfo(data.timezone)
    reminder_local = datetime.combine(
        data.due_date - timedelta(days=data.lead_days), time(9, 0), timezone
    )
    return reminder_local.astimezone(UTC)


def execute_assistant_proposal(
    session: Session, proposal: AssistantProposal, user_id: UUID
) -> object:
    """Validate and create the resource represented by one assistant proposal."""
    if proposal.kind is AssistantProposalKind.TASK:
        data = TaskProposalPayload.model_validate(proposal.payload)
        resource = PersonalTask(
            user_id=user_id,
            title=data.title,
            detail=data.detail,
            due_date=data.due_date,
            priority=data.priority,
            reminder_at=data.reminder_at,
        )
    elif proposal.kind is AssistantProposalKind.GROCERY_ITEM:
        data = GroceryProposalPayload.model_validate(proposal.payload)
        grocery_list = session.scalar(
            select(GroceryList).where(
                GroceryList.user_id == user_id, GroceryList.archived.is_(False)
            )
        )
        if grocery_list is None:
            grocery_list = GroceryList(user_id=user_id, name="Courses")
            session.add(grocery_list)
            session.flush()
        resource = GroceryItem(user_id=user_id, list_id=grocery_list.id, label=data.label)
    elif proposal.kind is AssistantProposalKind.TRAINING:
        data = TrainingProposalPayload.model_validate(proposal.payload)
        resource = TrainingSession(
            user_id=user_id,
            label=data.label,
            training_type=data.training_type,
            timing=data.timing,
        )
    elif proposal.kind is AssistantProposalKind.NOTE:
        require_active_consent(session, user_id, "assistant.memory", for_update=True)
        data = NoteProposalPayload.model_validate(proposal.payload)
        source = session.scalar(
            select(AssistantMessage)
            .join(AssistantThread, AssistantThread.id == AssistantMessage.thread_id)
            .where(
                AssistantMessage.id == proposal.assistant_message_id,
                AssistantThread.user_id == user_id,
            )
        )
        user_source = (
            session.scalar(
                select(AssistantMessage).where(
                    AssistantMessage.id == source.source_user_message_id,
                    AssistantMessage.thread_id == source.thread_id,
                    AssistantMessage.role == AssistantMessageRole.USER,
                )
            )
            if source is not None and source.source_user_message_id is not None
            else None
        )
        if user_source is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La source utilisateur de cette proposition est introuvable.",
            )
        assert_source_available(session, user_id, "message", proposal.assistant_message_id)
        assert_source_available(session, user_id, "message", user_source.id)
        capture = Capture(
            user_id=user_id,
            source=CaptureSource.TEXT,
            content=data.summary,
            timezone="Europe/Paris",
        )
        session.add(capture)
        session.flush()
        memory_type = classify_memory(data.summary)
        projects = current_projects(session, user_id, user_source.content)
        scope_type = "project" if len(projects) == 1 else "personal"
        scope_id = projects[0] if len(projects) == 1 else None
        previous = supersede_conflicting_preference(
            session, user_id, data.summary, scope_type=scope_type, scope_id=scope_id
        )
        resource = MemoryItem(
            user_id=user_id,
            capture_id=capture.id,
            kind=MemoryKind.INFORMATION,
            layer=layer_for_memory_type(memory_type),
            memory_type=memory_type,
            source_type="user_message",
            source_message_id=user_source.id,
            origin="explicit",
            scope_type=scope_type,
            scope_id=scope_id,
            summary=data.summary,
            reason="Pensée conservée à votre demande depuis l’assistant.",
            supersedes_id=previous.id if previous is not None else None,
        )
    elif proposal.kind is AssistantProposalKind.CALENDAR_EVENT:
        data = CalendarEventProposalPayload.model_validate(proposal.payload)
        conflict = session.scalar(
            select(CalendarEvent)
            .where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.starts_at < data.ends_at,
                CalendarEvent.ends_at > data.starts_at,
            )
            .with_for_update()
        )
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ce créneau est désormais occupé. Demandez un autre horaire à l’assistant.",
            )
        resource = CalendarEvent(
            user_id=user_id,
            title=data.title,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            timezone=data.timezone,
        )
    elif proposal.kind is AssistantProposalKind.RECURRING_REMINDER:
        data = RecurringReminderProposalPayload.model_validate(proposal.payload)
        due_date, reminder_at = recurring_schedule(data)
        resource = RecurringReminder(
            user_id=user_id,
            title=data.title,
            anchor_date=data.anchor_date,
            recurrence_months=data.recurrence_months,
            lead_days=data.lead_days,
            next_due_date=due_date,
            next_reminder_at=reminder_at,
            timezone=data.timezone,
        )
    else:
        data = DeadlineReminderProposalPayload.model_validate(proposal.payload)
        resource = PersonalTask(
            user_id=user_id,
            title=data.title,
            detail=f"Échéance le {data.due_date.isoformat()}.",
            due_date=data.due_date,
            reminder_at=deadline_schedule(data),
        )
    session.add(resource)
    session.flush()
    return resource


def execute_capture_proposal(session: Session, proposal: NeuralProposal, user_id: UUID) -> object:
    """Validate and create the resource represented by a capture proposal."""
    if proposal.user_id != user_id:
        raise HTTPException(status_code=422, detail="Source de proposition invalide.")
    source_capture = session.scalar(
        select(Capture).where(Capture.id == proposal.capture_id, Capture.user_id == user_id)
    )
    if source_capture is None:
        raise HTTPException(status_code=422, detail="Source de proposition invalide.")
    if proposal.source_run_id is not None and session.scalar(
        select(CaptureRun.id).where(
            CaptureRun.id == proposal.source_run_id,
            CaptureRun.user_id == user_id,
            CaptureRun.capture_id == source_capture.id,
        )
    ) is None:
        raise HTTPException(status_code=422, detail="Source de proposition invalide.")
    if proposal.capability in {"task", "reminder"}:
        title = proposal.payload.get("title")
        if not isinstance(title, str) or not title.strip() or len(title) > 160:
            raise HTTPException(status_code=422, detail="Le titre de la proposition est invalide.")
        due_date = proposal.payload.get("due_date")
        try:
            parsed_due_date = date.fromisoformat(str(due_date)) if due_date else None
        except ValueError as error:
            raise HTTPException(
                status_code=422, detail="La date de la proposition est invalide."
            ) from error
        reminder_at = None
        if proposal.capability == "reminder":
            try:
                reminder_at = datetime.fromisoformat(str(proposal.payload.get("reminder_at")))
            except (TypeError, ValueError) as error:
                raise HTTPException(
                    status_code=422, detail="Le rappel de la proposition est invalide."
                ) from error
        resource = PersonalTask(
            user_id=user_id,
            title=title.strip(),
            due_date=parsed_due_date,
            reminder_at=reminder_at,
        )
        session.add(resource)
        session.flush()
        proposal.confirmed_resource_id = resource.id
        return resource

    if proposal.capability == "note":
        require_active_consent(session, user_id, "assistant.memory", for_update=True)
        assert_source_available(session, user_id, "capture", proposal.capture_id)
        summary = proposal.payload.get("summary")
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 240:
            raise HTTPException(status_code=422, detail="La pensée proposée est invalide.")
        try:
            memory_kind = MemoryKind(
                str(proposal.payload.get("kind", MemoryKind.INFORMATION.value))
            )
        except ValueError as error:
            raise HTTPException(
                status_code=422, detail="Le type de pensée est invalide."
            ) from error
        memory_type = classify_memory(summary)
        projects = current_projects(
            session, user_id, source_capture.content
        )
        scope_type = "project" if len(projects) == 1 else "personal"
        scope_id = projects[0] if len(projects) == 1 else None
        previous = supersede_conflicting_preference(
            session, user_id, summary, scope_type=scope_type, scope_id=scope_id
        )
        resource = MemoryItem(
            user_id=user_id,
            capture_id=proposal.capture_id,
            source_run_id=proposal.source_run_id,
            kind=memory_kind,
            layer=layer_for_memory_type(memory_type),
            memory_type=memory_type,
            summary=summary.strip(),
            reason=proposal.reason,
            origin="explicit",
            scope_type=scope_type,
            scope_id=scope_id,
            supersedes_id=previous.id if previous is not None else None,
        )
        session.add(resource)
        session.flush()
        proposal.memory_item_id = resource.id
        proposal.confirmed_resource_id = resource.id
        return resource

    raise HTTPException(status_code=422, detail="Type de proposition invalide.")
