"""Short-lived typing hints for unlocked hidden conversations.

Nothing is persisted or sent through the account-wide realtime channel.
"""

from threading import Lock
from time import monotonic
from uuid import UUID


class SecretTypingRegistry:
    def __init__(self) -> None:
        self._expires_at: dict[tuple[UUID, UUID], float] = {}
        self._lock = Lock()

    def update(self, conversation_id: UUID, user_id: UUID, is_typing: bool) -> None:
        with self._lock:
            self._purge()
            key = (conversation_id, user_id)
            if is_typing:
                self._expires_at[key] = monotonic() + 4.5
            else:
                self._expires_at.pop(key, None)

    def is_other_typing(self, conversation_id: UUID, other_user_ids: list[UUID]) -> bool:
        with self._lock:
            self._purge()
            return any((conversation_id, user_id) in self._expires_at for user_id in other_user_ids)

    def clear_user(self, user_id: UUID) -> None:
        with self._lock:
            self._expires_at = {
                key: expires_at for key, expires_at in self._expires_at.items() if key[1] != user_id
            }

    def _purge(self) -> None:
        now = monotonic()
        self._expires_at = {
            key: expires_at for key, expires_at in self._expires_at.items() if expires_at > now
        }


secret_typing = SecretTypingRegistry()
