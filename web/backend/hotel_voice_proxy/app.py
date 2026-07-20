from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web
from azure.identity.aio import DefaultAzureCredential

from hotel_voice_proxy.auth import AuthenticationError, EntraTokenValidator
from hotel_voice_proxy.config import ProxySettings
from hotel_voice_proxy.foundry import FoundrySocket, FoundryWebSocketConnector
from hotel_voice_proxy.sessions import BrowserSessionStore, SessionError

logger = logging.getLogger(__name__)

SETTINGS_KEY = web.AppKey("settings", ProxySettings)
VALIDATOR_KEY = web.AppKey("validator", EntraTokenValidator)
SESSIONS_KEY = web.AppKey("sessions", BrowserSessionStore)
CONNECTOR_KEY = web.AppKey("connector", FoundryWebSocketConnector)
CREDENTIAL_KEY = web.AppKey("credential", DefaultAzureCredential)


def create_app(
    settings: ProxySettings,
    *,
    validator: EntraTokenValidator | None = None,
    session_store: BrowserSessionStore | None = None,
    connector: FoundryWebSocketConnector | None = None,
) -> web.Application:
    app = web.Application(client_max_size=2 * 1024 * 1024)
    credential = DefaultAzureCredential()
    app[SETTINGS_KEY] = settings
    app[VALIDATOR_KEY] = validator or EntraTokenValidator(
        tenant_id=settings.entra_tenant_id,
        audience=settings.entra_audience,
        required_scope=settings.entra_required_scope,
    )
    app[SESSIONS_KEY] = session_store or BrowserSessionStore(
        ttl_seconds=settings.session_ttl_seconds,
        max_sessions=settings.max_sessions,
    )
    app[CREDENTIAL_KEY] = credential
    app[CONNECTOR_KEY] = connector or FoundryWebSocketConnector(
        credential=credential,
        project_endpoint=settings.foundry_project_endpoint,
        agent_name=settings.foundry_agent_name,
    )
    app.router.add_get("/api/config", _get_config)
    app.router.add_post("/api/auth/session", _create_session)
    app.router.add_get("/api/calls", _call_websocket)
    app.router.add_get("/api/health", _health)
    app.on_cleanup.append(_cleanup)
    _serve_frontend_if_present(app)
    return app


async def _get_config(request: web.Request) -> web.Response:
    settings = request.app[SETTINGS_KEY]
    return web.json_response(
        {
            "environment": settings.environment,
            "hotelBrandName": "Lyrenza Hotels",
            "syntheticDataNotice": (
                "All guests, reservations, and folio details in this demo are synthetic."
            ),
            "features": {
                "voiceEnabled": True,
                "textEnabled": True,
                "headlessDemoEnabled": True,
                "prerecordedAudioEnabled": True,
            },
            "websocketPath": "/api/calls",
            "maxReconnectAttempts": 3,
            "reconnectBackoffMs": 750,
        }
    )


async def _create_session(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _error_response("The session request must be valid JSON.", 400)
    if body != {"clientContext": "web"}:
        return _error_response("The session request has an invalid client context.", 400)

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return _error_response("A bearer access token is required.", 401)
    try:
        user = await request.app[VALIDATOR_KEY].validate(token)
    except AuthenticationError as exc:
        logger.warning("Browser access token rejected: %s", exc)
        return _error_response("The access token is invalid or unauthorized.", 401)

    session = await request.app[SESSIONS_KEY].create(user)
    return web.json_response(
        {
            "sessionHandle": session.handle,
            "expiresAt": datetime.fromtimestamp(
                session.expires_at_epoch,
                tz=UTC,
            )
            .isoformat()
            .replace("+00:00", "Z"),
            "agentSessionId": session.agent_session_id,
        },
        status=201,
        headers={"Cache-Control": "no-store"},
    )


async def _call_websocket(request: web.Request) -> web.StreamResponse:
    websocket = web.WebSocketResponse(heartbeat=30, max_msg_size=16 * 1024 * 1024)
    await websocket.prepare(request)
    handle: str | None = None
    claimed = False
    try:
        first = await asyncio.wait_for(websocket.receive(), timeout=5)
        auth_frame = _parse_auth_frame(first)
        handle = auth_frame["opaqueHandle"]
        session = await request.app[SESSIONS_KEY].claim(handle)
        claimed = True
        supplied_session_id = auth_frame.get("agentSessionId")
        if supplied_session_id and supplied_session_id != session.agent_session_id:
            raise SessionError("The agent session ID does not match this browser session")
    except (TimeoutError, SessionError, ValueError):
        if claimed and handle is not None:
            await request.app[SESSIONS_KEY].release(handle)
        await websocket.send_json(
            {"type": "error", "message": "The call session is invalid or expired.", "code": "auth"}
        )
        await websocket.close(code=1008, message=b"Invalid call session")
        return websocket

    upstream: FoundrySocket | None = None
    try:
        upstream = await request.app[CONNECTOR_KEY].open(session.agent_session_id)
        await upstream.websocket.send_json(
            {
                "type": "session.start",
                "mode": auth_frame["mode"],
            }
        )
        await _relay_call(websocket, upstream)
    except Exception:
        logger.exception("The Foundry call proxy failed")
        if not websocket.closed:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "The hotel voice service is temporarily unavailable.",
                    "code": "upstream",
                }
            )
            await websocket.close(code=1011, message=b"Upstream unavailable")
    finally:
        if upstream is not None:
            await upstream.close()
        if claimed and handle is not None:
            await request.app[SESSIONS_KEY].release(handle)
    return websocket


def _parse_auth_frame(message: Any) -> dict[str, Any]:
    if message.type != WSMsgType.TEXT:
        raise ValueError("The first WebSocket frame must be JSON")
    frame = json.loads(message.data)
    if not isinstance(frame, dict) or frame.get("type") != "auth":
        raise ValueError("The first WebSocket frame must authenticate the call")
    if frame.get("mode") not in {"voice", "text", "prerecorded"}:
        raise ValueError("Unsupported call mode")
    if not isinstance(frame.get("opaqueHandle"), str):
        raise ValueError("Missing opaque session handle")
    return frame


async def _relay_call(browser: web.WebSocketResponse, upstream: FoundrySocket) -> None:
    browser_task = asyncio.create_task(_relay_browser_to_foundry(browser, upstream))
    foundry_task = asyncio.create_task(_relay_foundry_to_browser(upstream, browser))
    done, pending = await asyncio.wait(
        {browser_task, foundry_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        task.result()


async def _relay_browser_to_foundry(
    browser: web.WebSocketResponse,
    upstream: FoundrySocket,
) -> None:
    async for message in browser:
        if message.type == WSMsgType.TEXT:
            await upstream.websocket.send_str(message.data)
        elif message.type == WSMsgType.BINARY:
            await upstream.websocket.send_bytes(message.data)
        elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
            return


async def _relay_foundry_to_browser(
    upstream: FoundrySocket,
    browser: web.WebSocketResponse,
) -> None:
    async for message in upstream.websocket:
        if message.type == WSMsgType.TEXT:
            await browser.send_str(message.data)
        elif message.type == WSMsgType.BINARY:
            await browser.send_bytes(message.data)
        elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED}:
            return
        elif message.type == WSMsgType.ERROR:
            raise RuntimeError("The Foundry WebSocket closed with an error")
    if upstream.websocket.close_code not in {None, 1000}:
        raise RuntimeError(
            f"The Foundry WebSocket closed unexpectedly ({upstream.websocket.close_code})"
        )


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def _error_response(message: str, status: int) -> web.Response:
    return web.json_response(
        {"error": message},
        status=status,
        headers={"Cache-Control": "no-store"},
    )


def _serve_frontend_if_present(app: web.Application) -> None:
    dist = Path(
        os.getenv(
            "VOICE_FRONTEND_DIST",
            str(Path.cwd() / "web" / "frontend" / "dist"),
        )
    )
    if not dist.is_dir():
        return
    assets = dist / "assets"
    if assets.is_dir():
        app.router.add_static("/assets", assets)
    audio = dist / "audio"
    if audio.is_dir():
        app.router.add_static("/audio", audio)

    async def root_asset(request: web.Request) -> web.FileResponse:
        return web.FileResponse(dist / request.path.lstrip("/"))

    async def index(_request: web.Request) -> web.FileResponse:
        return web.FileResponse(dist / "index.html")

    for filename in ("favicon.svg", "redirect.html"):
        if (dist / filename).is_file():
            app.router.add_get(f"/{filename}", root_asset)
    app.router.add_get("/", index)
    app.router.add_get("/{path:(?!api/).*}", index)


async def _cleanup(app: web.Application) -> None:
    await app[CREDENTIAL_KEY].close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = ProxySettings.from_environment()
    web.run_app(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
