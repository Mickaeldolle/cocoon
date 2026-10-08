"""One-job scheduler entrypoints for serverless or external triggers."""

from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.internal_auth import require_worker_token
from app.modules.memory.worker import process_once as process_one_memory
from app.modules.neural.worker import process_next_pending_run

router = APIRouter(prefix="/api/internal/jobs", tags=["internal"])


@router.api_route("/captures/run", methods=["GET", "POST"], include_in_schema=False)
def run_one_capture(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    require_worker_token(authorization, get_settings().internal_worker_token)
    with SessionLocal() as session:
        processed = process_next_pending_run(session, f"capture-scheduled-{uuid4()}")
    return {"processed": processed is not None}


@router.api_route("/memory/run", methods=["GET", "POST"], include_in_schema=False)
def run_one_memory(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    settings = get_settings()
    require_worker_token(authorization, settings.internal_worker_token)
    if not settings.memory_embeddings_enabled:
        raise HTTPException(status_code=409, detail="Indexation mémoire désactivée.")
    return {"processed": process_one_memory(SessionLocal) is not None}
