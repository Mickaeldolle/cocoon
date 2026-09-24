"""Small server-side adapter for the Hermes JSON-RPC WebSocket gateway.

Expo never sees the gateway URL or its token.  Cocoon owns authentication and maps each
account to a dedicated Hermes profile and durable session, which prevents personal memory
from becoming shared family context.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

import websockets

from app.core.config import get_settings
from app.modules.assistant.kernel import MAX_CHOICES, AgentReply

_ASK_PATTERN = re.compile(r"::ask\{(?P<body>(?:[^\"}\\]|\"(?:\\.|[^\"\\])*\")*)\}")
_ATTRIBUTE_PATTERN = re.compile(r"(?P<key>[a-zA-Z_][\w-]*)=\"(?P<value>(?:\\.|[^\"\\])*)\"")


class HermesGatewayError(RuntimeError):
    """A safe-to-report failure while talking to Hermes."""


class HermesRpcError(HermesGatewayError):
    def __init__(self, code: int | None, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class HermesTurn:
    stored_session_id: str
    reply: AgentReply


def profile_name(user_id: UUID) -> str:
    """Return a stable opaque profile name without leaking email or display name."""
    return f"cocoon-{user_id.hex}"


def _decode_attribute(value: str) -> str:
    try:
        decoded = json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value
    return decoded if isinstance(decoded, str) else value


def parse_hermes_reply(text: str) -> AgentReply:
    """Turn Hermes' portable ``::ask`` directive into native mobile reply choices."""
    choices: list[str] = []
    questions: list[str] = []

    def replace(match: re.Match[str]) -> str:
        attrs = {
            item.group("key"): _decode_attribute(item.group("value"))
            for item in _ATTRIBUTE_PATTERN.finditer(match.group("body"))
        }
        question = " ".join(attrs.get("question", "").split())
        if question:
            questions.append(question[:240])
        for option in attrs.get("options", "").split("|"):
            normalized = " ".join(option.split())[:160]
            if normalized and normalized not in choices and len(choices) < MAX_CHOICES:
                choices.append(normalized)
        return ""

    visible = _ASK_PATTERN.sub(replace, text)
    visible = re.sub(r"\n{3,}", "\n\n", visible).strip()
    for question in questions:
        if question.casefold() not in visible.casefold():
            visible = f"{visible}\n\n{question}".strip()
    if not visible:
        raise HermesGatewayError("Hermes n’a fourni aucune réponse exploitable.")
    return AgentReply(text=visible[:12000], choices=choices, memories=[])


def _authenticated_url(base_url: str, token: str | None) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
        raise HermesGatewayError("L’adresse de la passerelle Hermes est invalide.")
    if parsed.scheme == "ws" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HermesGatewayError("Une passerelle Hermes distante doit utiliser TLS.")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if token and "token" not in query and "ticket" not in query:
        query["token"] = token
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


class HermesGatewayClient:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.hermes_gateway_ws_url:
            raise HermesGatewayError("La passerelle Hermes n’est pas configurée.")
        self.url = _authenticated_url(settings.hermes_gateway_ws_url, settings.hermes_gateway_token)
        self.timeout = settings.hermes_turn_timeout_seconds
        self._next_request_id = 0

    def _request_frame(self, method: str, params: dict[str, object]) -> tuple[int, str]:
        self._next_request_id += 1
        return self._next_request_id, json.dumps(
            {"jsonrpc": "2.0", "id": self._next_request_id, "method": method, "params": params},
            ensure_ascii=False,
        )

    @staticmethod
    async def _receive(socket: Any) -> dict[str, Any]:
        raw = await socket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            frame = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise HermesGatewayError("Hermes a envoyé une réponse illisible.") from error
        if not isinstance(frame, dict):
            raise HermesGatewayError("Hermes a envoyé une réponse invalide.")
        return frame

    async def _rpc(self, socket: Any, method: str, params: dict[str, object]) -> dict[str, Any]:
        request_id, frame = self._request_frame(method, params)
        await socket.send(frame)
        while True:
            response = await self._receive(socket)
            if response.get("id") != request_id:
                continue
            error = response.get("error")
            if isinstance(error, dict):
                raise HermesRpcError(
                    error.get("code") if isinstance(error.get("code"), int) else None,
                    str(error.get("message") or "Erreur Hermes"),
                )
            result = response.get("result")
            if not isinstance(result, dict):
                raise HermesGatewayError(f"Hermes n’a pas confirmé {method}.")
            return result

    async def _ensure_profile(self, socket: Any, name: str) -> None:
        try:
            await self._rpc(
                socket,
                "profiles.create",
                {
                    "name": name,
                    "description": "Assistant personnel mobile Cocoon",
                    "no_skills": True,
                    "no_alias": True,
                    "mirror_credentials": True,
                    "soul": (
                        "Tu es l’assistant personnel Cocoon. Réponds en français, de façon "
                        "chaleureuse et concise. Mémorise uniquement les informations durables "
                        "explicitement confiées par cette personne. N’utilise aucun outil autre "
                        "que la mémoire. Quand une question gagne à proposer des suites, termine "
                        'avec ::ask{question="…" options="Choix 1|Choix 2|Choix 3"}.'
                    ),
                },
            )
        except HermesRpcError as error:
            # Hermes uses 4062 both for an existing profile and invalid creation input.
            # A session create below remains the authoritative existence check.
            if error.code != 4062:
                raise
        await self._rpc(
            socket,
            "profiles.configure",
            {
                "name": name,
                "enabled_toolsets": ["memory"],
                "enabled_mcp_servers": [],
            },
        )

    async def _start_session(
        self, socket: Any, name: str, stored_session_id: str | None
    ) -> tuple[str, str]:
        if stored_session_id:
            result = await self._rpc(
                socket,
                "session.resume",
                {
                    "session_id": stored_session_id,
                    "profile": name,
                    "source": "cocoon-mobile",
                    "omit_messages": True,
                    "close_on_disconnect": False,
                },
            )
            runtime_id = result.get("session_id")
            if not isinstance(runtime_id, str) or not runtime_id:
                raise HermesGatewayError("Hermes n’a pas repris la conversation.")
            return runtime_id, stored_session_id

        await self._ensure_profile(socket, name)
        result = await self._rpc(
            socket,
            "session.create",
            {
                "profile": name,
                "source": "cocoon-mobile",
                "title": "Assistant Cocoon",
                "close_on_disconnect": False,
                "hidden": True,
            },
        )
        runtime_id = result.get("session_id")
        durable_id = result.get("stored_session_id")
        if not isinstance(runtime_id, str) or not isinstance(durable_id, str):
            raise HermesGatewayError("Hermes n’a pas créé la conversation.")
        return runtime_id, durable_id

    async def _submit(self, socket: Any, runtime_id: str, text: str) -> AgentReply:
        request_id, request = self._request_frame(
            "prompt.submit",
            {"session_id": runtime_id, "text": text, "surface": "cocoon-mobile"},
        )
        await socket.send(request)
        chunks: list[str] = []
        submit_confirmed = False
        completed: dict[str, Any] | None = None
        while completed is None or not submit_confirmed:
            frame = await self._receive(socket)
            if frame.get("id") == request_id:
                error = frame.get("error")
                if isinstance(error, dict):
                    raise HermesRpcError(
                        error.get("code") if isinstance(error.get("code"), int) else None,
                        str(error.get("message") or "Le message a été refusé par Hermes."),
                    )
                submit_confirmed = True
                continue
            if frame.get("method") != "event":
                continue
            params = frame.get("params")
            if not isinstance(params, dict) or params.get("session_id") != runtime_id:
                continue
            payload = params.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            if params.get("type") == "message.delta" and isinstance(payload.get("text"), str):
                chunks.append(payload["text"])
            elif params.get("type") == "message.complete":
                completed = payload

        status_value = completed.get("status") if completed else None
        if status_value != "complete":
            raise HermesGatewayError("Hermes n’a pas pu terminer sa réponse.")
        final_text = completed.get("text") if completed else None
        if not isinstance(final_text, str) or not final_text.strip():
            final_text = "".join(chunks)
        return parse_hermes_reply(final_text)

    async def turn(self, *, user_id: UUID, stored_session_id: str | None, text: str) -> HermesTurn:
        try:
            async with asyncio.timeout(self.timeout):
                async with websockets.connect(
                    self.url,
                    open_timeout=15,
                    close_timeout=5,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=4 * 1024 * 1024,
                ) as socket:
                    runtime_id, durable_id = await self._start_session(
                        socket, profile_name(user_id), stored_session_id
                    )
                    reply = await self._submit(socket, runtime_id, text)
                    return HermesTurn(stored_session_id=durable_id, reply=reply)
        except TimeoutError as error:
            raise HermesGatewayError("Hermes met trop de temps à répondre.") from error
        except (OSError, websockets.WebSocketException) as error:
            raise HermesGatewayError("Hermes est indisponible.") from error
