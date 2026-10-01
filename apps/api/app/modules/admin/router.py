from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.audit.models import AuditEvent
from app.modules.auth.dependencies import require_superadmin
from app.modules.auth.models import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    actor_user_id: UUID | None
    session_id: UUID | None
    device_id: UUID | None
    attempted_identity_ref: str | None
    client_ip: str | None
    client_ip_source: str | None
    user_agent_family: str | None
    client_platform: str | None
    request_id: UUID
    action: str
    outcome: str
    method: str
    route: str | None
    status_code: int
    duration_ms: int | None
    response_bytes: int | None
    request_details: dict | None
    query_details: dict | None
    response_details: dict | None


@router.get("/status")
def status(current_user: User = Depends(require_superadmin)) -> dict[str, str]:
    """Minimal protected probe for the future administration interface."""
    return {"status": "ok", "email": current_user.email}


@router.get("/audit-events", response_model=list[AuditEventResponse])
def audit_events(
    actor_user_id: UUID | None = None,
    before: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    _current_user: User = Depends(require_superadmin),
    session: Session = Depends(get_session),
) -> list[AuditEvent]:
    """Read a bounded page of metadata; protected content is never stored here."""
    query = select(AuditEvent)
    if actor_user_id is not None:
        query = query.where(AuditEvent.actor_user_id == actor_user_id)
    if before is not None:
        previous = session.get(AuditEvent, before)
        if previous is None:
            raise HTTPException(status_code=404, detail="Événement introuvable.")
        query = query.where(
            or_(
                AuditEvent.occurred_at < previous.occurred_at,
                (AuditEvent.occurred_at == previous.occurred_at) & (AuditEvent.id < previous.id),
            )
        )
    return list(
        session.scalars(
            query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit)
        )
    )
