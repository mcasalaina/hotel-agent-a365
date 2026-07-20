from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestClient, TestServer
from hotel_voice_proxy.app import _parse_auth_frame, _serve_frontend_if_present
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


def test_frontend_root_assets_are_served_before_spa_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    (tmp_path / "redirect.html").write_text("<html>bridge</html>", encoding="utf-8")
    monkeypatch.setenv("VOICE_FRONTEND_DIST", str(tmp_path))

    async def exercise() -> None:
        app = web.Application()
        _serve_frontend_if_present(app)
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            favicon = await client.get("/favicon.svg")
            assert favicon.status == 200
            assert favicon.content_type == "image/svg+xml"
            assert favicon.headers["Cache-Control"] == "no-store"
            assert await favicon.text() == "<svg></svg>"

            redirect = await client.get("/redirect.html")
            assert redirect.status == 200
            assert redirect.headers["Cache-Control"] == "no-store"
            assert await redirect.text() == "<html>bridge</html>"

            fallback = await client.get("/contact-center")
            assert fallback.status == 200
            assert fallback.headers["Cache-Control"] == "no-store"
            assert await fallback.text() == "<html>app</html>"
        finally:
            await client.close()

    asyncio.run(exercise())
