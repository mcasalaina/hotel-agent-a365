from __future__ import annotations

import asyncio
from pathlib import Path

import jwt
import pytest
from azure.ai.voicelive.models import (
    ResponseFunctionCallItem,
    ServerEventConversationItemInputAudioTranscriptionCompleted,
    ServerEventConversationItemInputAudioTranscriptionDelta,
    ServerEventResponseOutputItemAdded,
    ServerEventResponseOutputItemDone,
)
from hotel_servicing_agent.config import Settings, _voice_live_defaults
from hotel_servicing_agent.voice_live import VoiceLiveBridge
from hotel_voice_proxy.auth import (
    AuthenticatedUser,
    AuthenticationError,
    EntraTokenValidator,
)
from hotel_voice_proxy.foundry import build_foundry_websocket_url
from hotel_voice_proxy.sessions import BrowserSessionStore, SessionError


class _UnusedCredential:
    async def get_token(self, *scopes: str, **kwargs: object) -> object:
        raise AssertionError("The test must not request a token")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        project_endpoint="https://example.services.ai.azure.com/api/projects/hotels",
        model_deployment="gpt-5.4-mini",
        voice_live_endpoint="https://example.services.ai.azure.com",
        voice_live_api_version="2026-04-10",
        voice_live_agent_name="hotel-servicing-agent",
        voice_live_agent_version=None,
        voice_live_project_name="hotels",
        voice_live_voice="en-US-AvaMultilingualNeural",
        voice_live_prefer_locales=(),
        search_endpoint="https://search.example",
        knowledge_base_name="hotel-foundryiq",
        fabric_data_agent_mcp_url="https://fabric.example/mcp",
        fabric_workspace_id="workspace",
        fabric_guest_services_lakehouse_id="lakehouse",
        fabric_reservation_notebook_id="notebook",
        agent365_tenant_id="tenant",
        agent365_blueprint_client_id="blueprint",
        agent365_blueprint_secret_vault_url="https://vault.example",
        agent365_blueprint_secret_name="secret",
        agent365_instance_client_id="instance",
        work_iq_servers=(),
        instructions="Test",
    )


def test_voice_live_defaults_come_from_project_endpoint() -> None:
    assert _voice_live_defaults("https://example.services.ai.azure.com/api/projects/hotels") == (
        "https://example.services.ai.azure.com",
        "hotels",
    )


def test_voice_session_uses_multilingual_speech_and_interim_response(
    tmp_path: Path,
) -> None:
    bridge = VoiceLiveBridge(_settings(tmp_path), _UnusedCredential())  # type: ignore[arg-type]
    session = bridge.build_session_config(mode="voice", session_id="session-1")
    payload = session.as_dict()

    assert payload["voice"]["name"] == "en-US-AvaMultilingualNeural"
    assert "locale" not in payload["voice"]
    assert payload["turn_detection"]["type"] == "azure_semantic_vad_multilingual"
    assert payload["turn_detection"]["interrupt_response"] is True
    assert payload["input_audio_transcription"]["model"] == "azure-speech"
    assert payload["interim_response"]["type"] == "llm_interim_response"
    assert set(payload["interim_response"]["triggers"]) == {"tool", "latency"}
    interim_instructions = payload["interim_response"]["instructions"]
    assert "established conversation language" in interim_instructions
    assert "Names, hotel or place names" in interim_instructions
    assert "clearly and predominantly in another language" in interim_instructions
    assert "latest complete utterance is authoritative" in interim_instructions
    assert "Tool output must not trigger a language change" in interim_instructions
    assert "instructions" not in payload


def test_agent_instructions_require_stable_language_selection() -> None:
    instructions = (
        Path(__file__).parents[2] / "src/hotel-servicing-agent/agent-instructions.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join(instructions.split())

    assert "language of the user's latest complete utterance" in normalized
    assert "across text, voice, and tool-backed answers" in normalized
    assert "never adopt the language of tool output" in normalized
    assert "Names, hotel or place names" in normalized
    assert "clearly and predominantly in another language" in normalized
    assert "latest complete utterance" in normalized
    assert "overrides earlier turns" in normalized
    assert "one to three short, conversational sentences" in normalized
    assert "Do not use Markdown, bullets, numbered lists, tables" in normalized
    assert "Ask at most one focused question at a time" in normalized
    assert "ask only for the next missing detail" in normalized
    assert '"Any reservations" or reservations "on file"' in normalized
    assert "query reservations by that ID" in normalized
    assert "historical or cancelled reservations" in normalized


def test_prerecorded_session_disables_automatic_vad_response(tmp_path: Path) -> None:
    bridge = VoiceLiveBridge(_settings(tmp_path), _UnusedCredential())  # type: ignore[arg-type]
    session = bridge.build_session_config(mode="prerecorded", session_id="session-1")
    payload = session.as_dict()

    assert payload["turn_detection"]["type"] == "azure_semantic_vad_multilingual"
    assert payload["turn_detection"]["create_response"] is False
    assert payload["turn_detection"]["silence_duration_ms"] == 2_000
    assert payload["input_audio_echo_cancellation"] is None


def test_voice_event_deltas_are_forwarded_as_accumulated_transcripts(
    tmp_path: Path,
) -> None:
    class FakeConnection:
        class FakeResponse:
            def __init__(self) -> None:
                self.create_calls = 0

            async def create(self) -> None:
                self.create_calls += 1

        def __init__(self) -> None:
            self.response = self.FakeResponse()

        def __aiter__(self) -> FakeConnection:
            self._events = iter(
                [
                    ServerEventConversationItemInputAudioTranscriptionDelta(
                        item_id="item-1",
                        delta="Buenos ",
                    ),
                    ServerEventConversationItemInputAudioTranscriptionDelta(
                        item_id="item-1",
                        delta="dias",
                    ),
                    ServerEventConversationItemInputAudioTranscriptionCompleted(
                        item_id="item-1",
                        content_index=0,
                        transcript="Buenos dias",
                    ),
                ]
            )
            return self

        async def __anext__(self) -> object:
            try:
                return next(self._events)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages: list[dict[str, object]] = []

        async def send_json(self, message: dict[str, object]) -> None:
            self.messages.append(message)

    bridge = VoiceLiveBridge(_settings(tmp_path), _UnusedCredential())  # type: ignore[arg-type]
    websocket = FakeWebSocket()
    connection = FakeConnection()
    asyncio.run(
        bridge._relay_voice_events(  # type: ignore[arg-type]
            connection,  # type: ignore[arg-type]
            websocket,
            "session-1",
            "prerecorded",
        )
    )

    assert [message["text"] for message in websocket.messages] == [
        "Buenos ",
        "Buenos dias",
        "Buenos dias",
    ]
    assert connection.response.create_calls == 1


def test_voice_tool_calls_are_forwarded_as_safe_timeline_events(tmp_path: Path) -> None:
    class FakeConnection:
        class FakeResponse:
            async def create(self) -> None:
                raise AssertionError("The test must not create a response")

        def __init__(self) -> None:
            self.response = self.FakeResponse()

        def __aiter__(self) -> FakeConnection:
            fabric_call = ResponseFunctionCallItem(
                name="query_hotel_operations_data",
                call_id="fabric-call",
                arguments='{"question":"secret details"}',
                status="in_progress",
            )
            self._events = iter(
                [
                    ServerEventResponseOutputItemAdded(
                        response_id="response-1",
                        output_index=0,
                        item=fabric_call,
                    ),
                    ServerEventResponseOutputItemDone(
                        response_id="response-1",
                        output_index=0,
                        item=ResponseFunctionCallItem(
                            name="query_hotel_operations_data",
                            call_id="fabric-call",
                            arguments='{"question":"secret details"}',
                            status="completed",
                        ),
                    ),
                    ServerEventResponseOutputItemAdded(
                        response_id="response-1",
                        output_index=1,
                        item=ResponseFunctionCallItem(
                            name="query_work_context",
                            call_id="work-iq-call",
                            arguments='{"question":"private context"}',
                            status="in_progress",
                        ),
                    ),
                ]
            )
            return self

        async def __anext__(self) -> object:
            try:
                return next(self._events)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages: list[dict[str, object]] = []

        async def send_json(self, message: dict[str, object]) -> None:
            self.messages.append(message)

    bridge = VoiceLiveBridge(_settings(tmp_path), _UnusedCredential())  # type: ignore[arg-type]
    websocket = FakeWebSocket()
    asyncio.run(
        bridge._relay_voice_events(  # type: ignore[arg-type]
            FakeConnection(),  # type: ignore[arg-type]
            websocket,
            "session-1",
            "voice",
        )
    )

    assert [(message["category"], message["message"]) for message in websocket.messages] == [
        ("data_source", "Querying hotel operations and reservations in Fabric."),
        ("data_source", "Querying Microsoft 365 work context with Work IQ."),
    ]
    assert all("secret" not in str(message) for message in websocket.messages)
    assert all("private" not in str(message) for message in websocket.messages)


def test_foundry_websocket_url_uses_current_route_and_session() -> None:
    url = build_foundry_websocket_url(
        "https://example.services.ai.azure.com/api/projects/hotels",
        "hotel-servicing-agent",
        "session-1",
    )

    assert url.startswith(
        "wss://example.services.ai.azure.com/api/projects/hotels/agents/"
        "hotel-servicing-agent/endpoint/protocols/invocations_ws?"
    )
    assert "api-version=v1" in url
    assert "agent_session_id=session-1" in url


def test_browser_session_store_expires_handles() -> None:
    now = 100.0
    store = BrowserSessionStore(
        ttl_seconds=10,
        max_sessions=2,
        clock=lambda: now,
    )
    user = AuthenticatedUser(subject="user", tenant_id="tenant", username=None)
    session = asyncio.run(store.create(user))

    assert asyncio.run(store.get(session.handle)) == session
    now = 111.0
    with pytest.raises(SessionError):
        asyncio.run(store.get(session.handle))


def test_entra_validator_rejects_wrong_tenant_without_key_lookup() -> None:
    token = jwt.encode(
        {"tid": "wrong-tenant", "sub": "user"},
        key="",
        algorithm="none",
    )
    validator = EntraTokenValidator(
        tenant_id="expected-tenant",
        audience="api://hotel",
        required_scope="HotelAgent.Access",
    )

    with pytest.raises(AuthenticationError, match="different tenant"):
        asyncio.run(validator.validate(token))
