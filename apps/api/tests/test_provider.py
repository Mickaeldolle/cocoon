from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.assistant.providers import OpenAICompatibleProvider, _slot_for_limit


class StreamingResponse:
    def __init__(self, lines: list[bytes]) -> None:
        self.lines = lines
        self.closed = False

    def __enter__(self) -> "StreamingResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        self.closed = True
        return None

    def __iter__(self):
        return iter(self.lines)


def provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        SimpleNamespace(
            llm_api_url="http://127.0.0.1:11434/v1",
            llm_model="local-model",
            llm_api_key="test-key",
            llm_timeout_seconds=3.0,
            assistant_max_concurrent_provider_requests=2,
        )
    )


def test_stream_chat_yields_sse_deltas_without_buffering(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: object, *, timeout: float) -> StreamingResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return StreamingResponse(
            [
                b'data: {"choices":[{"delta":{"content":"Bonjour"}}]}\n',
                b'data: {"choices":[{"delta":{"content":" Cocoon"}}]}\n',
                b"data: [DONE]\n",
            ]
        )

    monkeypatch.setattr("app.modules.assistant.providers.urlopen", fake_urlopen)

    chunks = provider().stream_chat([{"role": "user", "content": "Salut"}])

    assert next(chunks) == "Bonjour"
    assert next(chunks) == " Cocoon"
    with pytest.raises(StopIteration):
        next(chunks)
    request = captured["request"]
    assert request.data is not None
    assert b'"stream": true' in request.data
    assert request.headers["Authorization"] == "Bearer test-key"
    assert captured["timeout"] == 3.0


def test_stream_chat_rejects_malformed_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.assistant.providers.urlopen",
        lambda *_args, **_kwargs: StreamingResponse([b"data: not-json\n"]),
    )

    with pytest.raises(HTTPException) as error:
        list(provider().stream_chat([]))

    assert error.value.status_code == 502


def test_stream_chat_stops_and_closes_provider_response_when_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from threading import Event

    response = StreamingResponse(
        [
            b'data: {"choices":[{"delta":{"content":"Premier"}}]}\n',
            b'data: {"choices":[{"delta":{"content":"Second"}}]}\n',
        ]
    )
    monkeypatch.setattr(
        "app.modules.assistant.providers.urlopen", lambda *_args, **_kwargs: response
    )
    cancelled = Event()
    chunks = provider().stream_chat([], cancel_event=cancelled)

    assert next(chunks) == "Premier"
    cancelled.set()
    with pytest.raises(StopIteration):
        next(chunks)
    assert response.closed is True


def test_provider_rejects_a_request_when_the_concurrency_budget_is_full() -> None:
    current = provider()
    current.settings.assistant_max_concurrent_provider_requests = 1
    slot = _slot_for_limit(1)
    assert slot.acquire(blocking=False)
    try:
        with pytest.raises(HTTPException) as error:
            list(current.stream_chat([]))
    finally:
        slot.release()

    assert error.value.status_code == 429


def test_three_simultaneous_provider_requests_respect_the_concurrency_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = provider()
    entered_two_requests = Event()
    release_provider = Event()
    count_lock = Lock()
    entered = 0

    def fake_urlopen(_request: object, *, timeout: float) -> StreamingResponse:
        nonlocal entered
        assert timeout == 3.0
        with count_lock:
            entered += 1
            if entered == 2:
                entered_two_requests.set()
        assert release_provider.wait(timeout=2)
        return StreamingResponse([b'data: {"choices":[{"delta":{"content":"ok"}}]}\n'])

    monkeypatch.setattr("app.modules.assistant.providers.urlopen", fake_urlopen)

    def run_request() -> list[str]:
        return list(current.stream_chat([{"role": "user", "content": "Salut"}]))

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run_request) for _ in range(3)]
        assert entered_two_requests.wait(timeout=1)
        release_provider.set()
        errors = 0
        results: list[list[str]] = []
        for future in futures:
            try:
                results.append(future.result(timeout=2))
            except HTTPException as error:
                errors += 1
                assert error.status_code == 429

    assert results == [["ok"], ["ok"]]
    assert errors == 1
