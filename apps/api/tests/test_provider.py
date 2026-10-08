import json
from threading import Event

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.modules.assistant.llm_service import LLMService, ProviderFactory
from app.modules.assistant.providers import (
    LLMError,
    OllamaProvider,
    OpenAICompatibleProvider,
    _slot_for_limit,
    _timeout,
)

SECRET = "test-secret-that-is-long-enough-for-validation"


def settings(**overrides: object) -> Settings:
    values = {
        "jwt_secret": SECRET,
        "llm_provider": "openai_compatible",
        "llm_base_url": "http://127.0.0.1:1234/v1",
        "llm_model": "test-model",
        "llm_api_key": "test-key",
        **overrides,
    }
    return Settings(_env_file=None, **values)


def mock_client(monkeypatch: pytest.MonkeyPatch, provider: object, handler) -> None:
    monkeypatch.setattr(provider, "_client", lambda: httpx.Client(
        transport=httpx.MockTransport(handler), timeout=_timeout(provider.settings),
        headers=provider._headers(),
    ))


def test_factory_chooses_ollama_and_openai_compatible() -> None:
    assert isinstance(ProviderFactory.create(settings()), OpenAICompatibleProvider)
    ollama = settings(llm_provider="ollama", ollama_model="qwen3:8b")
    assert isinstance(ProviderFactory.create(ollama), OllamaProvider)
    assert LLMService(ollama).configured


def test_openai_chat_uses_configured_model_and_secret_only_on_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleProvider(settings(llm_max_output_tokens=768))

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert body["max_tokens"] == 768
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Salut"}, "finish_reason": "stop"}]},
        )

    mock_client(monkeypatch, provider, handle)
    result = provider.chat([{"role": "user", "content": "Bonjour"}])
    assert result and result.content == "Salut" and result.finish_reason == "stop"


def test_openai_stream_delivers_deltas_and_closes_on_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleProvider(settings())
    cancelled = Event()

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["max_tokens"] == 2048
        return httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"Bonjour"}}]}\n\n'
                 'data: {"choices":[{"delta":{"content":" Cocoon"}}]}\n\n'
                 "data: [DONE]\n\n",
        )

    mock_client(monkeypatch, provider, handle)
    stream = provider.stream_chat([], cancel_event=cancelled)
    assert next(stream) == "Bonjour"
    cancelled.set()
    assert list(stream) == []


def test_openai_stream_accepts_final_usage_chunk_without_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleProvider(settings())

    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"Bonjour"}}]}\n\n'
                 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                 'data: {"choices":[],"usage":{"completion_tokens":1}}\n\n'
                 'data:[DONE]  \n\n',
        )

    mock_client(monkeypatch, provider, handle)
    assert "".join(provider.stream_chat([])) == "Bonjour"


def test_ollama_chat_and_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider(settings(llm_provider="ollama", ollama_model="qwen3:8b"))

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["model"] == "qwen3:8b"
        assert body["options"]["num_predict"] == 2048
        if body["stream"]:
            return httpx.Response(
                200, text='{"message":{"content":"Salut"},"done":false}\n'
                          '{"message":{"content":" !"},"done":true}\n'
            )
        return httpx.Response(
            200, json={"message": {"content": "Salut !"}, "done": True,
                       "prompt_eval_count": 4, "eval_count": 2}
        )

    mock_client(monkeypatch, provider, handle)
    assert provider.chat([]).usage["completion_tokens"] == 2
    assert list(provider.stream_chat([])) == ["Salut", " !"]


@pytest.mark.parametrize("code,expected", [(429, 429), (500, 503), (502, 503), (401, 503)])
def test_http_errors_are_sanitized(
    monkeypatch: pytest.MonkeyPatch, code: int, expected: int
) -> None:
    provider = OpenAICompatibleProvider(settings())
    mock_client(monkeypatch, provider, lambda _request: httpx.Response(code, text="private detail"))
    with pytest.raises(LLMError) as error:
        provider.chat([])
    assert error.value.status_code == expected
    assert "private detail" not in error.value.public_message


def test_invalid_stream_and_response_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(settings())
    mock_client(monkeypatch, provider, lambda _request: httpx.Response(200, text="data: invalid\n"))
    with pytest.raises(LLMError) as error:
        list(provider.stream_chat([]))
    assert error.value.status_code == 502
    with pytest.raises(LLMError) as error:
        provider.chat([])
    assert error.value.status_code == 502


def test_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(settings(llm_read_timeout=0))
    assert _timeout(provider.settings).read is None

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private host")

    mock_client(monkeypatch, provider, timeout)
    with pytest.raises(LLMError) as error:
        provider.chat([])
    assert error.value.status_code == 504


def test_health_check_does_not_change_api_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(settings())
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(503)), **kwargs
        ),
    )
    assert provider.health_check() is False
    service = LLMService(settings())
    service.provider = provider
    assert service.status()["available"] is False


def test_health_check_verifies_the_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    real_client = httpx.Client
    available = ["test-model"]

    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": item} for item in available]})

    monkeypatch.setattr(
        httpx, "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    provider = OpenAICompatibleProvider(settings())
    assert provider.health_check() is True
    available.clear()
    assert provider.health_check() is False


def test_service_translates_provider_errors_for_api(monkeypatch: pytest.MonkeyPatch) -> None:
    service = LLMService(settings())

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("internal address")

    mock_client(monkeypatch, service.provider, timeout)
    with pytest.raises(HTTPException) as error:
        service.chat([])
    assert error.value.status_code == 504
    assert "internal address" not in error.value.detail
    with pytest.raises(HTTPException) as error:
        list(service.stream_chat([]))
    assert error.value.status_code == 504


def test_concurrency_budget_is_enforced() -> None:
    provider = OpenAICompatibleProvider(settings(assistant_max_concurrent_provider_requests=1))
    slot = _slot_for_limit(1)
    assert slot.acquire(blocking=False)
    try:
        with pytest.raises(LLMError) as error:
            list(provider.stream_chat([]))
    finally:
        slot.release()
    assert error.value.status_code == 429


def test_configuration_validation() -> None:
    with pytest.raises(ValueError, match="OLLAMA_MODEL"):
        settings(llm_provider="ollama")
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        Settings(_env_file=None, jwt_secret=SECRET, llm_base_url="http://localhost:1234/v1")
    with pytest.raises(ValueError, match="llm_max_output_tokens"):
        settings(llm_max_output_tokens=0)
