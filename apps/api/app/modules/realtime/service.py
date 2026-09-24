import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import UUID

from fastapi import WebSocket


class RealtimeTickets:
    def __init__(self) -> None:
        self._tickets: dict[str, tuple[UUID, datetime]] = {}
        self._lock = Lock()

    def issue(self, user_id: UUID) -> str:
        with self._lock:
            self._purge_expired()
            ticket = secrets.token_urlsafe(32)
            self._tickets[ticket] = (user_id, datetime.now(UTC) + timedelta(seconds=60))
        return ticket

    def consume(self, ticket: str) -> UUID | None:
        with self._lock:
            item = self._tickets.pop(ticket, None)
        if item is None or item[1] <= datetime.now(UTC):
            return None
        return item[0]

    def _purge_expired(self) -> None:
        now = datetime.now(UTC)
        self._tickets = {key: value for key, value in self._tickets.items() if value[1] > now}


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)

    async def disconnect(self, user_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(user_id)
            if connections is None:
                return
            connections.discard(websocket)
            if not connections:
                self._connections.pop(user_id, None)

    async def broadcast(self, recipients: list[UUID], event: dict[str, object]) -> None:
        async with self._lock:
            sockets = [
                socket for user_id in recipients for socket in self._connections.get(user_id, set())
            ]
        for socket in sockets:
            try:
                await socket.send_json(event)
            except RuntimeError:
                # The receive loop will remove sockets that were closed concurrently.
                pass


tickets = RealtimeTickets()
connections = ConnectionManager()
