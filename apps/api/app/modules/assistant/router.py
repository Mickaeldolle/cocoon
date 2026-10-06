import asyncio
import json
import logging
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands.run_reminder_worker import send_pending_notifications
from app.core.config import get_settings
from app.core.database import get_session
from app.modules.assistant.context import (
    accessible_memory_summaries,
    accessible_personal_context,
    get_or_create_thread,
    open_task_titles,
    recent_messages,
)
from app.modules.assistant.executor import (
    deadline_schedule,
    execute_assistant_proposal,
    recurring_schedule,
)
from app.modules.assistant.free_models import (
    FreeModelCatalogError,
    free_models,
    select_free_model,
    uses_openrouter,
)
from app.modules.assistant.kernel import (
    answer,
    parse_streamed_answer,
    stream_answer,
    streamed_reply_prefix,
)
from app.modules.assistant.llm_service import LLMService
from app.modules.assistant.models import (
    AssistantMessage,
    AssistantMessageRole,
    AssistantPreference,
    AssistantProposal,
    AssistantProposalKind,
    AssistantProposalStatus,
    AssistantThread,
    CalendarEvent,
    NotificationOutbox,
    RecurringReminder,
)
from app.modules.assistant.proposals import (
    prepare_proposal_confirmation,
    record_failed_proposal,
    record_proposal_execution,
    stable_proposal_key,
)
from app.modules.assistant.rate_limit import assistant_rate_limiter
from app.modules.assistant.schemas import (
    AssistantBriefingResponse,
    AssistantChatResponse,
    AssistantHistoryResponse,
    AssistantMessageResponse,
    AssistantProposalResponse,
    AssistantStreamRequest,
    AssistantTurnRequest,
    AssistantTurnResponse,
    CalendarEventListResponse,
    CalendarEventProposalPayload,
    CalendarEventResponse,
    DailyBriefSettings,
    DeadlineReminderProposalPayload,
    GroceryMealPlanRequest,
    GroceryMealPlanResponse,
    NotificationResponse,
    RecurringReminderProposalPayload,
    RecurringReminderResponse,
    RecurringReminderUpdate,
    ThoughtOrganizationRequest,
    ThoughtOrganizationResponse,
    VoiceTranscriptionResponse,
)
from app.modules.assistant.service import (
    AssistantTurnDraft,
    organize_thought,
    plan_grocery_meals,
    propose_assistant_turn,
)
from app.modules.assistant.voice import MAX_VOICE_BYTES, SUPPORTED_AUDIO_TYPES, transcribe_audio
from app.modules.audit.service import note_request_details
from app.modules.auth.consents import require_active_consent
from app.modules.auth.dependencies import (
    AuthenticatedSession,
    get_authenticated_session,
    get_current_user,
    require_assistant_enabled,
)
from app.modules.auth.models import User, WebPushSubscription
from app.modules.memory.context import accessible_memory_summary_keys
from app.modules.memory.models import ContextDependency, MemoryExclusion, MemoryUsage
from app.modules.memory.policy import memory_allowed
from app.modules.memory.service import exclude_source
from app.modules.memory.text import summary_key as normalized_summary_key
from app.modules.neural.models import MemoryItem
from app.modules.personal.models import PersonalTask

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
notification_logger = logging.getLogger("cocoon.assistant.notifications")
_active_stream_turns: set[tuple[UUID, str]] = set()
_active_stream_turns_lock = threading.Lock()


def _claim_stream_turn(thread_id: UUID, key: str) -> None:
    with _active_stream_turns_lock:
        claim = (thread_id, key)
        if claim in _active_stream_turns:
            raise HTTPException(
                status_code=409, detail="Ce tour assistant est déjà en cours de traitement."
            )
        _active_stream_turns.add(claim)


def _release_stream_turn(thread_id: UUID, key: str | None) -> None:
    if key is not None:
        with _active_stream_turns_lock:
            _active_stream_turns.discard((thread_id, key))


def enforce_generation_rate_limit(
    current_user: User = Depends(require_assistant_enabled),
) -> None:
    if not assistant_rate_limiter.allow(
        current_user.id, get_settings().assistant_requests_per_minute
    ):
        raise HTTPException(
            status_code=429,
            detail="Trop de demandes à l’assistant. Réessayez dans une minute.",
        )


@router.get("/status")
async def assistant_status(
    _current_user: User = Depends(require_assistant_enabled),
) -> dict[str, str | bool]:
    """Private model availability; no URL or credentials in the response."""
    return await run_in_threadpool(LLMService().status)


@router.get("/models")
async def assistant_free_models(
    _current_user: User = Depends(require_assistant_enabled),
) -> dict[str, object]:
    settings = get_settings()
    if not uses_openrouter(settings):
        return {"available": False, "default_model": None, "models": []}
    try:
        models = await run_in_threadpool(free_models, settings)
    except FreeModelCatalogError as error:
        raise HTTPException(
            503, "Impossible de charger les modèles gratuits. Réessayez."
        ) from error
    ids = {item.id for item in models}
    default_model = settings.llm_model if settings.llm_model in ids else "openrouter/free"
    if default_model not in ids:
        default_model = models[0].id
    return {
        "available": True,
        "default_model": default_model,
        "models": [{"id": item.id, "name": item.name} for item in models],
    }


@router.post("/voice/transcriptions", response_model=VoiceTranscriptionResponse)
async def create_voice_transcription(
    request: Request,
    current_user: User = Depends(require_assistant_enabled),
    session: Session = Depends(get_session),
) -> VoiceTranscriptionResponse:
    """Transcribe an explicitly recorded short clip without retaining its audio bytes."""
    content_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0].lower()
    if content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Ce format audio n’est pas pris en charge.",
        )
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_VOICE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="L’enregistrement est trop long. Réessayez avec un message plus court.",
        )
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_VOICE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="L’enregistrement est trop long. Réessayez avec un message plus court.",
            )
        chunks.append(chunk)
    require_active_consent(session, current_user.id, "assistant.voice")
    return VoiceTranscriptionResponse(text=transcribe_audio(b"".join(chunks), content_type))


def exclude_calendar_conflicts(
    session: Session, user_id: UUID, draft: "AssistantTurnDraft"
) -> "AssistantTurnDraft":
    for proposal in draft.proposals:
        if proposal.kind != AssistantProposalKind.CALENDAR_EVENT.value:
            continue
        data = CalendarEventProposalPayload.model_validate(proposal.payload)
        conflict = session.scalar(
            select(CalendarEvent).where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.starts_at < data.ends_at,
                CalendarEvent.ends_at > data.starts_at,
            )
        )
        if conflict is not None:
            local_start = conflict.starts_at.astimezone(ZoneInfo(data.timezone))
            return AssistantTurnDraft(
                content=(
                    f"Vous avez déjà « {conflict.title} » prévu le "
                    f"{local_start.strftime('%d/%m à %H:%M')}. "
                    "Souhaitez-vous choisir un autre créneau ?"
                ),
                proposals=[],
                mode=draft.mode,
            )
    return draft


def proposal_response(proposal: AssistantProposal) -> AssistantProposalResponse:
    return AssistantProposalResponse(
        id=proposal.id,
        kind=proposal.kind.value,
        payload=proposal.payload,
        payload_version=proposal.payload_version,
        status=proposal.status.value,
        created_at=proposal.created_at,
    )


def calendar_event_response(event: CalendarEvent) -> CalendarEventResponse:
    return CalendarEventResponse(
        id=event.id,
        title=event.title,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        timezone=event.timezone,
        source=event.source,
    )


def recurring_reminder_response(reminder: RecurringReminder) -> RecurringReminderResponse:
    return RecurringReminderResponse(
        id=reminder.id,
        title=reminder.title,
        anchor_date=reminder.anchor_date,
        recurrence_months=reminder.recurrence_months,
        lead_days=reminder.lead_days,
        next_due_date=reminder.next_due_date,
        next_reminder_at=reminder.next_reminder_at,
        timezone=reminder.timezone,
        active=reminder.active,
    )


def notification_response(item: NotificationOutbox) -> NotificationResponse:
    return NotificationResponse(
        id=item.id,
        title=item.title,
        body=item.body,
        data=item.data,
        provider_status=item.provider_status,
        sent_at=item.sent_at,
        read_at=item.read_at,
        created_at=item.created_at,
    )


def message_response(
    message: AssistantMessage, proposals: list[AssistantProposal]
) -> AssistantMessageResponse:
    return AssistantMessageResponse(
        id=message.id,
        role=message.role.value,
        content=message.content,
        created_at=message.created_at,
        idempotency_key=message.idempotency_key,
        proposals=[proposal_response(proposal) for proposal in proposals],
    )


def _sse(event: str, payload: object) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _persist_chat_reply(
    session: Session,
    user_id: UUID,
    thread_id: UUID,
    reply: object,
    *,
    runtime: str = "local",
    recalled_memories: list[dict[str, object]] | None = None,
    recent_turns: list[dict[str, str]] | None = None,
    personal_context: list[dict[str, object]] | None = None,
    source_user_message_id: UUID | None = None,
) -> AssistantChatResponse:
    assistant_message = AssistantMessage(
        thread_id=thread_id,
        role=AssistantMessageRole.ASSISTANT,
        content=reply.text,
        source_user_message_id=source_user_message_id,
        working_choices=reply.choices or None,
        created_at=datetime.now(UTC),
    )
    session.add(assistant_message)
    session.flush()
    _record_memory_usage(
        session,
        assistant_message.id,
        recalled_memories or [],
        recent_turns or [],
        personal_context or [],
    )
    known = accessible_memory_summary_keys(session, user_id)
    proposals: list[AssistantProposal] = []
    for summary in reply.memories if memory_allowed(session, user_id) else []:
        summary_key = normalized_summary_key(summary)
        if summary_key in known:
            continue
        proposals.append(
            AssistantProposal(
                user_id=user_id,
                assistant_message_id=assistant_message.id,
                kind=AssistantProposalKind.NOTE,
                payload={"summary": summary},
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        known.add(summary_key)
    for proposal in proposals:
        proposal.proposal_key = stable_proposal_key(
            "assistant", assistant_message.id, proposal.kind.value, proposal.payload
        )
    session.add_all(proposals)
    session.commit()
    session.refresh(assistant_message)
    for proposal in proposals:
        session.refresh(proposal)
    return AssistantChatResponse(
        message=message_response(assistant_message, proposals),
        choices=reply.choices,
        remembered=[],
        runtime=runtime,
    )


def _record_memory_usage(
    session: Session,
    message_id: UUID,
    memories: list[dict[str, object]],
    recent_turns: list[dict[str, str]],
    personal_context: list[dict[str, object]],
) -> None:
    memory_ids = {UUID(str(memory["id"])) for memory in memories}
    ids = {
        UUID(item["source_message_id"]) for item in recent_turns if item.get("source_message_id")
    }
    for block in personal_context:
        if block.get("source") == "conversation.working":
            ids.update(UUID(item["source_message_id"]) for item in block.get("entries", []))
    message = session.get(AssistantMessage, message_id)
    current_source = message.source_user_message_id or session.scalar(
        select(AssistantMessage.id)
        .where(
            AssistantMessage.thread_id == message.thread_id,
            AssistantMessage.role == AssistantMessageRole.USER,
            AssistantMessage.created_at <= message.created_at,
        )
        .order_by(AssistantMessage.created_at.desc())
        .limit(1)
    )
    if current_source:
        ids.add(current_source)
    memory_ids.update(
        session.scalars(select(MemoryUsage.memory_id).where(MemoryUsage.message_id.in_(ids)))
    )
    for memory_id in memory_ids:
        session.add(MemoryUsage(message_id=message_id, memory_id=memory_id))
    for source_id in ids:
        session.add(ContextDependency(message_id=message_id, source_message_id=source_id))
    owner_id = session.scalar(
        select(AssistantThread.user_id).where(AssistantThread.id == message.thread_id)
    )
    excluded_parent = session.scalar(
        select(MemoryExclusion.source_id)
        .where(
            MemoryExclusion.user_id == owner_id,
            MemoryExclusion.source_type == "message",
            MemoryExclusion.source_id.in_(ids),
        )
        .limit(1)
    )
    forgotten_memory = session.scalar(
        select(MemoryItem.id)
        .where(
            MemoryItem.id.in_(memory_ids),
            MemoryItem.deleted_at.is_not(None),
        )
        .limit(1)
    )
    if excluded_parent is not None or forgotten_memory is not None:
        exclude_source(session, owner_id, "message", message_id)


@router.post(
    "/chat",
    response_model=AssistantChatResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_generation_rate_limit)],
)
async def create_chat_turn(
    payload: AssistantTurnRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="X-Assistant-Idempotency-Key"),
) -> AssistantChatResponse:
    """Run the personal-agent loop; candidate memories require explicit confirmation."""
    note_request_details(request, message_length=len(payload.text))
    thread = get_or_create_thread(session, current_user.id)
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 128:
            raise HTTPException(status_code=422, detail="La clé d’idempotence est invalide.")
        previous_user_message = session.scalar(
            select(AssistantMessage).where(
                AssistantMessage.thread_id == thread.id,
                AssistantMessage.role == AssistantMessageRole.USER,
                AssistantMessage.idempotency_key == idempotency_key,
            )
        )
        if previous_user_message is not None:
            previous_assistant_message = session.scalar(
                select(AssistantMessage)
                .where(
                    AssistantMessage.thread_id == thread.id,
                    AssistantMessage.role == AssistantMessageRole.ASSISTANT,
                    AssistantMessage.created_at >= previous_user_message.created_at,
                )
                .order_by(AssistantMessage.created_at.asc())
            )
            if previous_assistant_message is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ce tour assistant est déjà en cours de traitement.",
                )
            previous_proposals = list(
                session.scalars(
                    select(AssistantProposal).where(
                        AssistantProposal.assistant_message_id == previous_assistant_message.id
                    )
                )
            )
            return AssistantChatResponse(
                message=message_response(previous_assistant_message, previous_proposals),
                choices=[],
                remembered=[],
                runtime="local",
            )
    recent_turns = recent_messages(session, thread.id, limit=10, include_sources=True)
    recalled_memories = await run_in_threadpool(
        accessible_memory_summaries, session, current_user.id, limit=12, query=payload.text
    )
    personal_context = accessible_personal_context(
        session, current_user.id, limit=8, query=payload.text
    )
    # Commit the user's message before model work so a provider outage never loses it.
    user_message = AssistantMessage(
        thread_id=thread.id,
        role=AssistantMessageRole.USER,
        idempotency_key=idempotency_key,
        content=payload.text,
        created_at=datetime.now(UTC),
    )
    session.add(user_message)
    # Do not hold a database transaction while a local model can take several minutes.
    session.commit()
    reply = await run_in_threadpool(
        answer, payload.text, recent_turns, recalled_memories, personal_context
    )

    assistant_message = AssistantMessage(
        thread_id=thread.id,
        role=AssistantMessageRole.ASSISTANT,
        content=reply.text,
        source_user_message_id=user_message.id,
        working_choices=reply.choices or None,
        created_at=datetime.now(UTC),
    )
    session.add(assistant_message)
    session.flush()
    _record_memory_usage(
        session, assistant_message.id, recalled_memories, recent_turns, personal_context
    )
    known = accessible_memory_summary_keys(session, current_user.id)
    proposals: list[AssistantProposal] = []
    for summary in reply.memories if memory_allowed(session, current_user.id) else []:
        summary_key = normalized_summary_key(summary)
        if summary_key in known:
            continue
        proposals.append(
            AssistantProposal(
                user_id=current_user.id,
                assistant_message_id=assistant_message.id,
                kind=AssistantProposalKind.NOTE,
                payload={"summary": summary},
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        known.add(summary_key)
    for proposal in proposals:
        proposal.proposal_key = stable_proposal_key(
            "assistant", assistant_message.id, proposal.kind.value, proposal.payload
        )
    session.add_all(proposals)
    session.commit()
    session.refresh(assistant_message)
    for proposal in proposals:
        session.refresh(proposal)
    return AssistantChatResponse(
        message=message_response(assistant_message, proposals),
        choices=reply.choices,
        remembered=[],
        runtime="local",
    )


@router.post(
    "/chat/stream",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(enforce_generation_rate_limit)],
)
async def create_streaming_chat_turn(
    payload: AssistantStreamRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="X-Assistant-Idempotency-Key"),
) -> StreamingResponse:
    """Stream the assistant reply while committing the durable turn at completion."""
    note_request_details(request, message_length=len(payload.text))
    selected_model: str | None = None
    if payload.model is not None:
        if not uses_openrouter(get_settings()):
            raise HTTPException(422, "La sélection de modèles est réservée à OpenRouter.")
        try:
            selected_model = await run_in_threadpool(
                select_free_model, get_settings(), payload.model
            )
        except FreeModelCatalogError as error:
            raise HTTPException(
                503, "Impossible de vérifier ce modèle gratuit. Réessayez."
            ) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
    thread = get_or_create_thread(session, current_user.id)
    claimed_key: str | None = None
    previous_user_message: AssistantMessage | None = None
    try:
        if idempotency_key is not None:
            idempotency_key = idempotency_key.strip()
            if not idempotency_key or len(idempotency_key) > 128:
                raise HTTPException(status_code=422, detail="La clé d’idempotence est invalide.")
            _claim_stream_turn(thread.id, idempotency_key)
            claimed_key = idempotency_key
            previous_user_message = session.scalar(
                select(AssistantMessage).where(
                    AssistantMessage.thread_id == thread.id,
                    AssistantMessage.role == AssistantMessageRole.USER,
                    AssistantMessage.idempotency_key == idempotency_key,
                )
            )
            if previous_user_message is not None:
                if previous_user_message.content != payload.text:
                    raise HTTPException(
                        status_code=409, detail="Cette clé appartient à un autre message."
                    )
                next_user_at = session.scalar(
                    select(AssistantMessage.created_at)
                    .where(
                        AssistantMessage.thread_id == thread.id,
                        AssistantMessage.role == AssistantMessageRole.USER,
                        AssistantMessage.created_at > previous_user_message.created_at,
                    )
                    .order_by(AssistantMessage.created_at.asc())
                    .limit(1)
                )
                reply_query = select(AssistantMessage).where(
                    AssistantMessage.thread_id == thread.id,
                    AssistantMessage.role == AssistantMessageRole.ASSISTANT,
                    AssistantMessage.created_at >= previous_user_message.created_at,
                )
                if next_user_at is not None:
                    reply_query = reply_query.where(AssistantMessage.created_at < next_user_at)
                previous_assistant_message = session.scalar(
                    reply_query.order_by(AssistantMessage.created_at.asc())
                )
                if previous_assistant_message is not None:
                    previous_proposals = list(
                        session.scalars(
                            select(AssistantProposal).where(
                                AssistantProposal.assistant_message_id
                                == previous_assistant_message.id
                            )
                        )
                    )
                    replay = AssistantChatResponse(
                        message=message_response(previous_assistant_message, previous_proposals),
                        choices=[],
                        remembered=[],
                        runtime="local",
                    )

                    def replay_events() -> Iterator[str]:
                        yield _sse("complete", replay.model_dump(mode="json"))

                    _release_stream_turn(thread.id, claimed_key)
                    claimed_key = None
                    return StreamingResponse(replay_events(), media_type="text/event-stream")
                if not payload.retry:
                    raise HTTPException(
                        status_code=409, detail="Ce tour assistant est déjà en cours de traitement."
                    )
        elif payload.retry:
            raise HTTPException(status_code=422, detail="Une clé est requise pour réessayer.")

        recent_turns = recent_messages(
            session,
            thread.id,
            limit=10,
            exclude_message_id=previous_user_message.id if previous_user_message else None,
            include_sources=True,
        )
        recalled_memories = await run_in_threadpool(
            accessible_memory_summaries, session, current_user.id, limit=12, query=payload.text
        )
        personal_context = accessible_personal_context(
            session, current_user.id, limit=8, query=payload.text
        )
        if previous_user_message is None:
            user_message = AssistantMessage(
                thread_id=thread.id,
                role=AssistantMessageRole.USER,
                idempotency_key=idempotency_key,
                content=payload.text,
                created_at=datetime.now(UTC),
            )
            session.add(user_message)
            session.commit()
        else:
            user_message = previous_user_message
            session.commit()  # Persist rebuilt working context before provider work on a retry.
    except Exception:
        _release_stream_turn(thread.id, claimed_key)
        raise

    async def events() -> Iterator[str]:
        raw_content = ""
        emitted_reply = ""
        cancel_event = threading.Event()
        try:
            yield _sse("started", {"runtime": "local"})
            provider_stream = iter(
                stream_answer(
                    payload.text,
                    recent_turns,
                    recalled_memories,
                    personal_context,
                    cancel_event=cancel_event,
                    model=selected_model,
                )
            )

            def next_chunk() -> tuple[bool, str | None]:
                try:
                    return True, next(provider_stream)
                except StopIteration:
                    return False, None

            while True:
                if await request.is_disconnected():
                    cancel_event.set()
                    return
                has_chunk, chunk = await asyncio.to_thread(next_chunk)
                if not has_chunk or chunk is None:
                    break
                raw_content += chunk
                available_reply = streamed_reply_prefix(raw_content)
                if available_reply.startswith(emitted_reply) and len(available_reply) > len(
                    emitted_reply
                ):
                    delta = available_reply[len(emitted_reply) :]
                    emitted_reply = available_reply
                    yield _sse("delta", {"text": delta})
            reply = parse_streamed_answer(raw_content, payload.text)
            response = _persist_chat_reply(
                session,
                current_user.id,
                thread.id,
                reply,
                runtime="local",
                recalled_memories=recalled_memories,
                recent_turns=recent_turns,
                personal_context=personal_context,
                source_user_message_id=user_message.id,
            )
            yield _sse("complete", response.model_dump(mode="json"))
        except HTTPException as error:
            yield _sse("error", {"detail": str(error.detail), "status": error.status_code})
        except Exception:
            yield _sse(
                "error",
                {"detail": "Le flux assistant est indisponible. Réessayez.", "status": 502},
            )
        finally:
            cancel_event.set()
            _release_stream_turn(thread.id, claimed_key)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/turn",
    response_model=AssistantTurnResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_generation_rate_limit)],
)
def create_turn(
    payload: AssistantTurnRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="X-Assistant-Idempotency-Key"),
) -> AssistantTurnResponse:
    """Persist a personal exchange but never execute a proposal in this request."""
    note_request_details(request, message_length=len(payload.text))
    thread = get_or_create_thread(session, current_user.id)
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 128:
            raise HTTPException(status_code=422, detail="La clé d’idempotence est invalide.")
        previous_user_message = session.scalar(
            select(AssistantMessage).where(
                AssistantMessage.thread_id == thread.id,
                AssistantMessage.role == AssistantMessageRole.USER,
                AssistantMessage.idempotency_key == idempotency_key,
            )
        )
        if previous_user_message is not None:
            previous_assistant_message = session.scalar(
                select(AssistantMessage)
                .where(
                    AssistantMessage.thread_id == thread.id,
                    AssistantMessage.role == AssistantMessageRole.ASSISTANT,
                    AssistantMessage.created_at >= previous_user_message.created_at,
                )
                .order_by(AssistantMessage.created_at.asc())
            )
            if previous_assistant_message is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ce tour assistant est déjà en cours de traitement.",
                )
            previous_proposals = list(
                session.scalars(
                    select(AssistantProposal).where(
                        AssistantProposal.assistant_message_id == previous_assistant_message.id
                    )
                )
            )
            return AssistantTurnResponse(
                message=message_response(previous_assistant_message, previous_proposals),
                mode="llm",
            )
    recent_titles = open_task_titles(session, current_user.id, limit=8)
    recent_turns = recent_messages(session, thread.id, limit=8)
    draft = exclude_calendar_conflicts(
        session,
        current_user.id,
        propose_assistant_turn(payload.text, recent_titles, recent_turns),
    )
    session.add(
        AssistantMessage(
            thread_id=thread.id,
            role=AssistantMessageRole.USER,
            idempotency_key=idempotency_key,
            content=payload.text,
            created_at=datetime.now(UTC),
        )
    )
    assistant_message = AssistantMessage(
        thread_id=thread.id,
        role=AssistantMessageRole.ASSISTANT,
        content=draft.content,
        created_at=datetime.now(UTC),
    )
    session.add(assistant_message)
    session.flush()
    proposals = [
        AssistantProposal(
            user_id=current_user.id,
            assistant_message_id=assistant_message.id,
            kind=AssistantProposalKind(item.kind),
            payload=item.payload,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        for item in draft.proposals
    ]
    for proposal in proposals:
        proposal.proposal_key = stable_proposal_key(
            "assistant", assistant_message.id, proposal.kind.value, proposal.payload
        )
    session.add_all(proposals)
    session.commit()
    session.refresh(assistant_message)
    for proposal in proposals:
        session.refresh(proposal)
    return AssistantTurnResponse(
        message=message_response(assistant_message, proposals), mode=draft.mode
    )


@router.get("/history", response_model=AssistantHistoryResponse)
def history(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> AssistantHistoryResponse:
    thread = session.scalar(
        select(AssistantThread).where(AssistantThread.user_id == current_user.id)
    )
    if thread is None:
        return AssistantHistoryResponse(messages=[])
    messages = list(
        reversed(
            list(
                session.scalars(
                    select(AssistantMessage)
                    .where(AssistantMessage.thread_id == thread.id)
                    .order_by(AssistantMessage.created_at.desc())
                    .limit(50)
                )
            )
        )
    )
    message_ids = [message.id for message in messages]
    by_message: dict[UUID, list[AssistantProposal]] = {message.id: [] for message in messages}
    if message_ids:
        proposals = session.scalars(
            select(AssistantProposal)
            .where(
                AssistantProposal.user_id == current_user.id,
                AssistantProposal.assistant_message_id.in_(message_ids),
            )
            .order_by(AssistantProposal.created_at.asc())
        )
        for proposal in proposals:
            by_message[proposal.assistant_message_id].append(proposal)
    return AssistantHistoryResponse(
        messages=[message_response(message, by_message[message.id]) for message in messages]
    )


@router.get("/calendar/events", response_model=CalendarEventListResponse)
def list_calendar_events(
    starts_after: datetime | None = None,
    ends_before: datetime | None = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> CalendarEventListResponse:
    query = select(CalendarEvent).where(CalendarEvent.user_id == current_user.id)
    if starts_after is not None:
        query = query.where(CalendarEvent.ends_at > starts_after)
    if ends_before is not None:
        query = query.where(CalendarEvent.starts_at < ends_before)
    events = session.scalars(query.order_by(CalendarEvent.starts_at.asc()).limit(100))
    return CalendarEventListResponse(events=[calendar_event_response(event) for event in events])


@router.get("/reminders", response_model=list[RecurringReminderResponse])
def list_recurring_reminders(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[RecurringReminderResponse]:
    reminders = session.scalars(
        select(RecurringReminder)
        .where(RecurringReminder.user_id == current_user.id)
        .order_by(RecurringReminder.active.desc(), RecurringReminder.next_due_date.asc())
    )
    return [recurring_reminder_response(reminder) for reminder in reminders]


@router.patch("/reminders/{reminder_id}", response_model=RecurringReminderResponse)
def update_recurring_reminder(
    reminder_id: UUID,
    payload: RecurringReminderUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RecurringReminderResponse:
    reminder = session.scalar(
        select(RecurringReminder).where(
            RecurringReminder.id == reminder_id, RecurringReminder.user_id == current_user.id
        )
    )
    if reminder is None:
        raise HTTPException(status_code=404, detail="Rappel introuvable.")
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return recurring_reminder_response(reminder)
    if "timezone" in data:
        try:
            ZoneInfo(data["timezone"])
        except ZoneInfoNotFoundError as error:
            raise HTTPException(status_code=422, detail="Fuseau horaire invalide.") from error
    reset_schedule = "anchor_date" in data or "recurrence_months" in data
    for field, value in data.items():
        setattr(reminder, field, value)
    if reset_schedule:
        reminder.next_due_date, reminder.next_reminder_at = recurring_schedule(
            RecurringReminderProposalPayload(
                title=reminder.title,
                anchor_date=reminder.anchor_date,
                recurrence_months=reminder.recurrence_months,
                lead_days=reminder.lead_days,
                timezone=reminder.timezone,
            )
        )
    elif "lead_days" in data or "timezone" in data:
        reminder.next_reminder_at = deadline_schedule(
            DeadlineReminderProposalPayload(
                title=reminder.title,
                due_date=reminder.next_due_date,
                lead_days=reminder.lead_days,
                timezone=reminder.timezone,
            )
        )
    session.commit()
    session.refresh(reminder)
    return recurring_reminder_response(reminder)


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_recurring_reminder(
    reminder_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    reminder = session.scalar(
        select(RecurringReminder).where(
            RecurringReminder.id == reminder_id, RecurringReminder.user_id == current_user.id
        )
    )
    if reminder is None:
        raise HTTPException(status_code=404, detail="Rappel introuvable.")
    reminder.active = False
    prefix = f"recurring-reminder:{reminder.id}:"
    pending = session.scalars(
        select(NotificationOutbox).where(
            NotificationOutbox.user_id == current_user.id,
            NotificationOutbox.dedupe_key.startswith(prefix),
            NotificationOutbox.sent_at.is_(None),
            NotificationOutbox.failed_at.is_(None),
            NotificationOutbox.cancelled_at.is_(None),
        )
    )
    for item in pending:
        item.cancelled_at = datetime.now(UTC)
        item.lease_owner = None
        item.lease_until = None
    session.commit()


@router.get("/notifications", response_model=list[NotificationResponse])
def list_notifications(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[NotificationResponse]:
    items = session.scalars(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.user_id == current_user.id,
            NotificationOutbox.cancelled_at.is_(None),
            NotificationOutbox.read_at.is_(None),
            ~NotificationOutbox.dedupe_key.startswith("secret-nudge:"),
        )
        .order_by(NotificationOutbox.created_at.desc())
        .limit(100)
    )
    return [notification_response(item) for item in items]


@router.post(
    "/notifications/test",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_test_notification(
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: Session = Depends(get_session),
) -> NotificationResponse:
    """Send a generic push to the current device without a scheduler."""
    current_user = authenticated.user
    device = authenticated.user_session.device
    require_active_consent(session, current_user.id, "notifications.push")
    if device.platform == "web":
        settings = get_settings()
        if not all((settings.web_push_public_key, settings.web_push_private_key)) or not (
            settings.web_push_subject or ""
        ).startswith(("mailto:", "https://")):
            raise HTTPException(
                status_code=503, detail="Configuration VAPID incomplète ou invalide."
            )
        if (
            session.scalar(
                select(WebPushSubscription.id)
                .where(
                    WebPushSubscription.user_id == current_user.id,
                    WebPushSubscription.device_id == device.id,
                )
                .limit(1)
            )
            is None
        ):
            raise HTTPException(
                status_code=409, detail="Activez d'abord les notifications du navigateur."
            )
    elif not device.push_token:
        raise HTTPException(status_code=409, detail="Activez d'abord les notifications mobiles.")
    now = datetime.now(UTC)
    recent_tests = session.scalar(
        select(func.count(NotificationOutbox.id)).where(
            NotificationOutbox.user_id == current_user.id,
            NotificationOutbox.dedupe_key.startswith("web-push-test:"),
            NotificationOutbox.created_at >= now - timedelta(hours=1),
        )
    )
    if recent_tests is not None and recent_tests >= 5:
        raise HTTPException(status_code=429, detail="Limite de cinq tests par heure atteinte.")
    item = NotificationOutbox(
        user_id=current_user.id,
        dedupe_key=f"web-push-test:{uuid4()}",
        title="Cocoon",
        body="Ceci est une notification de test.",
        data={"kind": "notification_test", "device_id": str(device.id)},
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    item_id = item.id
    session.close()
    try:
        send_pending_notifications(datetime.now(UTC), max_items=1, item_id=item_id)
    except Exception:
        notification_logger.exception("notification_test_dispatch_failed")
    updated = session.get(NotificationOutbox, item_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Notification introuvable.")
    return notification_response(updated)


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> NotificationResponse:
    item = session.scalar(
        select(NotificationOutbox).where(
            NotificationOutbox.id == notification_id,
            NotificationOutbox.user_id == current_user.id,
            NotificationOutbox.cancelled_at.is_(None),
            ~NotificationOutbox.dedupe_key.startswith("secret-nudge:"),
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Notification introuvable.")
    if item.read_at is None:
        item.read_at = datetime.now(UTC)
        session.commit()
        session.refresh(item)
    return notification_response(item)


@router.post("/proposals/{proposal_id}/confirm", response_model=AssistantProposalResponse)
def confirm_proposal(
    proposal_id: UUID,
    proposal_version: int | None = Header(default=None, alias="X-Proposal-Version", ge=1),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AssistantProposalResponse:
    proposal, already_confirmed = prepare_proposal_confirmation(
        session,
        model=AssistantProposal,
        proposal_id=proposal_id,
        user_id=current_user.id,
        proposal_type="assistant",
        pending_status=AssistantProposalStatus.PENDING,
        confirmed_status=AssistantProposalStatus.CONFIRMED,
        cancelled_status=AssistantProposalStatus.CANCELLED,
        expired_status=AssistantProposalStatus.EXPIRED,
        failed_status=AssistantProposalStatus.FAILED,
        expected_payload_version=proposal_version,
        expired_detail=(
            "Cette proposition a expiré. Demandez une nouvelle proposition à l’assistant."
        ),
    )
    if already_confirmed:
        return proposal_response(proposal)

    try:
        resource = execute_assistant_proposal(session, proposal, current_user.id)
    except ValidationError as error:
        record_failed_proposal(
            session,
            proposal=proposal,
            proposal_type="assistant",
            failed_status=AssistantProposalStatus.FAILED,
            user_id=current_user.id,
            error_code="invalid_payload",
        )
        session.commit()
        raise HTTPException(status_code=422, detail="La proposition est invalide.") from error
    proposal.status = AssistantProposalStatus.CONFIRMED
    proposal.confirmed_resource_id = resource.id
    proposal.confirmed_at = datetime.now(UTC)
    session.query(AssistantProposal).filter(
        AssistantProposal.user_id == current_user.id,
        AssistantProposal.assistant_message_id == proposal.assistant_message_id,
        AssistantProposal.id != proposal.id,
        AssistantProposal.status == AssistantProposalStatus.PENDING,
    ).update(
        {AssistantProposal.status: AssistantProposalStatus.CANCELLED},
        synchronize_session=False,
    )
    record_proposal_execution(
        session,
        proposal_type="assistant",
        proposal_id=proposal.id,
        user_id=current_user.id,
        resource_id=resource.id,
        completed_at=proposal.confirmed_at,
    )
    session.commit()
    session.refresh(proposal)
    return proposal_response(proposal)


@router.post("/proposals/{proposal_id}/cancel", response_model=AssistantProposalResponse)
def cancel_proposal(
    proposal_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AssistantProposalResponse:
    proposal = session.scalar(
        select(AssistantProposal)
        .where(AssistantProposal.id == proposal_id, AssistantProposal.user_id == current_user.id)
        .with_for_update()
    )
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Proposition introuvable."
        )
    if proposal.status is AssistantProposalStatus.CONFIRMED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cette proposition est déjà confirmée."
        )
    if proposal.status is AssistantProposalStatus.PENDING:
        proposal.status = AssistantProposalStatus.CANCELLED
        session.commit()
        session.refresh(proposal)
    return proposal_response(proposal)


@router.get("/briefing", response_model=AssistantBriefingResponse)
def briefing(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> AssistantBriefingResponse:
    tasks = list(
        session.scalars(
            select(PersonalTask)
            .where(PersonalTask.user_id == current_user.id, PersonalTask.completed.is_(False))
            .order_by(
                PersonalTask.priority.desc(),
                PersonalTask.due_date.asc(),
                PersonalTask.created_at.asc(),
            )
            .limit(3)
        )
    )
    task_titles = [task.title for task in tasks]
    summary = (
        "Votre journée est dégagée pour le moment."
        if not task_titles
        else f"{len(task_titles)} priorité{'s' if len(task_titles) > 1 else ''} à garder en vue."
    )
    return AssistantBriefingResponse(
        heading="Votre point du jour",
        summary=summary,
        tasks=task_titles,
        generated_at=datetime.now(UTC),
    )


@router.get("/brief-settings", response_model=DailyBriefSettings)
def get_brief_settings(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> DailyBriefSettings:
    preference = session.get(AssistantPreference, current_user.id)
    if preference is None:
        return DailyBriefSettings()
    return DailyBriefSettings(
        timezone=preference.timezone,
        delivery_time=preference.delivery_time,
        enabled=preference.enabled,
        daily_notification_quota=preference.daily_notification_quota,
    )


@router.put("/brief-settings", response_model=DailyBriefSettings)
def update_brief_settings(
    payload: DailyBriefSettings,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> DailyBriefSettings:
    try:
        ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(status_code=422, detail="Fuseau horaire invalide.") from error
    preference = session.get(AssistantPreference, current_user.id) or AssistantPreference(
        user_id=current_user.id
    )
    preference.timezone = payload.timezone
    preference.delivery_time = payload.delivery_time
    preference.enabled = payload.enabled
    preference.daily_notification_quota = payload.daily_notification_quota
    session.add(preference)
    session.commit()
    return payload


@router.post(
    "/organize",
    response_model=ThoughtOrganizationResponse,
    dependencies=[Depends(enforce_generation_rate_limit)],
)
def organize(
    payload: ThoughtOrganizationRequest,
    current_user: User = Depends(get_current_user),
) -> ThoughtOrganizationResponse:
    """Compatibility endpoint: it classifies a thought but never persists it."""
    del current_user
    return organize_thought(payload)


@router.post(
    "/meal-plan",
    response_model=GroceryMealPlanResponse,
    dependencies=[Depends(enforce_generation_rate_limit)],
)
def create_meal_plan(
    payload: GroceryMealPlanRequest,
    current_user: User = Depends(get_current_user),
) -> GroceryMealPlanResponse:
    """Plan meals from the explicitly submitted grocery-list snapshot only."""
    del current_user
    return plan_grocery_meals(payload)
