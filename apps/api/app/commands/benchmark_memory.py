"""Synthetic lexical benchmark. Never connects to the configured application database."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from time import perf_counter

from sqlalchemy import create_engine, event, select
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
            sql_counter = {"enabled": 0, "count": 0}

            @event.listens_for(engine, "before_cursor_execute")
            def count_retrieval_sql(
                *_args: object, counter: dict[str, int] = sql_counter
            ) -> None:
                if counter["enabled"]:
                    counter["count"] += 1

            Base.metadata.create_all(engine)
            with Session(engine) as session:
                user = User(
                    email="synthetic@example.com",
                    display_name="Synthetic",
                    password_hash="synthetic-unusable-hash",
                    enable_assistant=True,
                )
                session.add(user)
                other = User(
                    email="other-synthetic@example.com",
                    display_name="Other synthetic",
                    password_hash="synthetic-unusable-hash",
                    enable_assistant=True,
                )
                session.add(other)
                session.flush()
                session.add(
                    UserConsent(user_id=user.id, policy_key="assistant.memory", policy_version=1)
                )
                session.add(
                    UserConsent(user_id=other.id, policy_key="assistant.memory", policy_version=1)
                )
                capture = Capture(
                    user_id=user.id, content="Synthetic corpus", source=CaptureSource.TEXT
                )
                session.add(capture)
                other_capture = Capture(
                    user_id=other.id, content="Other synthetic corpus", source=CaptureSource.TEXT
                )
                session.add(other_capture)
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
                other_memory = MemoryItem(
                    user_id=other.id,
                    capture_id=other_capture.id,
                    kind=MemoryKind.INFORMATION,
                    summary="Le projet Archipel utilise PostgreSQL",
                    reason="other account",
                )
                session.add(other_memory)
                session.add(
                    MemoryItem(
                        user_id=user.id,
                        capture_id=capture.id,
                        kind=MemoryKind.INFORMATION,
                        summary="Le carton est prêt",
                        reason="near miss for art",
                    )
                )
                for index in range(size - len(targets) - 1):
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
                    ("exact", "Quelle base pour Archipel ?", targets[0]),
                    ("exact", "FastAPI pour mon API ?", targets[1]),
                    ("exact", "Contraintes Zéphyr ?", targets[2]),
                    ("paraphrase", "Quelle pile serveur j'apprécie ?", targets[1]),
                    ("paraphrase", "Zéphyr exige-t-il un accès réseau ?", targets[2]),
                ]
                hit = legacy_hit = false_positive = cross_user_results = 0
                category_hits = {"exact": 0, "paraphrase": 0}
                reciprocal_ranks = []
                latencies_ms = []
                retrieval_sql_queries = []
                started = perf_counter()
                for category, question, target in questions:
                    query_started = perf_counter()
                    sql_counter["count"] = 0
                    sql_counter["enabled"] = 1
                    try:
                        retrieved = MemoryRetriever().retrieve(
                            session, user.id, query=question, limit=5
                        )
                    finally:
                        sql_counter["enabled"] = 0
                    latencies_ms.append((perf_counter() - query_started) * 1000)
                    retrieval_sql_queries.append(sql_counter["count"])
                    ids = [item.id for item in retrieved]
                    found = target.id in ids
                    hit += found
                    category_hits[category] += found
                    reciprocal_ranks.append(1 / (ids.index(target.id) + 1) if found else 0)
                    cross_user_results += other_memory.id in ids
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
                    if category == "exact":
                        legacy_hit += target.id in {item.id for item in old[:5]}
                for absent in ("Astronomie", "Photographie", "Musique classique", "art"):
                    false_positive += bool(
                        MemoryRetriever().retrieve(session, user.id, query=absent)
                    )
                ordered = sorted(latencies_ms)
                p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
                results.append(
                    {
                        "size": size,
                        "queries": len(questions),
                        "recall_at_5": hit / len(questions),
                        "exact_recall_at_5": category_hits["exact"] / 3,
                        "paraphrase_recall_at_5": category_hits["paraphrase"] / 2,
                        "mrr": round(sum(reciprocal_ranks) / len(questions), 3),
                        "legacy_recent_100_recall_at_5": legacy_hit / 3,
                        "unrelated_queries_with_results": false_positive,
                        "cross_user_results": cross_user_results,
                        "retrieval_p50_ms": round(median(latencies_ms), 2),
                        "retrieval_p95_ms": round(p95, 2),
                        "retrieval_sql_queries_p50": median(retrieval_sql_queries),
                        "retrieval_sql_queries_max": max(retrieval_sql_queries),
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
            "Synthetic lexical retrieval on isolated SQLite. Paraphrases and near misses "
            "are illustrative, not a representative hidden evaluation set. No live LLM, "
            "embeddings, PostgreSQL query plan/concurrency, device or user rating."
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
