"""Run durable universal-capture jobs as a separate service."""

import logging
import time
from collections.abc import Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.modules.neural.worker import process_next_pending_run

logger = logging.getLogger(__name__)


def process_once(
    worker_id: str | None = None, session_factory: Callable[[], Session] = SessionLocal
) -> str | None:
    """Claim at most one run; a lease permits another worker to recover it later."""
    resolved_worker_id = worker_id or f"capture-worker-{uuid4()}"
    with session_factory() as session:
        try:
            run_id = process_next_pending_run(session, resolved_worker_id)
        except Exception:
            logger.exception("capture_worker_failed worker_id=%s", resolved_worker_id)
            return None
    if run_id is not None:
        logger.info("capture_worker_completed worker_id=%s run_id=%s", resolved_worker_id, run_id)
        return str(run_id)
    return None


def main() -> None:
    settings = get_settings()
    worker_id = f"capture-worker-{uuid4()}"
    while True:
        process_once(worker_id)
        time.sleep(settings.worker_interval_seconds)


if __name__ == "__main__":
    main()
