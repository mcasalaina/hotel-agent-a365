from __future__ import annotations

import argparse
import asyncio
import json
import os
import wave
from pathlib import Path

from aiohttp import ClientSession, WSMsgType
from azure.identity.aio import DefaultAzureCredential
from hotel_voice_proxy.foundry import build_foundry_websocket_url

_FOUNDRY_SCOPE = "https://ai.azure.com/.default"


def _read_pcm_wave(path: Path) -> bytes:
    with wave.open(str(path), "rb") as recording:
        if (
            recording.getnchannels() != 1
            or recording.getsampwidth() != 2
            or recording.getframerate() != 24_000
            or recording.getcomptype() != "NONE"
        ):
            raise ValueError(
                "The smoke test requires an uncompressed, mono, 16-bit, 24 kHz WAV file"
            )
        return recording.readframes(recording.getnframes())


async def run_smoke(
    *,
    audio_path: Path,
    project_endpoint: str,
    agent_name: str,
    timeout_seconds: float,
    expected_text: str | None,
) -> dict[str, object]:
    audio = _read_pcm_wave(audio_path)
    session_id = f"voice-smoke-{os.urandom(8).hex()}"
    credential = DefaultAzureCredential()
    token = await credential.get_token(_FOUNDRY_SCOPE)
    user_transcript = ""
    agent_transcript = ""
    output_audio_bytes = 0

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

            async with asyncio.timeout(timeout_seconds):
                async for message in websocket:
                    if message.type == WSMsgType.BINARY:
                        output_audio_bytes += len(message.data)
                        continue
                    if message.type != WSMsgType.TEXT:
                        continue
                    event = json.loads(message.data)
                    if event.get("type") == "auth_ack":
                        for offset in range(0, len(audio), 2_400):
                            await websocket.send_bytes(audio[offset : offset + 2_400])
                        await websocket.send_json({"type": "audio_commit"})
                    elif event.get("type") == "transcript" and event.get("isFinal"):
                        if event.get("speaker") == "user":
                            user_transcript = str(event.get("text", ""))
                        else:
                            agent_transcript = str(event.get("text", ""))
                    elif event.get("type") == "error":
                        raise RuntimeError(str(event.get("message", "Voice smoke test failed")))

                    if user_transcript and agent_transcript and output_audio_bytes:
                        break
    finally:
        await credential.close()

    if not user_transcript:
        raise RuntimeError("Voice Live returned no final user transcript")
    if not agent_transcript:
        raise RuntimeError("Voice Live returned no final agent transcript")
    if output_audio_bytes == 0:
        raise RuntimeError("Voice Live returned no synthesized audio")
    if expected_text and expected_text.casefold() not in agent_transcript.casefold():
        raise RuntimeError(f"Agent transcript did not contain expected text: {expected_text!r}")

    return {
        "sessionId": session_id,
        "userTranscript": user_transcript,
        "agentTranscript": agent_transcript,
        "outputAudioBytes": output_audio_bytes,
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
        )
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
