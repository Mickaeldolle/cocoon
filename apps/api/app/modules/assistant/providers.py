"""Server-side language-model providers used by the assistant."""

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException, status

from app.core.config import Settings

_provider_slots: dict[int, threading.BoundedSemaphore] = {}
_provider_slots_lock = threading.Lock()


def _slot_for_limit(limit: int) -> threading.BoundedSemaphore:
    with _provider_slots_lock:
        slot = _provider_slots.get(limit)
        if slot is None:
            slot = threading.BoundedSemaphore(limit)
            _provider_slots[limit] = slot
        return slot


@contextmanager
def _provider_slot(settings: Settings) -> Iterator[None]:
    slot = _slot_for_limit(settings.assistant_max_concurrent_provider_requests)
    if not slot.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Le service IA est momentanément occupé. Réessayez dans un instant.",
        )
    try:
        yield
    finally:
        slot.release()


@dataclass(frozen=True)
class ProviderResult:
    """Normalized provider result; no credentials or private prompt is retained."""

    content: str
    mode: str
    provider: str
    model: str
    usage: dict[str, object] | None = None


class LLMProvider(Protocol):
    """Provider contract used by the assistant domain."""

    def chat(self, messages: list[dict[str, str]]) -> ProviderResult | None:
        ...

    def stream_chat(
        self, messages: list[dict[str, str]], *, cancel_event: threading.Event | None = None
    ) -> Iterator[str]:
        ...

    def generate_structured(
        self, messages: list[dict[str, str]], schema: dict[str, object]
    ) -> ProviderResult | None:
        ...


class OpenAICompatibleProvider:
    """Call a private OpenAI-compatible chat-completions endpoint from the API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _request(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        response_format: dict[str, object] | None = None,
    ) -> object | None:
        if not self.settings.llm_api_url or not self.settings.llm_model:
            return None
        payload: dict[str, object] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0.2,
        }
        if stream:
            payload["stream"] = True
        if response_format:
            payload["response_format"] = response_format
        request = Request(
            self.settings.llm_api_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **(
                    {"Authorization": f"Bearer {self.settings.llm_api_key}"}
                    if self.settings.llm_api_key
                    else {}
                ),
            },
            method="POST",
        )
        try:
            with _provider_slot(self.settings):
                with urlopen(  # noqa: S310
                    request, timeout=self.settings.llm_timeout_seconds
                ) as response:
                    return response.read()
        except (
            HTTPError,
            URLError,
            TimeoutError,
            KeyError,
            IndexError,
            json.JSONDecodeError,
        ) as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Le service IA est momentanément indisponible. Réessayez dans un instant.",
            ) from error

    def chat(self, messages: list[dict[str, str]]) -> ProviderResult | None:
        raw = self._request(messages)
        if raw is None:
            return None
        try:
            body = json.loads(raw.decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty provider content")
            return ProviderResult(
                content=content,
                mode="llm",
                provider="openai-compatible",
                model=self.settings.llm_model,
                usage=body.get("usage") if isinstance(body.get("usage"), dict) else None,
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="La réponse du service IA est inexploitable. Réessayez.",
            ) from error

    def stream_chat(
        self, messages: list[dict[str, str]], *, cancel_event: threading.Event | None = None
    ) -> Iterator[str]:
        if not self.settings.llm_api_url or not self.settings.llm_model:
            return
        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
        }
        request = Request(
            self.settings.llm_api_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **(
                    {"Authorization": f"Bearer {self.settings.llm_api_key}"}
                    if self.settings.llm_api_key
                    else {}
                ),
            },
            method="POST",
        )
        try:
            with _provider_slot(self.settings):
                with urlopen(  # noqa: S310
                    request, timeout=self.settings.llm_timeout_seconds
                ) as response:
                    for raw_line in response:
                        if cancel_event is not None and cancel_event.is_set():
                            return
                        try:
                            line = raw_line.decode("utf-8").strip()
                            line = line.removeprefix("data:").strip()
                            if not line or line == "[DONE]":
                                continue
                            content = json.loads(line)["choices"][0].get("delta", {}).get("content")
                        except (
                            UnicodeDecodeError,
                            json.JSONDecodeError,
                            KeyError,
                            IndexError,
                            TypeError,
                        ) as error:
                            raise HTTPException(
                                status_code=status.HTTP_502_BAD_GATEWAY,
                                detail="Le flux du service IA est inexploitable. Réessayez.",
                            ) from error
                        if isinstance(content, str) and content:
                            yield content
        except (HTTPError, URLError, TimeoutError) as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Le service IA est momentanément indisponible. Réessayez dans un instant.",
            ) from error

    def generate_structured(
        self, messages: list[dict[str, str]], schema: dict[str, object]
    ) -> ProviderResult | None:
        return self._result_from_request(messages, {"type": "json_schema", "json_schema": schema})

    def _result_from_request(
        self, messages: list[dict[str, str]], response_format: dict[str, object]
    ) -> ProviderResult | None:
        raw = self._request(messages, response_format=response_format)
        if raw is None:
            return None
        try:
            body = json.loads(raw.decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty provider content")
            return ProviderResult(
                content=content,
                mode="llm",
                provider="openai-compatible",
                model=self.settings.llm_model,
                usage=body.get("usage") if isinstance(body.get("usage"), dict) else None,
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="La réponse structurée du service IA est inexploitable. Réessayez.",
            ) from error
