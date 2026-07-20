from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from hotel_voice_proxy.auth import AuthenticatedUser


class SessionError(ValueError):
    """Raised when an opaque browser session is invalid or expired."""


@dataclass(frozen=True, slots=True)
class BrowserSession:
    handle: str
    subject: str
    tenant_id: str
    expires_at_epoch: float
    agent_session_id: str


class BrowserSessionStore:
    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_sessions: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if ttl_seconds <= 0 or max_sessions <= 0:
            raise ValueError("Session TTL and capacity must both be positive")
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._clock = clock
        self._sessions: dict[str, BrowserSession] = {}
        self._active_handles: set[str] = set()
        self._lock = asyncio.Lock()

    async def create(self, user: AuthenticatedUser) -> BrowserSession:
        async with self._lock:
            now = self._clock()
            self._remove_expired(now)
            while len(self._sessions) >= self._max_sessions:
                evictable = next(
                    (handle for handle in self._sessions if handle not in self._active_handles),
                    None,
                )
                if evictable is None:
                    raise SessionError("The browser session capacity is currently full")
                self._sessions.pop(evictable)
            handle = secrets.token_urlsafe(32)
            session = BrowserSession(
                handle=handle,
                subject=user.subject,
                tenant_id=user.tenant_id,
                expires_at_epoch=now + self._ttl_seconds,
                agent_session_id=uuid.uuid4().hex,
            )
            self._sessions[handle] = session
            return session

    async def get(self, handle: str) -> BrowserSession:
        async with self._lock:
            return self._get_valid_session(handle)

    async def claim(self, handle: str) -> BrowserSession:
        async with self._lock:
            session = self._get_valid_session(handle)
            if handle in self._active_handles:
                raise SessionError("The browser session is already in use")
            self._active_handles.add(handle)
            return session

    async def release(self, handle: str) -> None:
        async with self._lock:
            self._active_handles.discard(handle)

    def _get_valid_session(self, handle: str) -> BrowserSession:
        now = self._clock()
        self._remove_expired(now)
        session = self._sessions.get(handle)
        if session is None:
            raise SessionError("The browser session is invalid or expired")
        return session

    def _remove_expired(self, now: float) -> None:
        expired = [
            handle for handle, session in self._sessions.items() if session.expires_at_epoch <= now
        ]
        for handle in expired:
            self._sessions.pop(handle, None)
            self._active_handles.discard(handle)
