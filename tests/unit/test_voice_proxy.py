from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestClient, TestServer
from azure.core.credentials import AccessToken
from azure.identity.aio import DefaultAzureCredential
from hotel_voice_proxy.app import (
    CREDENTIAL_KEY,
    _parse_auth_frame,
    _serve_frontend_if_present,
    _verify_foundry_access,
)
from hotel_voice_proxy.auth import AuthenticatedUser
from hotel_voice_proxy.config import ProxySettings
from hotel_voice_proxy.foundry import FOUNDRY_SCOPE
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


def test_proxy_settings_load_user_assigned_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_CLIENT_ID", "managed-identity-client")
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant")
    monkeypatch.setenv("ENTRA_API_AUDIENCE", "audience")
    monkeypatch.setenv("ENTRA_REQUIRED_SCOPE", "HotelAgent.Access")
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://example.services.ai.azure.com/api/projects/example",
    )

    settings = ProxySettings.from_environment()

    assert settings.managed_identity_client_id == "managed-identity-client"


def test_startup_verifies_foundry_managed_identity() -> None:
    credential = AsyncMock(spec=DefaultAzureCredential)
    credential.get_token.return_value = AccessToken("not-a-real-token", 1_800_000_000)
    app = web.Application()
    app[CREDENTIAL_KEY] = credential

    asyncio.run(_verify_foundry_access(app))

    credential.get_token.assert_awaited_once_with(FOUNDRY_SCOPE)


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
