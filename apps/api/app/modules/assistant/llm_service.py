"""Provider selection and normalized assistant-facing LLM operations."""

import threading
from collections.abc import Iterator

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.modules.assistant.providers import (
    LLMError,
    LLMProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    ProviderResult,
)


class ProviderFactory:
    @staticmethod
    def create(settings: Settings) -> LLMProvider:
        if settings.llm_provider == "ollama":
            return OllamaProvider(settings)
        return OpenAICompatibleProvider(settings)


class LLMService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.provider = ProviderFactory.create(self.settings)

    @property
    def configured(self) -> bool:
        return bool(self.provider.base_url and self.provider.model)

    def chat(self, messages: list[dict[str, str]]) -> ProviderResult | None:
        try:
            return self.provider.chat(messages)
        except LLMError as error:
            raise HTTPException(error.status_code, error.public_message) from error

    def stream_chat(
        self, messages: list[dict[str, str]], *, cancel_event: threading.Event | None = None
    ) -> Iterator[str]:
        if not self.settings.llm_streaming:
            result = self.chat(messages)
            if result and (cancel_event is None or not cancel_event.is_set()):
                return iter((result.content,))
            return iter(())
        return self._stream(messages, cancel_event=cancel_event)

    def _stream(
        self, messages: list[dict[str, str]], *, cancel_event: threading.Event | None
    ) -> Iterator[str]:
        try:
            yield from self.provider.stream_chat(messages, cancel_event=cancel_event)
        except LLMError as error:
            raise HTTPException(error.status_code, error.public_message) from error

    def status(self) -> dict[str, str | bool]:
        return {
            "available": (
                self.provider.health_check() if self.settings.llm_healthcheck_enabled else False
            ),
            "provider": self.settings.llm_provider,
            "model": self.provider.model or "",
        }
