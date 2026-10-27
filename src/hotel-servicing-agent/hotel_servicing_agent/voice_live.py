from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from azure.ai.voicelive.aio import VoiceLiveConnection, connect
from azure.ai.voicelive.models import (
    AssistantMessageItem,
    AudioEchoCancellation,
    AudioInputTranscriptionOptions,
    AudioNoiseReduction,
    AzureSemanticVadMultilingual,
    AzureStandardVoice,
    InputAudioFormat,
    InputTextContentPart,
    InterimResponseTrigger,
    LlmInterimResponseConfig,
    MessageItem,
    Modality,
    OutputAudioFormat,
    OutputTextContentPart,
    RequestSession,
    ResponseCreateParams,
    ResponseFunctionCallItem,
    ServerEventConversationItemInputAudioTranscriptionCompleted,
    ServerEventConversationItemInputAudioTranscriptionDelta,
    ServerEventError,
    ServerEventResponseAudioDelta,
    ServerEventResponseAudioTranscriptDelta,
    ServerEventResponseAudioTranscriptDone,
    ServerEventResponseOutputItemAdded,
    ServerEventResponseOutputItemDone,
    ServerEventResponseTextDone,
    ServerEventSessionUpdated,
    ServerEventType,
)
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import AzureError
from starlette.websockets import WebSocket

from hotel_servicing_agent.config import Settings

logger = logging.getLogger(__name__)

_ALLOWED_MODES = frozenset({"voice", "text", "prerecorded"})
_TOOL_ACTIVITY: dict[str, tuple[str, str]] = {
    "search_hotel_knowledge": (
        "data_source",
        "Searching approved hotel knowledge in Foundry IQ.",
    ),
    "query_hotel_operations_data": (
        "data_source",
        "Querying hotel operations and reservations in Fabric.",
    ),
    "manage_reservation": (
        "tool",
        "Updating reservation data in Fabric.",
    ),
    "check_work_context_access": (
        "tool",
        "Checking Microsoft 365 work-context access.",
    ),
    "query_work_context": (
        "data_source",
        "Querying Microsoft 365 work context with Work IQ.",
    ),
    "send_email": (
        "tool",
        "Sending an email with Work IQ.",
    ),
    "reply_to_email": (
        "tool",
        "Replying to an email with Work IQ.",
    ),
}


class VoiceLiveBridge:
    """Bridges the hosted invocations WebSocket to a Voice Live agent session."""

    def __init__(self, settings: Settings, credential: AsyncTokenCredential) -> None:
        self._settings = settings
        self._credential = credential
        self._conversation_ids: dict[str, str] = {}

    async def handle(self, websocket: WebSocket) -> None:
        start = await websocket.receive_json()
        if not isinstance(start, dict) or start.get("type") != "session.start":
            await _send_error(
                websocket,
                "The first frame must start the call session.",
                "bad_start",
            )
            return
        mode = start.get("mode")
        if mode not in _ALLOWED_MODES:
            await _send_error(websocket, "The requested call mode is not supported.", "bad_mode")
            return

        session_id = (
            os.getenv("FOUNDRY_AGENT_SESSION_ID")
            or websocket.query_params.get("agent_session_id")
            or uuid.uuid4().hex
        )
        await websocket.send_json({"type": "call_state", "state": "connecting"})

        async with connect(
            endpoint=self._settings.voice_live_endpoint,
            credential=self._credential,
            api_version=self._settings.voice_live_api_version,
            agent_name=self._settings.voice_live_agent_name,
            agent_version=self._settings.voice_live_agent_version,
            project_name=self._settings.voice_live_project_name,
            conversation_id=self._conversation_ids.get(session_id),
        ) as connection:
            await connection.session.update(
                session=self.build_session_config(mode=mode, session_id=session_id)
            )
            event_task = asyncio.create_task(
                self._relay_voice_events(connection, websocket, session_id, mode)
            )
            client_task = asyncio.create_task(
                self._relay_client_frames(connection, websocket, mode)
            )
            done, pending = await asyncio.wait(
                {event_task, client_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()

    def build_session_config(self, *, mode: str, session_id: str) -> RequestSession:
        prefer_locales = (
            list(self._settings.voice_live_prefer_locales)
            if self._settings.voice_live_prefer_locales
            else None
        )
        if mode == "prerecorded":
            turn_detection = AzureSemanticVadMultilingual(
                prefix_padding_ms=400,
                silence_duration_ms=2_000,
                auto_truncate=False,
                create_response=False,
                interrupt_response=False,
            )
        else:
            turn_detection = AzureSemanticVadMultilingual(
                prefix_padding_ms=400,
                silence_duration_ms=500,
                auto_truncate=True,
                create_response=True,
                interrupt_response=True,
            )
        return RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            voice=AzureStandardVoice(
                name=self._settings.voice_live_voice,
                prefer_locales=prefer_locales,
            ),
            input_audio_sampling_rate=24_000,
            input_audio_format=InputAudioFormat.PCM16,
            output_audio_format=OutputAudioFormat.PCM16,
            input_audio_transcription=AudioInputTranscriptionOptions(model="azure-speech"),
            turn_detection=turn_detection,
            input_audio_echo_cancellation=(
                None if mode == "prerecorded" else AudioEchoCancellation()
            ),
            input_audio_noise_reduction=AudioNoiseReduction(type="azure_deep_noise_suppression"),
            interim_response=LlmInterimResponseConfig(
                triggers=[
                    InterimResponseTrigger.TOOL,
                    InterimResponseTrigger.LATENCY,
                ],
                latency_threshold_ms=750,
                model="gpt-4.1-mini",
                instructions=(
                    "Use the caller's established conversation language. The caller's latest "
                    "complete utterance is authoritative: when it is clearly and predominantly in "
                    "another language, immediately use that language and override earlier turns. "
                    "If none is established, start in English. "
                    "Names, hotel or place names, accents, and isolated foreign words must not "
                    "trigger a language change. Tool output must not trigger a language change. "
                    "In eight words or fewer, say only that you are checking the requested "
                    "hotel information. Never invent progress or a result."
                ),
                max_completion_tokens=24,
            ),
            metadata={
                "channel": "web-voice",
                "agent_session_id": session_id,
            },
        )

    async def _relay_client_frames(
        self,
        connection: VoiceLiveConnection,
        websocket: WebSocket,
        mode: str,
    ) -> None:
        while True:
            frame = await websocket.receive()
            if frame["type"] == "websocket.disconnect":
                return
            audio = frame.get("bytes")
            if audio is not None:
                if len(audio) % 2:
                    await _send_error(
                        websocket,
                        "Audio frames must contain complete PCM16 samples.",
                        "bad_audio_frame",
                    )
                    continue
                await connection.input_audio_buffer.append(
                    audio=base64.b64encode(audio).decode("ascii")
                )
                continue

            text = frame.get("text")
            if text is None:
                continue
            try:
                message = _parse_client_message(text)
            except ValueError:
                await _send_error(websocket, "The call command was not valid JSON.", "bad_json")
                continue
            should_continue = await self._handle_client_message(
                connection,
                websocket,
                message,
                mode,
            )
            if not should_continue:
                return

    async def _handle_client_message(
        self,
        connection: VoiceLiveConnection,
        websocket: WebSocket,
        message: dict[str, Any],
        mode: str,
    ) -> bool:
        message_type = message.get("type")
        if message_type == "text_turn":
            text = message.get("text")
            if not isinstance(text, str) or not text.strip():
                await _send_error(websocket, "A text turn cannot be empty.", "empty_text")
                return True
            normalized = text.strip()
            await websocket.send_json(
                {
                    "type": "transcript",
                    "speaker": "user",
                    "text": normalized,
                    "isFinal": True,
                    "timestamp": _utc_timestamp(),
                }
            )
            await connection.conversation.item.create(
                item=MessageItem(
                    role="user",
                    content=[InputTextContentPart(text=normalized)],
                )
            )
            await connection.response.create()
            return True

        if message_type == "audio_commit":
            if mode != "prerecorded":
                await _send_error(
                    websocket,
                    "Audio commit is only valid for prerecorded calls.",
                    "bad_audio_commit",
                )
                return True
            await connection.input_audio_buffer.commit()
            return True

        if message_type == "cancel_output":
            await connection.output_audio_buffer.clear()
            try:
                await connection.response.cancel()
            except AzureError as exc:
                if "no active response" not in str(exc).lower():
                    raise
            return True

        if message_type == "mic_state":
            return True

        if message_type == "end_call":
            await websocket.send_json(
                {
                    "type": "disposition",
                    "outcome": "resolved",
                    "summary": "The caller ended the hotel guest-services session.",
                    "timestamp": _utc_timestamp(),
                }
            )
            await websocket.send_json({"type": "call_state", "state": "ended"})
            return False

        await _send_error(websocket, "The call command is not supported.", "unknown_command")
        return True

    async def _relay_voice_events(
        self,
        connection: VoiceLiveConnection,
        websocket: WebSocket,
        session_id: str,
        mode: str,
    ) -> None:
        greeting_sent = False
        user_transcript = ""
        agent_transcript = ""
        announced_tool_calls: set[str] = set()
        async for event in connection:
            if isinstance(event, ServerEventSessionUpdated):
                agent_config = event.session.agent
                if agent_config is not None:
                    self._conversation_ids[session_id] = agent_config.thread_id
                    if len(self._conversation_ids) > 1_000:
                        self._conversation_ids.pop(next(iter(self._conversation_ids)))
                await websocket.send_json({"type": "auth_ack", "agentSessionId": session_id})
                await websocket.send_json({"type": "call_state", "state": "connected"})
                if mode == "voice" and not greeting_sent:
                    greeting_sent = True
                    await websocket.send_json(
                        {
                            "type": "timeline_event",
                            "category": "progress",
                            "message": "Voice Live is welcoming the caller.",
                            "timestamp": _utc_timestamp(),
                        }
                    )
                    await connection.response.create(
                        response=ResponseCreateParams(
                            pre_generated_assistant_message=AssistantMessageItem(
                                content=[
                                    OutputTextContentPart(
                                        text=(
                                            "Welcome to Lyrenza Hotels. How can I help you today?"
                                        )
                                    )
                                ]
                            )
                        )
                    )
                continue

            if isinstance(event, ServerEventConversationItemInputAudioTranscriptionDelta):
                if event.delta:
                    user_transcript += event.delta
                    await _send_transcript(websocket, "user", user_transcript, False)
                continue

            if isinstance(event, ServerEventConversationItemInputAudioTranscriptionCompleted):
                await _send_transcript(websocket, "user", event.transcript, True)
                user_transcript = ""
                if mode == "prerecorded":
                    await connection.response.create()
                continue

            if isinstance(event, ServerEventResponseAudioTranscriptDelta):
                agent_transcript += event.delta
                await _send_transcript(websocket, "agent", agent_transcript, False)
                continue

            if isinstance(event, ServerEventResponseAudioTranscriptDone):
                await _send_transcript(websocket, "agent", event.transcript, True)
                agent_transcript = ""
                continue

            if isinstance(event, ServerEventResponseTextDone):
                await _send_transcript(websocket, "agent", event.text, True)
                continue

            if isinstance(event, ServerEventResponseAudioDelta):
                await websocket.send_bytes(event.delta)
                continue

            if isinstance(
                event,
                (ServerEventResponseOutputItemAdded, ServerEventResponseOutputItemDone),
            ):
                item = event.item
                if (
                    isinstance(item, ResponseFunctionCallItem)
                    and item.call_id not in announced_tool_calls
                ):
                    announced_tool_calls.add(item.call_id)
                    category, message = _TOOL_ACTIVITY.get(
                        item.name,
                        ("tool", "Using a backend service."),
                    )
                    await websocket.send_json(
                        {
                            "type": "timeline_event",
                            "category": category,
                            "message": message,
                            "timestamp": _utc_timestamp(),
                        }
                    )
                continue

            if event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                await websocket.send_json(
                    {
                        "type": "timeline_event",
                        "category": "progress",
                        "message": "Listening to the caller.",
                        "timestamp": _utc_timestamp(),
                    }
                )
                continue

            if event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
                await websocket.send_json(
                    {
                        "type": "timeline_event",
                        "category": "progress",
                        "message": "Processing the caller's request.",
                        "timestamp": _utc_timestamp(),
                    }
                )
                continue

            if isinstance(event, ServerEventError):
                logger.error("Voice Live session error: %s", event.error.message)
                await _send_error(
                    websocket,
                    "Voice processing could not complete the current turn.",
                    event.error.code or "voice_live_error",
                )


def _parse_client_message(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Call messages must be JSON objects")
    return parsed


async def _send_transcript(
    websocket: WebSocket,
    speaker: str,
    text: str,
    is_final: bool,
) -> None:
    await websocket.send_json(
        {
            "type": "transcript",
            "speaker": speaker,
            "text": text,
            "isFinal": is_final,
            "timestamp": _utc_timestamp(),
        }
    )


async def _send_error(websocket: WebSocket, message: str, code: str) -> None:
    await websocket.send_json({"type": "error", "message": message, "code": code})


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
