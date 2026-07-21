from __future__ import annotations

from collections.abc import AsyncIterable, Mapping, Sequence
from contextvars import ContextVar, Token
from typing import Any, cast
from urllib.parse import unquote

from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse, ResponseStreamEvent

_agent_user_id: ContextVar[str | None] = ContextVar("agent_user_id", default=None)
_evaluation_snapshot_id: ContextVar[str | None] = ContextVar(
    "evaluation_snapshot_id",
    default=None,
)
_SNAPSHOT_INSTRUCTION_PREFIX = "ASSERT_EVALUATION_SNAPSHOT_ID:"


def current_agent_user_id() -> str:
    user_id = _agent_user_id.get()
    if not user_id:
        raise RuntimeError("Work IQ requires an authenticated Agent 365 user context")
    return user_id


def current_evaluation_snapshot_id() -> str | None:
    return _evaluation_snapshot_id.get()


def _baggage_value(headers: object, key: str) -> str | None:
    if not isinstance(headers, Mapping):
        return None
    baggage = next(
        (value for name, value in headers.items() if str(name).lower() == "baggage"),
        None,
    )
    if not isinstance(baggage, str):
        return None
    for member in baggage.split(","):
        name, separator, value = member.strip().partition("=")
        if separator and name.strip() == key:
            decoded = unquote(value.split(";", 1)[0].strip())
            return decoded or None
    return None


def _metadata_value(request: object, key: str) -> str | None:
    metadata = getattr(request, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _structured_input_value(request: object, key: str) -> str | None:
    structured_inputs = getattr(request, "structured_inputs", None)
    if not isinstance(structured_inputs, Mapping):
        return None
    value = structured_inputs.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _message_text(content: object) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, Sequence):
        return None
    text_parts: list[str] = []
    for part in content:
        part_type = part.get("type") if isinstance(part, Mapping) else getattr(part, "type", None)
        text = part.get("text") if isinstance(part, Mapping) else getattr(part, "text", None)
        if part_type == "input_text" and isinstance(text, str):
            text_parts.append(text)
    return "\n".join(text_parts) if text_parts else None


def _extract_snapshot_marker(request: object) -> str | None:
    response_input = getattr(request, "input", None)
    if not isinstance(response_input, list):
        return None
    filtered: list[object] = []
    snapshot_id: str | None = None
    for item in response_input:
        role = item.get("role") if isinstance(item, Mapping) else getattr(item, "role", None)
        raw_content = (
            item.get("content") if isinstance(item, Mapping) else getattr(item, "content", None)
        )
        content = _message_text(raw_content)
        if role != "developer" or content is None:
            filtered.append(item)
            continue
        value = content.removeprefix(_SNAPSHOT_INSTRUCTION_PREFIX).strip()
        if (
            content.startswith(_SNAPSHOT_INSTRUCTION_PREFIX)
            and value
            and all(character.isalnum() or character in "_-" for character in value)
            and snapshot_id is None
        ):
            snapshot_id = value
            continue
        filtered.append(item)
    if snapshot_id is not None:
        cast(Any, request).input = filtered
    return snapshot_id


class Agent365ResponsesHostServer(ResponsesHostServer):  # type: ignore[misc]
    """Makes Foundry's per-user context available to Agent 365 function tools."""

    async def _handle_inner_agent(
        self,
        request: CreateResponse,
        context: ResponseContext,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        user_token: Token[str | None] = _agent_user_id.set(context.platform_context.user_id_key)
        snapshot_token: Token[str | None] = _evaluation_snapshot_id.set(
            _baggage_value(context.client_headers, "assert.snapshot_id")
            or _structured_input_value(request, "assert_snapshot_id")
            or _metadata_value(request, "assert_snapshot_id")
            or _extract_snapshot_marker(request)
        )
        try:
            async for event in super()._handle_inner_agent(request, context):
                yield event
        finally:
            _evaluation_snapshot_id.reset(snapshot_token)
            _agent_user_id.reset(user_token)
