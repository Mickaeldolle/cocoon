import json
from datetime import UTC, datetime, time
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.assistant.executor import execute_capture_proposal
from app.modules.assistant.proposal_types import ProposalStatus
from app.modules.assistant.proposals import (
    prepare_proposal_confirmation,
    record_failed_proposal,
    record_proposal_execution,
)
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.neural.models import (
    Capture,
    CaptureRun,
    CaptureRunEvent,
    CaptureRunStatus,
    CaptureSource,
    MemoryItem,
    MemoryState,
    NeuralProposal,
)
from app.modules.neural.schemas import (
    CaptureCreate,
    CaptureResponse,
    CaptureRunEventResponse,
    CaptureRunResponse,
    HomeResponse,
    HomeSignal,
    ProposalResponse,
)
from app.modules.neural.service import parse_reminder_at, safe_timezone, understand
from app.modules.neural.worker import create_capture_run, process_capture_run
from app.modules.personal.models import PersonalTask

router = APIRouter(prefix="/api", tags=["neural"])


def proposal_response(item: NeuralProposal) -> ProposalResponse:
    return ProposalResponse(
        id=item.id,
        capability=item.capability,
        payload=item.payload,
        payload_version=item.payload_version,
        reason=item.reason,
        status=item.status,
        confirmed_at=item.confirmed_at,
        label=str(item.payload.get("label") or item.payload.get("title") or item.capability),
    )


def _capture(session: Session, current_user: User, payload: CaptureCreate) -> CaptureResponse:
    content = " ".join(payload.text.split())
    capture = Capture(
        user_id=current_user.id,
        source=CaptureSource.TEXT,
        content=content,
        timezone=safe_timezone(payload.timezone).key,
    )
    session.add(capture)
    session.flush()
    run = CaptureRun(user_id=current_user.id, capture_id=capture.id)
    session.add(run)
    session.flush()
    session.add(
        CaptureRunEvent(
            run_id=run.id,
            sequence=1,
            event_type="capture_persisted",
            payload={"source": capture.source.value},
        )
    )
    # Persist the raw signal before any model work so interruptions never lose it.
    session.commit()
    result = understand(content)
    proposals: list[NeuralProposal] = []
    due_date = result.payload.get("due_date")
    reminder_at = parse_reminder_at(content, payload.timezone, result.review_at)
    if result.capability == "reminder":
        if reminder_at is None and result.review_at is not None:
            local_date = result.review_at.astimezone(safe_timezone(payload.timezone)).date()
            reminder_at = datetime.combine(
                local_date,
                time(9, 0),
                tzinfo=safe_timezone(payload.timezone),
            ).astimezone(UTC)
        task_payload = {
            "title": str(result.payload.get("title") or result.summary)[:160],
            "due_date": due_date,
            "reminder_at": reminder_at.isoformat() if reminder_at else None,
        }
        proposals.append(
            NeuralProposal(
                user_id=current_user.id,
                capture_id=capture.id,
                capability="reminder",
                payload=task_payload,
                reason="Rendez-vous daté : je vous propose un rappel pour ne pas le manquer.",
            )
        )
    elif result.capability == "task":
        task_payload = {
            "title": str(result.payload.get("title") or result.summary)[:160],
            "due_date": due_date,
        }
        proposals.append(
            NeuralProposal(
                user_id=current_user.id,
                capture_id=capture.id,
                capability="task",
                payload=task_payload,
                reason="Créer une tâche personnelle à partir de cette capture.",
            )
        )
        if reminder_at is not None:
            proposals.append(
                NeuralProposal(
                    user_id=current_user.id,
                    capture_id=capture.id,
                    capability="reminder",
                    payload={**task_payload, "reminder_at": reminder_at.isoformat()},
                    reason="Créer la tâche et programmer le rappel demandé.",
                )
            )
        proposals.append(
            NeuralProposal(
                user_id=current_user.id,
                capture_id=capture.id,
                capability="note",
                payload={"summary": result.summary, "kind": result.kind.value},
                reason="Conserver cette capture comme pensée personnelle.",
            )
        )
    elif not result.clarification:
        proposals.append(
            NeuralProposal(
                user_id=current_user.id,
                capture_id=capture.id,
                capability="note",
                payload={"summary": result.summary, "kind": result.kind.value},
                reason="Conserver cette capture comme pensée personnelle.",
            )
        )
    session.add_all(proposals)
    run.status = CaptureRunStatus.COMPLETED
    run.finished_at = datetime.now(UTC)
    session.add(
        CaptureRunEvent(
            run_id=run.id,
            sequence=2,
            event_type="completed",
            payload={"proposal_count": len(proposals)},
        )
    )
    session.commit()
    for item in proposals:
        session.refresh(item)
    return CaptureResponse(
        id=capture.id,
        run_id=run.id,
        summary=result.summary,
        clarification=result.clarification,
        proposals=[proposal_response(item) for item in proposals[:3]],
        mode=result.mode,
    )


@router.get("/runs/{run_id}", response_model=CaptureRunResponse)
def get_capture_run(
    run_id: UUID,
    after_sequence: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> CaptureRunResponse:
    run = session.scalar(
        select(CaptureRun).where(CaptureRun.id == run_id, CaptureRun.user_id == current_user.id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Exécution introuvable.")
    events = list(
        session.scalars(
            select(CaptureRunEvent)
            .where(
                CaptureRunEvent.run_id == run.id,
                CaptureRunEvent.sequence > after_sequence,
            )
            .order_by(CaptureRunEvent.sequence.asc())
        )
    )
    return CaptureRunResponse(
        id=run.id,
        capture_id=run.capture_id,
        status=run.status.value,
        attempt=run.attempt,
        error_code=run.error_code,
        created_at=run.created_at,
        finished_at=run.finished_at,
        events=[
            CaptureRunEventResponse(
                sequence=event.sequence,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at,
            )
            for event in events
        ],
    )


@router.post("/runs/{run_id}/cancel", response_model=CaptureRunResponse)
def cancel_capture_run(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> CaptureRunResponse:
    run = session.scalar(
        select(CaptureRun)
        .where(CaptureRun.id == run_id, CaptureRun.user_id == current_user.id)
        .with_for_update()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Exécution introuvable.")
    if run.status is CaptureRunStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Cette exécution est déjà terminée.")
    if run.status is CaptureRunStatus.CANCELLED:
        return get_capture_run(run_id, 0, current_user, session)
    run.status = CaptureRunStatus.CANCELLED
    run.finished_at = datetime.now(UTC)
    run.cancelled_at = datetime.now(UTC)
    run.lease_owner = None
    run.lease_until = None
    next_sequence = session.scalar(
        select(CaptureRunEvent.sequence)
        .where(CaptureRunEvent.run_id == run.id)
        .order_by(CaptureRunEvent.sequence.desc())
        .limit(1)
    ) or 0
    session.add(
        CaptureRunEvent(
            run_id=run.id,
            sequence=next_sequence + 1,
            event_type="cancelled",
            payload={},
        )
    )
    session.commit()
    return get_capture_run(run_id, 0, current_user, session)
def _capture(
    session: Session,
    current_user: User,
    payload: CaptureCreate,
    idempotency_key: str | None = None,
) -> CaptureResponse:
    run = create_capture_run(session, current_user, payload, idempotency_key)
    return process_capture_run(session, run.id)


@router.post("/captures", response_model=CaptureResponse, status_code=201)
def create_capture(
    payload: CaptureCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="X-Capture-Idempotency-Key"),
) -> CaptureResponse:
    if idempotency_key is not None and not idempotency_key.strip():
        raise HTTPException(status_code=422, detail="La clé d’idempotence est invalide.")
    if idempotency_key is not None and len(idempotency_key) > 128:
        raise HTTPException(status_code=422, detail="La clé d’idempotence est trop longue.")
    return _capture(session, current_user, payload, idempotency_key)


@router.post("/captures/queue", response_model=CaptureRunResponse, status_code=202)
def queue_capture(
    payload: CaptureCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="X-Capture-Idempotency-Key"),
) -> CaptureRunResponse:
    """Persist a capture and return before model work for a separate worker."""
    if idempotency_key is not None and not idempotency_key.strip():
        raise HTTPException(status_code=422, detail="La clé d’idempotence est invalide.")
    if idempotency_key is not None and len(idempotency_key) > 128:
        raise HTTPException(status_code=422, detail="La clé d’idempotence est trop longue.")
    run = create_capture_run(session, current_user, payload, idempotency_key)
    return get_capture_run(run.id, 0, current_user, session)


@router.post("/captures/stream")
def stream_capture(
    payload: CaptureCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="X-Capture-Idempotency-Key"),
    last_event_id: int = Header(default=0, ge=0, alias="Last-Event-ID"),
) -> StreamingResponse:
    if idempotency_key is not None and not idempotency_key.strip():
        raise HTTPException(status_code=422, detail="La clé d’idempotence est invalide.")
    if idempotency_key is not None and len(idempotency_key) > 128:
        raise HTTPException(status_code=422, detail="La clé d’idempotence est trop longue.")
    run = create_capture_run(session, current_user, payload, idempotency_key)

    def encode_events(after_sequence: int):
        events = list(
            session.scalars(
                select(CaptureRunEvent)
                .where(
                    CaptureRunEvent.run_id == run.id,
                    CaptureRunEvent.sequence > after_sequence,
                )
                .order_by(CaptureRunEvent.sequence.asc())
            )
        )
        cursor = after_sequence
        for event in events:
            data = json.dumps(
                {
                    "run_id": str(run.id),
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                },
                ensure_ascii=False,
            )
            cursor = event.sequence
            yield cursor, f"id: {event.sequence}\nevent: run_event\ndata: {data}\n\n"

    def events():
        cursor = last_event_id
        try:
            # Flush the durable acknowledgement before starting model work. This
            # gives clients a real first event and a safe Last-Event-ID cursor.
            for event_cursor, encoded in encode_events(cursor):
                cursor = event_cursor
                yield encoded
            result = process_capture_run(session, run.id)
            for event_cursor, encoded in encode_events(cursor):
                cursor = event_cursor
                yield encoded
            yield f"id: {cursor}\nevent: complete\ndata: {result.model_dump_json()}\n\n"
        except Exception as error:
            session.rollback()
            for event_cursor, encoded in encode_events(cursor):
                cursor = event_cursor
                yield encoded
            detail = (
                error.detail
                if isinstance(error, HTTPException) and isinstance(error.detail, str)
                else "La capture brute est conservée. Réessayez."
            )
            data = json.dumps({"detail": detail}, ensure_ascii=False)
            yield f"event: error\ndata: {data}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/neural-proposals/{proposal_id}/confirm", response_model=ProposalResponse)
def confirm(
    proposal_id: UUID,
    proposal_version: int | None = Header(default=None, alias="X-Proposal-Version", ge=1),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProposalResponse:
    proposal, already_confirmed = prepare_proposal_confirmation(
        session,
        model=NeuralProposal,
        proposal_id=proposal_id,
        user_id=current_user.id,
        proposal_type="capture",
        pending_status="pending",
        confirmed_status="confirmed",
        cancelled_status="cancelled",
        expired_status="expired",
        failed_status="failed",
        expected_payload_version=proposal_version,
        expired_detail="Cette proposition a expiré. Faites une nouvelle capture.",
    )
    if already_confirmed:
        return proposal_response(proposal)
    try:
        execute_capture_proposal(session, proposal, current_user.id)
    except HTTPException as error:
        if error.status_code != 422:
            raise
        record_failed_proposal(
            session,
            proposal=proposal,
            proposal_type="capture",
            failed_status="failed",
            user_id=current_user.id,
            error_code="invalid_payload",
        )
        session.commit()
        raise HTTPException(status_code=422, detail="La proposition est invalide.") from error
    session.query(NeuralProposal).filter(
        NeuralProposal.capture_id == proposal.capture_id,
        NeuralProposal.id != proposal.id,
        NeuralProposal.status == "pending",
    ).update({NeuralProposal.status: "cancelled"}, synchronize_session=False)
    proposal.status = "confirmed"
    proposal.confirmed_at = datetime.now(UTC)
    record_proposal_execution(
        session,
        proposal_type="capture",
        proposal_id=proposal.id,
        user_id=current_user.id,
        resource_id=proposal.confirmed_resource_id,
        completed_at=proposal.confirmed_at,
    )
    session.commit()
    return proposal_response(proposal)


@router.post("/neural-proposals/{proposal_id}/cancel", response_model=ProposalResponse)
def cancel(
    proposal_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProposalResponse:
    proposal = session.scalar(
        select(NeuralProposal)
        .where(NeuralProposal.id == proposal_id, NeuralProposal.user_id == current_user.id)
        .with_for_update()
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposition introuvable.")
    if proposal.status in {
        ProposalStatus.CONFIRMED,
        ProposalStatus.EXPIRED,
        ProposalStatus.FAILED,
    }:
        raise HTTPException(status_code=409, detail="Cette proposition est déjà terminée.")
    if proposal.status == ProposalStatus.PENDING:
        proposal.status = ProposalStatus.CANCELLED
        session.commit()
        session.refresh(proposal)
    return proposal_response(proposal)


@router.get("/home", response_model=HomeResponse)
def home(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> HomeResponse:
    signals: list[HomeSignal] = []
    pending = list(
        session.scalars(
            select(NeuralProposal)
            .where(NeuralProposal.user_id == current_user.id, NeuralProposal.status == "pending")
            .order_by(NeuralProposal.created_at.desc())
            .limit(1)
        )
    )
    for proposal in pending:
        title = str(proposal.payload.get("title") or "Proposition à confirmer")[:240]
        signals.append(
            HomeSignal(
                id=proposal.id,
                kind="confirm",
                title=title,
                reason=proposal.reason,
                source="Capture personnelle",
                proposal_id=proposal.id,
                payload_version=proposal.payload_version,
            )
        )
    stale = list(
        session.scalars(
            select(MemoryItem)
            .where(
                MemoryItem.user_id == current_user.id,
                MemoryItem.state == MemoryState.ACTIVE,
                MemoryItem.review_at.is_not(None),
                MemoryItem.review_at <= datetime.now(UTC),
            )
            .order_by(MemoryItem.review_at.asc())
            .limit(2)
        )
    )
    for item in stale:
        signals.append(
            HomeSignal(
                id=item.id,
                kind="review",
                title=item.summary,
                reason="Cette information mérite d'être vérifiée.",
                source="Mémoire personnelle",
            )
        )
    tasks = list(
        session.scalars(
            select(PersonalTask)
            .where(PersonalTask.user_id == current_user.id, PersonalTask.completed.is_(False))
            .order_by(PersonalTask.due_date.asc())
            .limit(1)
        )
    )
    for task in tasks:
        signals.append(
            HomeSignal(
                id=task.id,
                kind="now",
                title=task.title,
                reason="Action personnelle en attente.",
                source="Action confirmée",
            )
        )
    return HomeResponse(signals=signals[:3])
