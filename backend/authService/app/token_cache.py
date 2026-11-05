"""Short-lived memory of verified /auth/me results.

Every service calls /auth/me on every request, and each call costs two
Supabase round trips: verifying the token and reading staff_roles. Keeping a
verified result for a few seconds lets repeat requests skip both.

Trade-off: a revoked session, or a role changed outside this service, can take
up to ``TTL_SECONDS`` to take effect. Role changes made through
``PATCH /auth/users/{id}/role`` clear that user's entries at once. An entry
never outlives the token's own ``exp``, and a token whose ``exp`` cannot be
read is not cached at all.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from collections.abc import Callable
from typing import Generic, TypeVar

TTL_SECONDS = 30.0
MAX_ENTRIES = 1024

Value = TypeVar("Value")


def token_expiry(token: str) -> float | None:
    """Return the JWT's ``exp`` claim (Unix seconds), or None if unreadable.

    Only called after Supabase has verified the token; the claim only caps how
    long the verified result is kept.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]
    except (IndexError, ValueError, KeyError, TypeError):
        return None
    if isinstance(exp, bool) or not isinstance(exp, int | float):
        return None
    return float(exp)


def _key(token: str) -> str:
    # Store a hash, never the bearer token itself.
    return hashlib.sha256(token.encode()).hexdigest()


class VerifiedUserCache(Generic[Value]):
    def __init__(
        self,
        ttl_seconds: float = TTL_SECONDS,
        max_entries: int = MAX_ENTRIES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, str, Value]] = {}

    def get(self, token: str) -> Value | None:
        key = _key(token)
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, _, value = entry
            if expires_at <= now:
                del self._entries[key]
                return None
            return value

    def put(self, token: str, user_id: str, value: Value) -> None:
        exp = token_expiry(token)
        if exp is None:
            return
        now = self._clock()
        expires_at = min(now + self._ttl, exp)
        if expires_at <= now:
            return
        with self._lock:
            if len(self._entries) >= self._max_entries:
                self._entries = {
                    k: e for k, e in self._entries.items() if e[0] > now
                }
                if len(self._entries) >= self._max_entries:
                    self._entries.clear()
            self._entries[_key(token)] = (expires_at, user_id, value)

    def invalidate_user(self, user_id: str) -> None:
        with self._lock:
            self._entries = {
                k: e for k, e in self._entries.items() if e[1] != user_id
            }

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
