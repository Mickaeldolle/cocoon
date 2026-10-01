"""Bounded audit metadata: never copy arbitrary HTTP bodies or headers."""

import hashlib
import hmac
import ipaddress
import logging
from uuid import UUID

from fastapi import Request, Response

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.modules.audit.models import AuditEvent

logger = logging.getLogger("cocoon.audit")

AUTH_ACTIONS = {
    "/api/auth/register": "auth.register",
    "/api/auth/login": "auth.login.password",
    "/api/auth/passkeys/login/verify": "auth.login.passkey",
    "/api/auth/refresh": "auth.refresh",
    "/api/auth/logout": "auth.logout",
}
SECRET_STEP_UP = {
    "/api/secret/unlock": "secret.unlock.password",
    "/api/secret/passkeys/unlock/verify": "secret.unlock.passkey",
    "/api/secret/biometric/unlock": "secret.unlock.biometric",
    "/api/secret/development-biometric/unlock": "secret.unlock.development",
    "/api/secret/lock": "secret.lock",
}
READ_ACTIONS = {
    "/api/auth/devices": "auth.devices.read",
    "/api/admin/audit-events": "admin.audit.read",
    "/api/assistant/history": "assistant.history.read",
    "/api/assistant/briefing": "assistant.briefing.read",
    "/api/conversations": "conversations.list",
    "/api/conversations/{conversation_id}/messages": "messages.list",
    "/api/memories": "memories.list",
}
WRITE_ACTIONS = {
    ("POST", "/api/conversations"): "conversation.create",
    ("POST", "/api/conversations/{conversation_id}/messages"): "message.send",
    ("POST", "/api/assistant/chat"): "assistant.chat",
    ("POST", "/api/assistant/chat/stream"): "assistant.chat.stream",
    ("POST", "/api/assistant/turn"): "assistant.turn",
    ("POST", "/api/assistant/proposals/{proposal_id}/confirm"): "proposal.confirm",
    ("POST", "/api/assistant/proposals/{proposal_id}/cancel"): "proposal.cancel",
}
NOISY_ROUTES = {
    "/api/secret/conversations/{conversation_id}/typing",
    "/api/realtime/ticket",
}
SAFE_DETAIL_KEYS = {
    "platform",
    "policy_version",
    "policy_key",
    "source",
    "active",
    "member_count",
    "message_length",
    "resource_type",
    "token_issued",
    "ui_action",
}


def normalized_platform(value: str) -> str:
    platform = value.strip().lower()
    return platform if platform in {"ios", "android", "web"} else "other"


def note_request_details(request: Request, **details: str | int | bool) -> None:
    """Called only with selected, validated fields from an endpoint."""
    safe = {
        key: normalized_platform(value) if key == "platform" and isinstance(value, str) else value
        for key, value in details.items()
        if key in SAFE_DETAIL_KEYS
        and (isinstance(value, bool) or isinstance(value, int) or isinstance(value, str))
        and (not isinstance(value, str) or len(value) <= 64)
    }
    if safe:
        request.state.audit_request_details = safe


def note_response_details(request: Request, **details: str | int | bool) -> None:
    safe = {
        key: value
        for key, value in details.items()
        if key in SAFE_DETAIL_KEYS
        and (isinstance(value, bool) or isinstance(value, int) or isinstance(value, str))
        and (not isinstance(value, str) or len(value) <= 64)
    }
    if safe:
        request.state.audit_response_details = safe


def attempted_identity_reference(email: str) -> str:
    """Correlate failed attempts without storing the supplied email address."""
    return opaque_reference("login", email.strip().lower())


def opaque_reference(kind: str, value: str) -> str:
    key = get_settings().jwt_secret.encode("utf-8")
    payload = f"cocoon-audit-{kind}:v1:{value}".encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def event_action(method: str, route: str | None) -> str | None:
    if route is None:
        return None
    if method == "GET":
        if route.endswith("/typing") or route == "/api/assistant/status":
            return None
        if route.startswith("/api/secret/") and not route.endswith("/typing"):
            return "secret.read"
        return READ_ACTIONS.get(route) or ("api.get" if route.startswith("/api/") else None)
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if method == "POST" and route == "/api/audit/button-press":
        return "ui.button.press"
    if route in AUTH_ACTIONS:
        return AUTH_ACTIONS[route]
    if route in SECRET_STEP_UP:
        return SECRET_STEP_UP[route]
    if route in NOISY_ROUTES or route.endswith("/typing"):
        return None
    if route == "/api/auth/passkeys/login/options":
        return "auth.login.passkey.options"
    if route.startswith("/api/auth/passkeys/login/"):
        return None
    if route.startswith("/api/secret/passkeys/") and route.endswith("/options"):
        return None
    if route.startswith("/api/secret/"):
        return "secret.action"
    if (method, route) in WRITE_ACTIONS:
        return WRITE_ACTIONS[(method, route)]
    if route.startswith("/api/"):
        return f"api.{method.lower()}"
    return None


def client_ip(request: Request) -> tuple[str | None, str | None]:
    peer = request.client.host if request.client is not None else None
    try:
        peer_address = ipaddress.ip_address(peer) if peer else None
    except ValueError:
        return None, None
    if peer_address is None:
        return None, None
    trusted = [
        ipaddress.ip_network(cidr, strict=False)
        for cidr in get_settings().audit_trusted_proxy_cidrs
    ]
    if not any(peer_address in network for network in trusted):
        return str(peer_address), "peer"
    forwarded = request.headers.get("X-Forwarded-For", "")
    # Walk backwards through trusted hops; ignore a client-supplied prefix.
    for item in reversed(forwarded.split(",")):
        try:
            address = ipaddress.ip_address(item.strip())
        except ValueError:
            return str(peer_address), "peer"
        if not any(address in network for network in trusted):
            return str(address), "forwarded"
    return str(peer_address), "peer"


def user_agent_family(request: Request) -> str | None:
    agent = request.headers.get("User-Agent", "").lower()[:512]
    for marker, name in (
        ("edg/", "Edge"),
        ("firefox/", "Firefox"),
        ("chrome/", "Chrome"),
        ("safari/", "Safari"),
        ("okhttp", "OkHttp"),
        ("python-httpx", "HTTPX"),
    ):
        if marker in agent:
            return name
    return "Other" if agent else None


def query_details(request: Request, route: str) -> dict[str, int] | None:
    if route.startswith("/api/secret/"):
        return None
    details = {}
    for key in ("limit", "offset", "page"):
        values = request.query_params.getlist(key)
        if len(values) == 1 and values[0].isdecimal() and len(values[0]) <= 6:
            details[key] = int(values[0])
    return details or None


def path_details(request: Request, route: str) -> dict[str, str]:
    if route.startswith("/api/secret/"):
        return {}
    details = {}
    for key, value in request.path_params.items():
        if not key.endswith("_id"):
            continue
        try:
            resource_id = str(UUID(str(value)))
        except ValueError:
            continue
        details[f"{key.removesuffix('_id')}_ref"] = opaque_reference(key, resource_id)
    return details


def response_metadata(response: Response | None) -> dict[str, str | bool] | None:
    if response is None:
        return None
    content_type = response.headers.get("content-type", "").split(";", 1)[0]
    details: dict[str, str | bool] = {}
    if content_type in {"application/json", "text/event-stream", "text/plain"}:
        details["content_type"] = content_type
    if content_type == "text/event-stream":
        details["streamed"] = True
    return details or None


def error_code(status_code: int) -> str | None:
    if status_code < 400:
        return None
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_failed",
        429: "rate_limited",
    }.get(status_code, "server_error" if status_code >= 500 else "client_error")


def _record_request(
    request: Request,
    *,
    request_id: str,
    status_code: int,
    duration_ms: int,
    response: Response | None = None,
) -> None:
    route = getattr(request.scope.get("route"), "path", None)
    action = event_action(request.method, route)
    if action is None or route is None:
        return
    is_secret = route.startswith("/api/secret/")
    ip, ip_source = client_ip(request)
    request_data = path_details(request, route)
    if not is_secret:
        request_data.update(getattr(request.state, "audit_request_details", {}))
    response_data = response_metadata(response) or {}
    if code := error_code(status_code):
        response_data["error_code"] = code
    if not is_secret:
        response_data.update(getattr(request.state, "audit_response_details", {}))
    response_length = response.headers.get("content-length") if response else None
    response_bytes = (
        int(response_length)
        if response_length and response_length.isdecimal() and len(response_length) <= 12
        else None
    )
    factory = getattr(request.app.state, "test_session_factory", SessionLocal)
    try:
        with factory.begin() as session:
            session.add(
                AuditEvent(
                    actor_user_id=getattr(request.state, "audit_user_id", None),
                    session_id=getattr(request.state, "audit_session_id", None),
                    device_id=getattr(request.state, "audit_device_id", None),
                    attempted_identity_ref=getattr(
                        request.state, "audit_attempted_identity_ref", None
                    ),
                    client_ip=ip,
                    client_ip_source=ip_source,
                    user_agent_family=user_agent_family(request),
                    client_platform=getattr(request.state, "audit_platform", None),
                    request_id=UUID(request_id),
                    action=action,
                    outcome=(
                        "success"
                        if status_code < 400
                        else "denied"
                        if status_code in {401, 403}
                        else "error"
                    ),
                    method=request.method,
                    route=None if is_secret else route,
                    status_code=status_code,
                    duration_ms=max(0, duration_ms),
                    response_bytes=response_bytes,
                    request_details=request_data or None,
                    query_details=query_details(request, route),
                    response_details=response_data or None,
                )
            )
    except Exception:
        logger.exception("audit_write_failed request_id=%s action=%s", request_id, action)


def record_request(
    request: Request,
    *,
    request_id: str,
    status_code: int,
    duration_ms: int,
    response: Response | None = None,
) -> None:
    """Never let a logging failure change the HTTP result."""
    try:
        _record_request(
            request,
            request_id=request_id,
            status_code=status_code,
            duration_ms=duration_ms,
            response=response,
        )
    except Exception:
        logger.exception("audit_write_failed request_id=%s", request_id)
