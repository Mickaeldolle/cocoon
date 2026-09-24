"""Durable processing path for universal capture runs.

The first MVP worker is callable synchronously by the HTTP endpoint. Keeping
creation and processing in this module gives a future queue worker the same
idempotent, cancellable and failure-aware contract without duplicating domain
logic.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.auth.models import User
from app.modules.neural.models import (
    Capture,
    CaptureRun,
    CaptureRunEvent,
    CaptureRunStatus,
    CaptureSource,
    NeuralProposal,
)
from app.modules.neural.schemas import CaptureCreate, CaptureResponse, ProposalResponse
from app.modules.neural.service import parse_reminder_at, safe_timezone, understand


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


def proposal_key(capture_id: UUID, capability: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
    return f"{capture_id}:{capability}:{digest}"


def _next_sequence(session: Session, run_id: UUID) -> int:
    return (
        session.scalar(
            select(CaptureRunEvent.sequence)
            .where(CaptureRunEvent.run_id == run_id)
            .order_by(CaptureRunEvent.sequence.desc())
            .limit(1)
        )
        or 0
    ) + 1


def _add_event(
    session: Session, run_id: UUID, event_type: str, payload: dict[str, object]
) -> None:
    session.add(
        CaptureRunEvent(
            run_id=run_id,
            sequence=_next_sequence(session, run_id),
            event_type=event_type,
            payload=payload,
        )
    )


def _response_from_run(session: Session, run: CaptureRun) -> CaptureResponse:
    capture = session.get(Capture, run.capture_id)
    if capture is None:
        raise HTTPException(status_code=500, detail="La capture associée est introuvable.")
    completed = session.scalar(
        select(CaptureRunEvent)
        .where(CaptureRunEvent.run_id == run.id, CaptureRunEvent.event_type == "completed")
        .order_by(CaptureRunEvent.sequence.desc())
    )
    payload = completed.payload if completed else {}
    proposals = list(
        session.scalars(
            select(NeuralProposal)
            .where(NeuralProposal.capture_id == capture.id)
            .order_by(NeuralProposal.created_at.asc())
            .limit(3)
        )
    )
    clarification = payload.get("clarification")
    return CaptureResponse(
        id=capture.id,
        run_id=run.id,
        summary=str(payload.get("summary") or capture.content[:240]),
        clarification=clarification if isinstance(clarification, str) else None,
        proposals=[proposal_response(item) for item in proposals],
        mode="llm" if payload.get("mode") == "llm" else "rules",
    )


def create_capture_run(
    session: Session,
    current_user: User,
    payload: CaptureCreate,
    idempotency_key: str | None = None,
) -> CaptureRun:
    """Persist a capture and its run before any model work."""
    content = " ".join(payload.text.split())
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if idempotency_key:
        existing = session.scalar(
            select(CaptureRun).where(
                CaptureRun.user_id == current_user.id,
                CaptureRun.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.status is CaptureRunStatus.COMPLETED:
                return existing
            if existing.status is CaptureRunStatus.RUNNING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cette capture est déjà en cours de traitement.",
                )
            if existing.status is CaptureRunStatus.CANCELLED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cette capture a été annulée. Utilisez une nouvelle clé.",
                )
            if existing.attempt >= existing.max_attempts:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cette capture a atteint le nombre maximal de tentatives.",
                )
            existing.status = CaptureRunStatus.QUEUED
            existing.finished_at = None
            existing.lease_owner = None
            existing.lease_until = None
            _add_event(session, existing.id, "retry_scheduled", {"attempt": existing.attempt})
            session.commit()
            return existing

    # A retry without a client key can still be recognized by the durable
    # normalized content hash. Scope the lookup to the owner and only reuse a
    # completed run; an active run is reported instead of creating a duplicate.
    duplicate = session.scalar(
        select(CaptureRun)
        .join(Capture, Capture.id == CaptureRun.capture_id)
        .where(CaptureRun.user_id == current_user.id, Capture.content_hash == content_hash)
        .order_by(CaptureRun.created_at.desc())
    )
    if duplicate is not None:
        if duplicate.status is CaptureRunStatus.COMPLETED:
            return duplicate
        if duplicate.status in {CaptureRunStatus.QUEUED, CaptureRunStatus.RUNNING}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cette capture identique est déjà en cours de traitement.",
            )

    capture = Capture(
        user_id=current_user.id,
        source=CaptureSource.TEXT,
        content=content,
        content_hash=content_hash,
        timezone=safe_timezone(payload.timezone).key,
    )
    session.add(capture)
    session.flush()
    run = CaptureRun(
        user_id=current_user.id,
        capture_id=capture.id,
        idempotency_key=idempotency_key,
    )
    session.add(run)
    session.flush()
    _add_event(session, run.id, "capture_persisted", {"source": capture.source.value})
    session.commit()
    return run


def _claim_run(session: Session, run_id: UUID, worker_id: str) -> CaptureRun:
    now = datetime.now(UTC)
    run = session.scalar(select(CaptureRun).where(CaptureRun.id == run_id).with_for_update())
    if run is None:
        raise HTTPException(status_code=404, detail="Exécution introuvable.")
    if run.status is CaptureRunStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Cette exécution a été annulée.")
    if run.status is CaptureRunStatus.COMPLETED:
        return run
    if (
        run.status is CaptureRunStatus.RUNNING
        and run.lease_owner not in {None, worker_id}
        and run.lease_until is not None
        and run.lease_until > now
    ):
        raise HTTPException(status_code=409, detail="Cette exécution est déjà prise en charge.")
    if run.attempt > run.max_attempts:
        run.status = CaptureRunStatus.FAILED
        run.error_code = "max_attempts_exceeded"
        run.finished_at = now
        session.commit()
        raise HTTPException(status_code=409, detail="Cette exécution a échoué définitivement.")
    if run.status is CaptureRunStatus.QUEUED and run.error_code is not None:
        run.attempt += 1
    run.status = CaptureRunStatus.RUNNING
    run.lease_owner = worker_id
    run.lease_until = now + timedelta(seconds=get_settings().worker_lease_seconds)
    run.error_code = None
    run.updated_at = now
    _add_event(session, run.id, "claimed", {"attempt": run.attempt})
    session.commit()
    return run


def process_capture_run(
    session: Session, run_id: UUID, *, worker_id: str | None = None
) -> CaptureResponse:
    """Process one run with durable stage events and terminal failure state."""
    run = session.get(CaptureRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Exécution introuvable.")
    if run.status is CaptureRunStatus.COMPLETED:
        return _response_from_run(session, run)
    if run.status is CaptureRunStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Cette exécution a été annulée.")

    run = _claim_run(session, run_id, worker_id or f"http-{uuid4()}")
    if run.status is CaptureRunStatus.COMPLETED:
        return _response_from_run(session, run)

    capture = session.get(Capture, run.capture_id)
    if capture is None:
        raise HTTPException(status_code=500, detail="La capture associée est introuvable.")

    try:
        session.expire_all()
        run = session.get(CaptureRun, run_id)
        if run is None or run.status is CaptureRunStatus.CANCELLED:
            raise HTTPException(status_code=409, detail="Cette exécution a été annulée.")
        _add_event(session, run.id, "understand_started", {})
        session.commit()

        result = understand(capture.content)
        proposals: list[NeuralProposal] = []
        due_date = result.payload.get("due_date")
        reminder_at = parse_reminder_at(capture.content, capture.timezone, result.review_at)
        if result.capability == "reminder":
            if reminder_at is None and result.review_at is not None:
                local_date = result.review_at.astimezone(safe_timezone(capture.timezone)).date()
                reminder_at = datetime.combine(
                    local_date,
                    time(9, 0),
                    tzinfo=safe_timezone(capture.timezone),
                ).astimezone(UTC)
            task_payload = {
                "title": str(result.payload.get("title") or result.summary)[:160],
                "due_date": due_date,
                "reminder_at": reminder_at.isoformat() if reminder_at else None,
            }
            proposals.append(
                NeuralProposal(
                    user_id=run.user_id,
                    capture_id=capture.id,
                    capability="reminder",
                    proposal_key=proposal_key(capture.id, "reminder", task_payload),
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
                    user_id=run.user_id,
                    capture_id=capture.id,
                    capability="task",
                    proposal_key=proposal_key(capture.id, "task", task_payload),
                    payload=task_payload,
                    reason="Créer une tâche personnelle à partir de cette capture.",
                )
            )
            if reminder_at is not None:
                proposals.append(
                    NeuralProposal(
                        user_id=run.user_id,
                        capture_id=capture.id,
                        capability="reminder",
                        proposal_key=proposal_key(
                            capture.id,
                            "reminder",
                            {**task_payload, "reminder_at": reminder_at.isoformat()},
                        ),
                        payload={**task_payload, "reminder_at": reminder_at.isoformat()},
                        reason="Créer la tâche et programmer le rappel demandé.",
                    )
                )
            proposals.append(
                NeuralProposal(
                    user_id=run.user_id,
                    capture_id=capture.id,
                    capability="note",
                    proposal_key=proposal_key(
                        capture.id,
                        "note",
                        {"summary": result.summary, "kind": result.kind.value},
                    ),
                    payload={"summary": result.summary, "kind": result.kind.value},
                    reason="Conserver cette capture comme pensée personnelle.",
                )
            )
        elif not result.clarification:
            proposals.append(
                NeuralProposal(
                    user_id=run.user_id,
                    capture_id=capture.id,
                    capability="note",
                    proposal_key=proposal_key(
                        capture.id,
                        "note",
                        {"summary": result.summary, "kind": result.kind.value},
                    ),
                    payload={"summary": result.summary, "kind": result.kind.value},
                    reason="Conserver cette capture comme pensée personnelle.",
                )
            )
        # The understanding call can take long enough for the user to cancel the
        # run from another request. Re-read the durable state before creating any
        # proposal so cancellation cannot be followed by a late commit.
        session.expire_all()
        current_run = session.get(CaptureRun, run_id)
        if current_run is None or current_run.status is CaptureRunStatus.CANCELLED:
            raise HTTPException(status_code=409, detail="Cette exécution a été annulée.")
        run = current_run
        for proposal in proposals:
            proposal.source_run_id = run.id
        session.add_all(proposals)
        run.status = CaptureRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.lease_owner = None
        run.lease_until = None
        run.updated_at = datetime.now(UTC)
        _add_event(
            session,
            run.id,
            "completed",
            {
                "proposal_count": len(proposals),
                "summary": result.summary,
                "clarification": result.clarification,
                "mode": result.mode,
            },
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
    except Exception as error:
        session.rollback()
        failed_run = session.get(CaptureRun, run_id)
        if failed_run is not None and failed_run.status not in {
            CaptureRunStatus.COMPLETED,
            CaptureRunStatus.CANCELLED,
        }:
            error_code = (
                "provider_unavailable"
                if isinstance(error, HTTPException) and error.status_code == 503
                else "processing_failed"
            )
            retryable = failed_run.attempt < failed_run.max_attempts
            failed_run.status = CaptureRunStatus.QUEUED if retryable else CaptureRunStatus.FAILED
            failed_run.error_code = error_code
            failed_run.finished_at = None if retryable else datetime.now(UTC)
            failed_run.lease_owner = None
            failed_run.lease_until = None
            _add_event(
                session,
                failed_run.id,
                "failed",
                {"error_code": error_code, "retryable": retryable},
            )
            session.commit()
        raise


def process_next_pending_run(session: Session, worker_id: str) -> UUID | None:
    """Claim and process one queued or lease-expired run for an external worker."""
    now = datetime.now(UTC)
    run = session.scalar(
        select(CaptureRun)
        .where(
            (CaptureRun.status == CaptureRunStatus.QUEUED)
            | (
                (CaptureRun.status == CaptureRunStatus.RUNNING)
                & (CaptureRun.lease_until.is_not(None))
                & (CaptureRun.lease_until <= now)
            )
        )
        .order_by(CaptureRun.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if run is None:
        return None
    run_id = run.id
    session.commit()
    process_capture_run(session, run_id, worker_id=worker_id)
    return run_id
