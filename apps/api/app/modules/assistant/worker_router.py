"""Bounded scheduler entrypoint for serverless notification delivery."""

from hmac import compare_digest

from fastapi import APIRouter, Header, HTTPException

from app.commands.run_reminder_worker import process_once
from app.core.config import get_settings

router = APIRouter(prefix="/api/internal/notifications", tags=["internal"])


@router.post("/run")
def run_notifications(authorization: str | None = Header(default=None)) -> dict[str, int]:
    token = get_settings().notification_worker_token
    if not token:
        raise HTTPException(status_code=404, detail="Introuvable.")
    if not compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="Non autorisé.")
    queued, sent = process_once(max_items=3)
    return {"queued": queued, "sent": sent}
