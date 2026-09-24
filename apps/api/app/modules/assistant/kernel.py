"""Small, deterministic shell around the conversational model."""

import json
import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.modules.assistant import service as assistant_service

MAX_CHOICES = 3
MAX_MEMORIES = 2
_SENSITIVE_MEMORY_PATTERN = re.compile(
    r"\b(maladie|diagnostic|médicament|medicament|douleur|ordonnance|iban|carte bancaire|"
    r"mot de passe|password|code secret)\b",
    flags=re.IGNORECASE,
)
_EXPLICIT_MEMORY_PATTERN = re.compile(
    r"\b(je préfère|je prefere|j'aime|j’aime|je n'aime pas|je n’aime pas|"
    r"je veux|je souhaite|je dois|mon objectif|mon projet|j'habite|j’habite|"
    r"je travaille|je vis|à partir de|a partir de|désormais|desormais|"
    r"je fais|je pratique|je prends|je garde)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class AgentReply:
    text: str
    choices: list[str]
    memories: list[str]


def _conversation_messages(
    message: str,
    recent_conversation: list[dict[str, str]],
    recalled_memories: list[str] | None = None,
    personal_context: list[dict[str, object]] | None = None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Tu es Cocoon, un assistant personnel français simple et attentif. "
                "Réponds naturellement et de façon concise. Demande une précision si nécessaire. "
                "Tu ne donnes pas de conseil médical et tu n’inventes jamais de faits. "
                "Retourne exclusivement un objet JSON sans Markdown : "
                '{"reply":string,"choices":string[],"memories":string[]}. '
                "choices contient zéro à trois réponses brèves pour poursuivre la conversation. "
                "memories contient seulement les faits durables ou préférences explicitement "
                "donnés dans le dernier message, zéro à deux éléments. N’y place jamais "
                "d’information médicale, financière, d’authentification ou intime."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "message": message,
                    "recent_conversation": recent_conversation[-10:],
                    "recalled_memories": (recalled_memories or [])[:12],
                    "personal_context": (personal_context or [])[:4],
                },
                ensure_ascii=False,
            ),
        },
    ]


def answer(
    message: str,
    recent_conversation: list[dict[str, str]],
    recalled_memories: list[str],
    personal_context: list[dict[str, object]] | None = None,
) -> AgentReply:
    """Ask the configured model for one direct conversational turn."""
    content = assistant_service.llm_chat(
        _conversation_messages(message, recent_conversation, recalled_memories, personal_context)
    )
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Le modèle est indisponible. Réessayez dans un instant.",
        )
    return parse_model_answer(content, message)


def stream_answer(
    message: str,
    recent_conversation: list[dict[str, str]],
    recalled_memories: list[str],
    personal_context: list[dict[str, object]] | None = None,
    cancel_event: threading.Event | None = None,
) -> Iterator[str]:
    """Yield JSON model deltas; the final payload is validated by the API."""
    yield from assistant_service.llm_stream(
        _conversation_messages(message, recent_conversation, recalled_memories, personal_context),
        cancel_event=cancel_event,
    )


def parse_streamed_answer(content: str, message: str) -> AgentReply:
    """Validate structured output, while accepting plain model text as a safe fallback."""
    return parse_model_answer(content, message)


def parse_model_answer(content: str, message: str) -> AgentReply:
    """Parse structured output or keep a natural-language response usable."""
    payload = assistant_service.json_from_llm(content)
    if not isinstance(payload, dict):
        reply = _reply_text(content, limit=1200)
        if reply is None:
            raise HTTPException(status_code=502, detail="La réponse du modèle est vide.")
        return AgentReply(text=reply, choices=[], memories=[])
    reply = _reply_text(payload.get("reply"), limit=1200)
    if reply is None:
        raise HTTPException(status_code=502, detail="La réponse du modèle est incomplète.")
    return AgentReply(
        text=reply,
        choices=_string_list(payload.get("choices", []), limit=MAX_CHOICES, item_limit=160),
        memories=_safe_memories(payload.get("memories", []), message),
    )


def _short_text(value: object, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized[:limit] if normalized else None


def _reply_text(value: object, *, limit: int) -> str | None:
    """Bound a reply without destroying Markdown whitespace and line breaks."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized[:limit] if normalized else None


def _string_list(value: object, *, limit: int, item_limit: int) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        return []
    result: list[str] = []
    for item in value:
        normalized = _short_text(item, limit=item_limit)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _safe_memories(value: object, source_message: str) -> list[str]:
    if not _EXPLICIT_MEMORY_PATTERN.search(source_message):
        return []
    return [
        memory
        for memory in _string_list(value, limit=MAX_MEMORIES, item_limit=240)
        if not _SENSITIVE_MEMORY_PATTERN.search(memory)
    ]


def streamed_reply_prefix(content: str) -> str:
    """Decode a JSON reply prefix or expose a plain-text stream prefix."""
    match = re.search(r'"reply"\s*:\s*"', content)
    if match is None:
        if content.lstrip().startswith(("{", "[")):
            return ""
        return _reply_text(content, limit=1200) or ""
    raw = content[match.end() :]
    escaped = False
    end = len(raw)
    for index, character in enumerate(raw):
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            end = index
            break
    candidate = raw[:end]
    while candidate:
        try:
            return json.loads('"' + candidate + '"')
        except json.JSONDecodeError:
            candidate = candidate[:-1]
    return ""
