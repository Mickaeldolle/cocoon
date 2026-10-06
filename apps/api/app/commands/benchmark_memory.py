"""Synthetic lexical benchmark. Never connects to the configured application database."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import Base
from app.main import app  # noqa: F401 -- register the existing model metadata
from app.modules.auth.models import User, UserConsent
from app.modules.memory.retriever import MemoryRetriever
from app.modules.neural.models import Capture, CaptureSource, MemoryItem, MemoryKind


def run_benchmark() -> dict[str, object]:
    settings = get_settings()
    original = settings.memory_embeddings_enabled
    settings.memory_embeddings_enabled = False
    results = []
    try:
        for size in (10, 100, 500, 1000):
            engine = create_engine("sqlite://")
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                user = User(
                    email="synthetic@example.com",
                    display_name="Synthetic",
                    password_hash="synthetic-unusable-hash",
                    enable_assistant=True,
                )
                session.add(user)
                session.flush()
                session.add(
                    UserConsent(user_id=user.id, policy_key="assistant.memory", policy_version=1)
                )
                capture = Capture(
                    user_id=user.id, content="Synthetic corpus", source=CaptureSource.TEXT
                )
                session.add(capture)
                session.flush()
                targets = []
                for summary in (
                    "Le projet Archipel utilise PostgreSQL",
                    "Je préfère FastAPI",
                    "Le projet Zéphyr doit fonctionner hors ligne",
                ):
                    item = MemoryItem(
                        user_id=user.id,
                        capture_id=capture.id,
                        kind=MemoryKind.INFORMATION,
                        summary=summary,
                        reason="synthetic",
                        observed_at=datetime.now(UTC) - timedelta(days=400),
                    )
                    session.add(item)
                    targets.append(item)
                for index in range(size - len(targets)):
                    session.add(
                        MemoryItem(
                            user_id=user.id,
                            capture_id=capture.id,
                            kind=MemoryKind.INFORMATION,
                            summary=f"Recette numéro {index}",
                            reason="synthetic",
                        )
                    )
                session.commit()
                questions = [
                    "Quelle base pour Archipel ?",
                    "FastAPI pour mon API ?",
                    "Contraintes Zéphyr ?",
                ]
                hit = legacy_hit = false_positive = 0
                started = perf_counter()
                for question, target in zip(questions, targets, strict=True):
                    retrieved = MemoryRetriever().retrieve(
                        session, user.id, query=question, limit=5
                    )
                    hit += target.id in {item.id for item in retrieved}
                    old = list(
                        session.scalars(
                            select(MemoryItem)
                            .where(MemoryItem.user_id == user.id)
                            .order_by(MemoryItem.observed_at.desc())
                            .limit(100)
                        )
                    )
                    words = {word.casefold() for word in question.split() if len(word) > 2}
                    old.sort(
                        key=lambda item: len(words & set(item.summary.casefold().split())),
                        reverse=True,
                    )
                    legacy_hit += target.id in {item.id for item in old[:5]}
                for absent in ("Astronomie", "Photographie", "Musique classique"):
                    false_positive += bool(
                        MemoryRetriever().retrieve(session, user.id, query=absent)
                    )
                results.append(
                    {
                        "size": size,
                        "queries": 3,
                        "recall_at_5": hit / 3,
                        "legacy_recent_100_recall_at_5": legacy_hit / 3,
                        "unrelated_queries_with_results": false_positive,
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                    }
                )
            engine.dispose()
    finally:
        settings.memory_embeddings_enabled = original
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "backend": "isolated_sqlite",
        "limitations": (
            "Synthetic lexical retrieval only; no live LLM, embeddings, user rating "
            "or PostgreSQL concurrency qualification."
        ),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(run_benchmark(), indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
