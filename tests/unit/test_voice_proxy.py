from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from aiohttp import WSMsgType
from hotel_voice_proxy.app import _parse_auth_frame
from hotel_voice_proxy.auth import AuthenticatedUser
from hotel_voice_proxy.sessions import BrowserSessionStore, SessionError


def test_call_auth_frame_supports_prerecorded_mode() -> None:
    message = SimpleNamespace(
        type=WSMsgType.TEXT,
        data=json.dumps(
            {
                "type": "auth",
                "opaqueHandle": "opaque",
                "mode": "prerecorded",
            }
        ),
    )

    assert _parse_auth_frame(message)["mode"] == "prerecorded"


def test_call_auth_frame_rejects_binary_authentication() -> None:
    message = SimpleNamespace(type=WSMsgType.BINARY, data=b"opaque")

    with pytest.raises(ValueError, match="must be JSON"):
        _parse_auth_frame(message)


def test_browser_session_cannot_be_replayed_concurrently() -> None:
    async def exercise() -> None:
        store = BrowserSessionStore(ttl_seconds=60, max_sessions=10)
        user = AuthenticatedUser(subject="user", tenant_id="tenant", username=None)
        session = await store.create(user)

        assert await store.claim(session.handle) == session
        with pytest.raises(SessionError, match="already in use"):
            await store.claim(session.handle)
        await store.release(session.handle)
        assert await store.claim(session.handle) == session

    asyncio.run(exercise())
