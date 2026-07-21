from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import wave
from array import array
from pathlib import Path

from aiohttp import ClientSession, WSMsgType
from azure.identity.aio import DefaultAzureCredential
from hotel_voice_proxy.foundry import build_foundry_websocket_url

_FOUNDRY_SCOPE = "https://ai.azure.com/.default"
_SAMPLE_RATE = 24_000
_SAMPLE_WIDTH = 2


def _read_pcm_wave(path: Path) -> bytes:
    with wave.open(str(path), "rb") as recording:
        if (
            recording.getnchannels() != 1
            or recording.getsampwidth() != 2
            or recording.getframerate() != _SAMPLE_RATE
            or recording.getcomptype() != "NONE"
        ):
            raise ValueError(
                "The smoke test requires an uncompressed, mono, 16-bit, 24 kHz WAV file"
            )
        audio = recording.readframes(recording.getnframes())
    return _trim_edge_silence(audio)


def _trim_edge_silence(
    audio: bytes,
    *,
    threshold: int = 256,
    padding_ms: int = 200,
) -> bytes:
    samples = array("h")
    samples.frombytes(audio)
    if sys.byteorder != "little":
        samples.byteswap()

    first_voiced = next(
        (index for index, sample in enumerate(samples) if abs(sample) >= threshold),
        None,
    )
    if first_voiced is None:
        raise ValueError("The prerecorded prompt contains no audible speech")
    last_voiced = next(
        index
        for index in range(len(samples) - 1, first_voiced - 1, -1)
        if abs(samples[index]) >= threshold
    )
    padding_samples = _SAMPLE_RATE * padding_ms // 1_000
    start = max(0, first_voiced - padding_samples)
    end = min(len(samples), last_voiced + padding_samples + 1)
    trimmed = array("h", samples[start:end])
    if sys.byteorder != "little":
        trimmed.byteswap()
    return trimmed.tobytes()


async def run_smoke(
    *,
    audio_path: Path,
    project_endpoint: str,
    agent_name: str,
    timeout_seconds: float,
    expected_text: str | None,
    expect_activity: bool = False,
    session_id: str | None = None,
) -> dict[str, object]:
    audio = _read_pcm_wave(audio_path)
    session_id = session_id or f"voice-smoke-{os.urandom(8).hex()}"
    credential = DefaultAzureCredential()
    token = await credential.get_token(_FOUNDRY_SCOPE)
    user_transcript = ""
    agent_transcript = ""
    final_user_transcripts: list[str] = []
    final_agent_transcripts: list[str] = []
    output_audio_bytes = 0
    observed_events: dict[str, int] = {}
    timeline_events: list[dict[str, str]] = []
    backend_activity_seen = False
    agent_transcript_after_activity = ""

    try:
        async with (
            ClientSession() as client,
            client.ws_connect(
                build_foundry_websocket_url(project_endpoint, agent_name, session_id),
                headers={"Authorization": f"Bearer {token.token}"},
                heartbeat=30,
                max_msg_size=16 * 1024 * 1024,
            ) as websocket,
        ):
            await websocket.send_json({"type": "session.start", "mode": "prerecorded"})

            try:
                async with asyncio.timeout(timeout_seconds):
                    async for message in websocket:
                        if message.type == WSMsgType.BINARY:
                            output_audio_bytes += len(message.data)
                            continue
                        if message.type != WSMsgType.TEXT:
                            continue
                        event = json.loads(message.data)
                        event_type = str(event.get("type", "unknown"))
                        observed_events[event_type] = observed_events.get(event_type, 0) + 1
                        if event_type == "timeline_event":
                            category = str(event.get("category", ""))
                            timeline_events.append(
                                {
                                    "category": category,
                                    "message": str(event.get("message", "")),
                                }
                            )
                            backend_activity_seen = backend_activity_seen or category in {
                                "tool",
                                "data_source",
                            }
                        if event_type == "auth_ack":
                            for offset in range(0, len(audio), 2_400):
                                chunk = audio[offset : offset + 2_400]
                                await websocket.send_bytes(chunk)
                                await asyncio.sleep(len(chunk) / (_SAMPLE_RATE * _SAMPLE_WIDTH))
                            await websocket.send_json({"type": "audio_commit"})
                        elif event_type == "transcript" and event.get("isFinal"):
                            if event.get("speaker") == "user":
                                user_transcript = str(event.get("text", ""))
                                final_user_transcripts.append(user_transcript)
                            else:
                                agent_transcript = str(event.get("text", ""))
                                final_agent_transcripts.append(agent_transcript)
                                if backend_activity_seen:
                                    agent_transcript_after_activity = agent_transcript
                        elif event_type == "error":
                            raise RuntimeError(
                                f"{event.get('message', 'Voice smoke test failed')} "
                                f"(session={session_id}, code={event.get('code', 'unknown')})"
                            )

                        candidate_transcript = (
                            agent_transcript_after_activity if expect_activity else agent_transcript
                        )
                        expected_received = (
                            expected_text is None
                            or expected_text.casefold() in candidate_transcript.casefold()
                        )
                        if (
                            user_transcript
                            and candidate_transcript
                            and output_audio_bytes
                            and expected_received
                        ):
                            break
            except TimeoutError as exc:
                raise RuntimeError(
                    "Voice smoke test timed out "
                    f"(session={session_id}, events={observed_events}, "
                    f"audioBytes={output_audio_bytes}, "
                    f"finalUserTranscripts={final_user_transcripts}, "
                    f"finalAgentTranscripts={final_agent_transcripts}, "
                    f"timelineEvents={timeline_events})"
                ) from exc
    finally:
        await credential.close()

    final_transcript = agent_transcript_after_activity if expect_activity else agent_transcript
    if not user_transcript:
        raise RuntimeError(
            "Voice Live returned no final user transcript "
            f"(session={session_id}, events={observed_events})"
        )
    if not final_transcript:
        raise RuntimeError(
            "Voice Live returned no final agent transcript "
            f"(session={session_id}, events={observed_events})"
        )
    if output_audio_bytes == 0:
        raise RuntimeError(
            "Voice Live returned no synthesized audio "
            f"(session={session_id}, events={observed_events})"
        )
    if expected_text and expected_text.casefold() not in final_transcript.casefold():
        raise RuntimeError(f"Agent transcript did not contain expected text: {expected_text!r}")

    return {
        "sessionId": session_id,
        "userTranscript": user_transcript,
        "agentTranscript": final_transcript,
        "finalUserTranscripts": final_user_transcripts,
        "finalAgentTranscripts": final_agent_transcripts,
        "outputAudioBytes": output_audio_bytes,
        "observedEvents": observed_events,
        "timelineEvents": timeline_events,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a prerecorded PCM WAV prompt through the hosted Voice Live WebSocket."
    )
    parser.add_argument("audio", type=Path)
    parser.add_argument(
        "--project-endpoint",
        default=os.getenv("FOUNDRY_PROJECT_ENDPOINT"),
    )
    parser.add_argument(
        "--agent-name",
        default=os.getenv("FOUNDRY_AGENT_NAME", "hotel-servicing-agent"),
    )
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--expect")
    parser.add_argument(
        "--expect-activity",
        action="store_true",
        help="Wait for a tool or data-source event and the agent response that follows it.",
    )
    parser.add_argument("--session-id")
    args = parser.parse_args()
    if not args.project_endpoint:
        parser.error("--project-endpoint or FOUNDRY_PROJECT_ENDPOINT is required")

    result = asyncio.run(
        run_smoke(
            audio_path=args.audio,
            project_endpoint=args.project_endpoint,
            agent_name=args.agent_name,
            timeout_seconds=args.timeout,
            expected_text=args.expect,
            expect_activity=args.expect_activity,
            session_id=args.session_id,
        )
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
