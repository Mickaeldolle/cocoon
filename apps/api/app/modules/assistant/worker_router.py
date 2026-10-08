"""Bounded scheduler entrypoint for serverless notification delivery."""

from fastapi import APIRouter, Header

from app.commands.run_reminder_worker import process_once
from app.core.config import get_settings
from app.core.internal_auth import require_worker_token

router = APIRouter(prefix="/api/internal/notifications", tags=["internal"])


@router.api_route("/run", methods=["GET", "POST"], include_in_schema=False)
def run_notifications(authorization: str | None = Header(default=None)) -> dict[str, int]:
    require_worker_token(authorization, get_settings().notification_worker_token)
    queued, sent = process_once(max_items=3)
    return {"queued": queued, "sent": sent}
