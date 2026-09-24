"""Shared proposal execution primitives used by assistant and capture routes."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.assistant.models import ProposalExecution


def prepare_proposal_confirmation(
    session: Session,
    *,
    model: Any,
    proposal_id: UUID,
    user_id: UUID,
    proposal_type: str,
    pending_status: Any,
    confirmed_status: Any,
    cancelled_status: Any,
    expired_status: Any,
    failed_status: Any | None = None,
    expected_payload_version: int | None = None,
    not_found_detail: str = "Proposition introuvable.",
    expired_detail: str = "Cette proposition a expiré.",
    cancelled_detail: str = "Cette proposition a été annulée.",
    invalid_detail: str = "Cette proposition ne peut plus être confirmée.",
) -> tuple[Any, bool]:
    """Lock a proposal and apply the shared expiry/replay lifecycle.

    Returns ``(proposal, already_confirmed)``. Resource-specific validation and
    creation stay in the caller, but ownership, expiration and idempotent replay
    follow one contract for assistant and capture proposals.
    """
    proposal = session.scalar(
        select(model)
        .where(model.id == proposal_id, model.user_id == user_id)
        .with_for_update()
    )
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)

    if (
        expected_payload_version is not None
        and proposal.payload_version != expected_payload_version
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La proposition a changé. Demandez une nouvelle confirmation.",
        )

    expires_at = proposal.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if proposal.status == pending_status and expires_at is not None and expires_at <= datetime.now(
        expires_at.tzinfo
    ):
        proposal.status = expired_status
        session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=expired_detail)

    if proposal.status == confirmed_status:
        execution = get_proposal_execution(session, proposal_type, proposal.id)
        if execution is None:
            record_proposal_execution(
                session,
                proposal_type=proposal_type,
                proposal_id=proposal.id,
                user_id=user_id,
                resource_id=proposal.confirmed_resource_id,
                completed_at=getattr(proposal, "confirmed_at", None),
            )
            session.commit()
        return proposal, True
    if proposal.status == cancelled_status:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=cancelled_detail)
    if failed_status is not None and proposal.status == failed_status:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=invalid_detail)
    if proposal.status != pending_status:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=invalid_detail)
    return proposal, False


def stable_proposal_key(
    proposal_type: str, source_id: UUID, kind: str, payload: dict[str, object]
) -> str:
    """Build a bounded, deterministic key for one versioned proposal payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
    return f"{proposal_type}:{source_id}:{kind}:{digest}"


def get_proposal_execution(
    session: Session, proposal_type: str, proposal_id: UUID
) -> ProposalExecution | None:
    """Return the durable execution record for one logical proposal."""
    return session.scalar(
        select(ProposalExecution).where(
            ProposalExecution.proposal_type == proposal_type,
            ProposalExecution.proposal_id == proposal_id,
        )
    )


def record_proposal_execution(
    session: Session,
    *,
    proposal_type: str,
    proposal_id: UUID,
    user_id: UUID,
    resource_id: UUID | None,
    completed_at: datetime | None = None,
    execution_status: str = "committed",
    error_code: str | None = None,
) -> ProposalExecution:
    """Insert one execution journal row, or return the existing idempotent row."""
    existing = get_proposal_execution(session, proposal_type, proposal_id)
    if existing is not None:
        return existing
    execution = ProposalExecution(
        proposal_type=proposal_type,
        proposal_id=proposal_id,
        user_id=user_id,
        status=execution_status,
        resource_id=resource_id,
        error_code=error_code,
        completed_at=completed_at,
    )
    session.add(execution)
    return execution


def record_failed_proposal(
    session: Session,
    *,
    proposal: Any,
    proposal_type: str,
    failed_status: Any,
    user_id: UUID,
    error_code: str,
) -> ProposalExecution:
    """Persist a safe, terminal business failure in the proposal journal."""
    proposal.status = failed_status
    return record_proposal_execution(
        session,
        proposal_type=proposal_type,
        proposal_id=proposal.id,
        user_id=user_id,
        resource_id=None,
        execution_status="failed",
        error_code=error_code,
    )
