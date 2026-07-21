from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from openai import AsyncOpenAI
from openai.types.responses import ResponseInputParam

from hotel_assert.constants import MAX_APPROVAL_ROUNDS


class FoundryInvocationError(RuntimeError):
    """Raised when the Hosted Agent cannot return a usable response."""


_ROLES = {"user", "assistant", "system", "developer"}


def _response_history(history: Sequence[dict[str, str]]) -> ResponseInputParam:
    result: ResponseInputParam = []
    for item in history:
        role = item.get("role")
        if role not in _ROLES:
            raise ValueError(f"Unsupported response history role: {role}")
        result.append(
            {
                "role": cast(Literal["user", "assistant", "system", "developer"], role),
                "content": item.get("content", ""),
            }
        )
    return result


def _snapshot_marker(metadata: dict[str, str] | None) -> dict[str, str] | None:
    if not metadata:
        return None
    snapshot_id = metadata.get("assert_snapshot_id", "").strip()
    if not snapshot_id:
        return None
    return {
        "role": "developer",
        "content": f"ASSERT_EVALUATION_SNAPSHOT_ID:{snapshot_id}",
    }


def _with_snapshot_marker(
    response_input: Sequence[Any],
    metadata: dict[str, str] | None,
) -> list[Any]:
    marker = _snapshot_marker(metadata)
    return ([marker] if marker else []) + list(response_input)


@dataclass(frozen=True)
class FoundryTargetConfig:
    endpoint: str
    agent_name: str
    model: str
    api_version: str

    @property
    def base_url(self) -> str:
        return f"{self.endpoint.rstrip('/')}/agents/{self.agent_name}/endpoint/protocols/openai"


def assistant_text(response: Any) -> str:
    for item in response.output:
        if getattr(item, "type", None) != "message" or getattr(item, "role", None) != "assistant":
            continue
        text = [
            content.text
            for content in item.content
            if getattr(content, "type", None) == "output_text"
        ]
        if text:
            return "\n".join(text)
    return ""


async def _complete_approvals(
    client: AsyncOpenAI,
    *,
    model: str,
    history: Sequence[dict[str, str]],
    response: Any,
    headers: dict[str, str],
    metadata: dict[str, str] | None,
) -> Any:
    for _ in range(MAX_APPROVAL_ROUNDS):
        approvals = [
            item
            for item in response.output
            if getattr(item, "type", None) == "mcp_approval_request"
        ]
        if not approvals:
            return response
        approval_input = list(response.output)
        approval_input.extend(
            {
                "type": "mcp_approval_response",
                "approve": True,
                "approval_request_id": item.id,
            }
            for item in approvals
        )
        response = await client.responses.create(
            model=model,
            input=_with_snapshot_marker(list(history) + approval_input, metadata),
            extra_headers=headers,
            metadata=metadata,
            extra_body={"structured_inputs": metadata} if metadata else None,
        )
    raise FoundryInvocationError("Hosted Agent exceeded the MCP approval limit")


async def invoke_hosted_agent(
    *,
    config: FoundryTargetConfig,
    token: str,
    history: Sequence[dict[str, str]],
    traceparent: str,
    baggage: str,
    metadata: dict[str, str] | None = None,
) -> tuple[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "traceparent": traceparent,
        "baggage": baggage,
    }
    client = AsyncOpenAI(
        api_key="unused",
        base_url=config.base_url,
        default_query={"api-version": config.api_version},
        default_headers=headers,
        max_retries=2,
    )
    try:
        response = await client.responses.create(
            model=config.model,
            input=_with_snapshot_marker(_response_history(history), metadata),
            extra_headers=headers,
            metadata=metadata,
            extra_body={"structured_inputs": metadata} if metadata else None,
        )
        response = await _complete_approvals(
            client,
            model=config.model,
            history=history,
            response=response,
            headers=headers,
            metadata=metadata,
        )
    finally:
        await client.close()
    text = assistant_text(response)
    if not text:
        raise FoundryInvocationError("Hosted Agent returned no assistant text")
    return text, str(response.id)
