"""Run the optional local memory indexer, or prepare its pgvector storage."""

import argparse
import json
import logging
import time

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.modules.memory.embeddings import install_vector_storage, vector_storage_status
from app.modules.memory.worker import process_once


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup-vector", action="store_true")
    parser.add_argument("--check-vector", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    if args.check_vector and (args.setup_vector or args.once or args.retry_failed):
        parser.error("--check-vector ne peut pas être combiné avec les autres modes")
    logging.basicConfig(level=logging.INFO)
    if args.check_vector:
        with SessionLocal() as session:
            status = vector_storage_status(session)
        print(json.dumps(status, sort_keys=True))
        if not status["ready"]:
            raise SystemExit(1)
        return
    if args.setup_vector:
        with SessionLocal() as session:
            install_vector_storage(session)
            session.commit()
        return
    if args.retry_failed:
        from sqlalchemy import update

        from app.modules.memory.models import MemoryEmbedding

        with SessionLocal() as session:
            session.execute(
                update(MemoryEmbedding)
                .where(MemoryEmbedding.status == "failed")
                .values(status="pending", attempt=0, retry_at=None)
            )
            session.commit()
    settings = get_settings()
    if not settings.memory_embeddings_enabled:
        raise SystemExit("Activer MEMORY_EMBEDDINGS_ENABLED avant de lancer l'indexeur")
    while True:
        try:
            processed = process_once(SessionLocal)
        except SQLAlchemyError:
            logging.getLogger(__name__).warning("memory_worker_database_unavailable")
            if args.once:
                raise SystemExit("La base mémoire est indisponible") from None
            processed = None
        if args.once:
            return
        if processed is None:
            time.sleep(settings.memory_worker_interval_seconds)


if __name__ == "__main__":
    main()
