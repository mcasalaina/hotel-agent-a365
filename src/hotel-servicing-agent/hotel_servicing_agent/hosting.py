from __future__ import annotations

from collections.abc import AsyncIterable
from contextvars import ContextVar, Token
from typing import Any

from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse, ResponseStreamEvent

_agent_user_id: ContextVar[str | None] = ContextVar("agent_user_id", default=None)


def current_agent_user_id() -> str:
    user_id = _agent_user_id.get()
    if not user_id:
        raise RuntimeError("Work IQ requires an authenticated Agent 365 user context")
    return user_id


class Agent365ResponsesHostServer(ResponsesHostServer):  # type: ignore[misc]
    """Makes Foundry's per-user context available to Agent 365 function tools."""

    async def _handle_inner_agent(
        self,
        request: CreateResponse,
        context: ResponseContext,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        token: Token[str | None] = _agent_user_id.set(context.platform_context.user_id_key)
        try:
            async for event in super()._handle_inner_agent(request, context):
                yield event
        finally:
            _agent_user_id.reset(token)
