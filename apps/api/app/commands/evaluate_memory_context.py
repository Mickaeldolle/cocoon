"""Evaluate synthetic assistant context against the configured live provider."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from app.core.config import get_settings
from app.modules.assistant.kernel import _conversation_messages
from app.modules.assistant.llm_service import LLMService

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CASES = REPOSITORY_ROOT / "docs" / "validation" / "memory-live-cases.json"
WINDOWS = (2048, 4096, 8192)
OUTPUT_RESERVE = 256


def load_cases(path: Path) -> list[dict[str, object]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Le corpus doit contenir une liste de scénarios.")
    required = {"id", "message", "recent_conversation", "recalled_memories", "personal_context"}
    for case in cases:
        if not isinstance(case, dict) or not required.issubset(case):
            raise ValueError("Chaque scénario doit déclarer son message et ses contextes.")
        if not isinstance(case["id"], str) or not isinstance(case["message"], str):
            raise ValueError("Identifiant et message doivent être du texte.")
        for field in ("recent_conversation", "recalled_memories", "personal_context"):
            if not isinstance(case[field], list):
                raise ValueError(f"{field} doit être une liste.")
        for field, maximum in (("history_filler_count", 1000), ("memory_filler_count", 11)):
            count = case.get(field, 0)
            if not isinstance(count, int) or not 0 <= count <= maximum:
                raise ValueError(f"{field} doit être compris entre 0 et {maximum}.")
        for field in ("required_memory_ids", "expected_terms", "forbidden_terms"):
            values = case.get(field, [])
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                raise ValueError(f"{field} doit contenir uniquement du texte.")
    return cases


def evaluate(cases: list[dict[str, object]], *, dry_run: bool) -> dict[str, object]:
    settings = get_settings()
    model_settings = settings.model_copy(update={"llm_max_output_tokens": OUTPUT_RESERVE})
    service = LLMService(model_settings)
    if not dry_run and not service.configured:
        raise ValueError("Configurer un provider LLM avant une évaluation réelle.")
    results = []
    for window in WINDOWS:
        # UTF-8 bytes are only a conservative estimate; provider usage is the token proof.
        max_bytes = min(settings.assistant_prompt_max_bytes, (window - OUTPUT_RESERVE) * 2)
        for case in cases:
            history = list(case["recent_conversation"])
            filler_count = case.get("history_filler_count", 0)
            for index in range(filler_count):
                history.append({"role": "user", "content": f"Message fictif ancien {index}."})
            memories = [
                {
                    "id": f"memoire-fictive-bruit-{index}",
                    "summary": (
                        f"Note fictive {index} sans rapport avec la question. "
                        + "Ce contenu remplit volontairement le contexte de test. " * 3
                    ),
                    "origin": "explicit",
                    "scope_type": "personal",
                }
                for index in range(case.get("memory_filler_count", 0))
            ]
            memories.extend(case["recalled_memories"])
            messages = _conversation_messages(
                case["message"],
                history,
                memories,
                case["personal_context"],
                max_bytes=max_bytes,
            )
            selected = json.loads(messages[1]["content"])
            selected_ids = [item.get("id") for item in selected["memory_sources"]]
            entry: dict[str, object] = {
                "case": case["id"],
                "context_window_tokens": window,
                "output_reserve_tokens": OUTPUT_RESERVE,
                "prompt_byte_limit": max_bytes,
                "prompt_bytes": sum(
                    len(message["content"].encode("utf-8")) for message in messages
                ),
                "selected_memories": selected_ids,
                "required_memories_selected": {
                    memory_id: memory_id in selected_ids
                    for memory_id in case.get("required_memory_ids", [])
                },
                "selected_history_messages": len(selected["recent_conversation"]),
            }
            if not dry_run:
                started = perf_counter()
                result = service.chat(messages)
                entry["latency_ms"] = round((perf_counter() - started) * 1000)
                if result is None:
                    raise ValueError("Le provider configuré ne renvoie aucune réponse.")
                usage = result.usage or {}
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
                entry.update(
                    {
                        "provider": result.provider,
                        "model": result.model,
                        "usage": usage,
                        "finish_reason": result.finish_reason,
                        "reply": result.content,
                        "expected_terms_found": {
                            term: term.casefold() in result.content.casefold()
                            for term in case.get("expected_terms", [])
                        },
                        "forbidden_terms_found": {
                            term: term.casefold() in result.content.casefold()
                            for term in case.get("forbidden_terms", [])
                        },
                        "within_declared_window": (
                            prompt_tokens + completion_tokens <= window
                            if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int)
                            else None
                        ),
                    }
                )
            results.append(entry)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
        "method": (
            "Two UTF-8 bytes per available token are a sizing heuristic, not a token count. "
            "Only provider usage can verify actual tokens; answers still need human review."
        ),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = json.dumps(
        evaluate(load_cases(args.cases), dry_run=args.dry_run), indent=2, ensure_ascii=False
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
