"""Private LLM adapters. Provider payloads and credentials stay server-side."""

import json
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

import httpx

from app.core.config import Settings

logger = logging.getLogger("cocoon.llm")
_provider_slots: dict[int, threading.BoundedSemaphore] = {}
_provider_slots_lock = threading.Lock()


class LLMError(Exception):
    status_code = 503
    public_message = "Le service IA est momentanément indisponible. Réessayez."


class LLMUnavailableError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    status_code = 429
    public_message = "Le service IA est momentanément occupé. Réessayez."


class LLMTimeoutError(LLMError):
    status_code = 504
    public_message = "Le service IA met trop de temps à répondre. Réessayez."


class LLMAuthenticationError(LLMError):
    public_message = "Le service IA est indisponible. Contactez un administrateur."


class LLMInvalidResponseError(LLMError):
    status_code = 502
    public_message = "La réponse du service IA est inexploitable. Réessayez."


def _slot_for_limit(limit: int) -> threading.BoundedSemaphore:
    with _provider_slots_lock:
        return _provider_slots.setdefault(limit, threading.BoundedSemaphore(limit))


@contextmanager
def _provider_slot(settings: Settings) -> Iterator[None]:
    slot = _slot_for_limit(settings.assistant_max_concurrent_provider_requests)
    if not slot.acquire(blocking=False):
        raise LLMRateLimitError
    try:
        yield
    finally:
        slot.release()


@dataclass(frozen=True)
class ProviderResult:
    content: str
    mode: str
    provider: str
    model: str
    usage: dict[str, object] | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    streaming: bool = True
    structured_output: bool = False
    tool_calling: bool = False


class LLMProvider(Protocol):
    capabilities: ProviderCapabilities

    @property
    def base_url(self) -> str | None: ...

    @property
    def model(self) -> str | None: ...

    def chat(self, messages: list[dict[str, str]]) -> ProviderResult | None: ...

    def stream_chat(
        self, messages: list[dict[str, str]], *, cancel_event: threading.Event | None = None
    ) -> Iterator[str]: ...

    def health_check(self) -> bool: ...


def _timeout(settings: Settings) -> httpx.Timeout:
    read_seconds = (
        settings.llm_read_timeout
        if settings.llm_read_timeout is not None
        else settings.llm_timeout_seconds
    )
    return httpx.Timeout(
        connect=settings.llm_connection_timeout,
        read=None if read_seconds == 0 else read_seconds,
        write=settings.llm_connection_timeout,
        pool=settings.llm_pool_timeout,
    )


def _provider_error(error: Exception) -> LLMError:
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        if code == 429:
            return LLMRateLimitError()
        if code in (401, 403):
            return LLMAuthenticationError()
        return LLMUnavailableError() if code >= 500 else LLMInvalidResponseError()
    if isinstance(error, httpx.TimeoutException):
        return LLMTimeoutError()
    if isinstance(error, httpx.RequestError):
        return LLMUnavailableError()
    return LLMInvalidResponseError()


class _HTTPProvider:
    name = ""
    capabilities = ProviderCapabilities()
    endpoint = ""
    health_endpoint = ""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def model(self) -> str | None:
        raise NotImplementedError

    @property
    def base_url(self) -> str | None:
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        return {}

    def _payload(self, messages: list[dict[str, str]], stream: bool) -> dict[str, object]:
        raise NotImplementedError

    def _parse_result(self, body: object) -> ProviderResult:
        raise NotImplementedError

    def _parse_delta(self, body: object) -> str | None:
        raise NotImplementedError

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=_timeout(self.settings), headers=self._headers(), trust_env=False
        )

    def _url(self) -> str:
        return f"{self.base_url.rstrip('/')}{self.endpoint}"

    def _log(self, started: float, status: str, error_type: str = "") -> None:
        logger.info(
            "llm_request provider=%s model=%s latency_ms=%d status=%s error_type=%s",
            self.name, self.model, round((perf_counter() - started) * 1000), status, error_type,
        )

    def chat(self, messages: list[dict[str, str]]) -> ProviderResult | None:
        if not self.base_url or not self.model:
            return None
        started = perf_counter()
        try:
            with _provider_slot(self.settings), self._client() as client:
                response = client.post(self._url(), json=self._payload(messages, False))
                response.raise_for_status()
                result = self._parse_result(response.json())
            self._log(started, "success")
            return result
        except LLMError as error:
            self._log(started, "error", type(error).__name__)
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as error:
            self._log(started, "error", type(error).__name__)
            raise _provider_error(error) from error

    def stream_chat(
        self, messages: list[dict[str, str]], *, cancel_event: threading.Event | None = None
    ) -> Iterator[str]:
        if not self.base_url or not self.model:
            return
        started = perf_counter()
        try:
            with _provider_slot(self.settings), self._client() as client:
                with client.stream(
                    "POST", self._url(), json=self._payload(messages, True)
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if cancel_event is not None and cancel_event.is_set():
                            self._log(started, "cancelled")
                            return
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("data:"):
                            line = line.removeprefix("data:").strip()
                        elif self.name == "openai_compatible":
                            continue
                        if self.name == "openai_compatible" and line == "[DONE]":
                            break
                        chunk = self._parse_delta(json.loads(line))
                        if chunk:
                            yield chunk
            self._log(started, "success")
        except LLMError as error:
            self._log(started, "error", type(error).__name__)
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as error:
            self._log(started, "error", type(error).__name__)
            raise _provider_error(error) from error

    def health_check(self) -> bool:
        if not self.base_url or not self.model:
            return False
        try:
            with httpx.Client(
                timeout=httpx.Timeout(5), headers=self._headers(), trust_env=False
            ) as client:
                response = client.get(f"{self.base_url.rstrip('/')}{self.health_endpoint}")
                response.raise_for_status()
                body = response.json()
                return self._model_available(body)
        except (httpx.HTTPError, ValueError):
            return False

    def _model_available(self, body: object) -> bool:
        return isinstance(body, dict)


class OpenAICompatibleProvider(_HTTPProvider):
    name = "openai_compatible"
    endpoint = "/chat/completions"
    health_endpoint = "/models"

    @property
    def model(self) -> str | None:
        return self.settings.llm_model

    @property
    def base_url(self) -> str | None:
        return self.settings.llm_base_url or self.settings.llm_api_url

    def _headers(self) -> dict[str, str]:
        return (
            {"Authorization": f"Bearer {self.settings.llm_api_key}"}
            if self.settings.llm_api_key else {}
        )

    def _payload(self, messages: list[dict[str, str]], stream: bool) -> dict[str, object]:
        return {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": self.settings.llm_max_output_tokens,
            "stream": stream,
        }

    def _parse_result(self, body: object) -> ProviderResult:
        if not isinstance(body, dict):
            raise ValueError("invalid response")
        choice = body["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty response")
        return ProviderResult(
            content, "llm", self.name, self.model or "",
            body.get("usage") if isinstance(body.get("usage"), dict) else None,
            choice.get("finish_reason"),
        )

    def _parse_delta(self, body: object) -> str | None:
        if not isinstance(body, dict):
            raise ValueError("invalid stream chunk")
        choices = body["choices"]
        if not isinstance(choices, list):
            raise ValueError("invalid choices")
        if not choices:
            return None
        content = choices[0].get("delta", {}).get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("invalid delta")
        return content

    def _model_available(self, body: object) -> bool:
        if not isinstance(body, dict):
            return False
        models = body.get("data")
        return (
            isinstance(models, list)
            and any(isinstance(item, dict) and item.get("id") == self.model for item in models)
        )


class OllamaProvider(_HTTPProvider):
    name = "ollama"
    endpoint = "/api/chat"
    health_endpoint = "/api/tags"

    @property
    def model(self) -> str | None:
        return self.settings.ollama_model

    @property
    def base_url(self) -> str | None:
        return self.settings.ollama_base_url

    def _payload(self, messages: list[dict[str, str]], stream: bool) -> dict[str, object]:
        return {
            "model": self.model, "messages": messages, "stream": stream,
            "options": {
                "temperature": 0.2,
                "num_predict": self.settings.llm_max_output_tokens,
            },
        }

    def _parse_result(self, body: object) -> ProviderResult:
        if not isinstance(body, dict):
            raise ValueError("invalid response")
        content = body["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty response")
        usage = {
            "prompt_tokens": body.get("prompt_eval_count"),
            "completion_tokens": body.get("eval_count"),
        }
        return ProviderResult(
            content, "llm", self.name, self.model or "", usage,
            "stop" if body.get("done") else None,
        )

    def _parse_delta(self, body: object) -> str | None:
        content = body["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("invalid delta")
        return content

    def _model_available(self, body: object) -> bool:
        if not isinstance(body, dict):
            return False
        models = body.get("models")
        return (
            isinstance(models, list)
            and any(isinstance(item, dict) and item.get("name") == self.model for item in models)
        )
