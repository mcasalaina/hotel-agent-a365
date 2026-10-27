from __future__ import annotations

from collections.abc import AsyncIterable, Mapping
from contextvars import ContextVar, Token
from typing import Any

from agent_framework import Agent
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from azure.ai.agentserver.responses import ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse, ResponseStreamEvent
from azure.core.credentials_async import AsyncTokenCredential

from hotel_servicing_agent.config import Settings
from hotel_servicing_agent.property_catalog import property_id_from_text
from hotel_servicing_agent.property_context import fabric_property_context
from hotel_servicing_agent.voice_live import VoiceLiveBridge

_agent_user_id: ContextVar[str | None] = ContextVar("agent_user_id", default=None)


def current_agent_user_id() -> str:
    user_id = _agent_user_id.get()
    if not user_id:
        raise RuntimeError("Work IQ requires an authenticated Agent 365 user context")
    return user_id


def _latest_user_text(response_input: object) -> str:
    if isinstance(response_input, str):
        return response_input
    if not isinstance(response_input, list):
        return ""
    for item in reversed(response_input):
        if not isinstance(item, Mapping) or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for part in content:
                if isinstance(part, Mapping):
                    text = part.get("text")
                    if isinstance(text, str):
                        texts.append(text)
            return "\n".join(texts)
    return ""


class Agent365ResponsesHostServer(ResponsesHostServer):  # type: ignore[misc]
    """Makes Foundry's per-user context available to Agent 365 function tools."""

    async def _handle_inner_agent(
        self,
        request: CreateResponse,
        context: ResponseContext,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        token: Token[str | None] = _agent_user_id.set(context.platform_context.user_id_key)
        try:
            caller_property_id = property_id_from_text(
                _latest_user_text(getattr(request, "input", None))
            )
            with fabric_property_context(caller_property_id):
                async for event in super()._handle_inner_agent(request, context):
                    yield event
        finally:
            _agent_user_id.reset(token)


class VoiceLiveAgentHost(InvocationAgentServerHost, Agent365ResponsesHostServer):
    """Hosts Responses and duplex Voice Live traffic in one Foundry container."""

    def __init__(
        self,
        agent: Agent,
        settings: Settings,
        voice_credential: AsyncTokenCredential,
    ) -> None:
        super().__init__(agent=agent)
        self._voice_bridge = VoiceLiveBridge(settings, voice_credential)
        self.ws_handler(self._voice_bridge.handle)
