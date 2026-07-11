from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from agent_framework import FunctionTool
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

FABRIC_TOKEN_SCOPE = "https://api.fabric.microsoft.com/.default"
PROPERTY_ID_DIRECTIVE = (
    " Always include the exact property_id for every property mentioned in the answer."
)
FabricQueryRunner = Callable[[str, dict[str, str], str], Awaitable[str]]


class FabricDataAgentTool:
    """Queries the published Fabric Data Agent through its MCP endpoint."""

    def __init__(
        self,
        mcp_url: str,
        credential: Any,
        query_runner: FabricQueryRunner | None = None,
    ) -> None:
        self._mcp_url = mcp_url
        self._credential = credential
        self._query_runner = query_runner or _query_data_agent

    def as_function_tool(self) -> FunctionTool:
        return FunctionTool(
            name="query_hotel_operations_data",
            description=(
                "Query governed hotel operations and guest-services data across both Fabric "
                "lakehouses, the semantic model, and the ontology. Every property result includes "
                "its exact property_id for reliable handoff to approved knowledge retrieval."
            ),
            func=self.query,
        )

    async def query(self, question: str) -> str:
        if not question.strip():
            raise ValueError("question must not be empty")
        token = self._credential.get_token(FABRIC_TOKEN_SCOPE)
        headers = {"Authorization": f"Bearer {token.token}"}
        governed_question = f"{question.strip()}{PROPERTY_ID_DIRECTIVE}"
        return await self._query_runner(self._mcp_url, headers, governed_question)


async def _query_data_agent(
    mcp_url: str,
    headers: dict[str, str],
    question: str,
) -> str:
    async with (
        streamablehttp_client(mcp_url, headers=headers, timeout=300) as (
            read,
            write,
            _,
        ),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = (await session.list_tools()).tools
        if len(tools) != 1:
            raise RuntimeError(f"Expected one Fabric Data Agent MCP tool, found {len(tools)}")
        tool = tools[0]
        question_argument = next(iter(tool.inputSchema["properties"]))
        result = await session.call_tool(
            tool.name,
            {question_argument: question},
            read_timeout_seconds=timedelta(seconds=300),
        )
        text = "\n".join(block.text for block in result.content if block.type == "text").strip()
        if result.isError:
            raise RuntimeError(f"Fabric Data Agent query failed: {text}")
        if not text:
            raise RuntimeError("Fabric Data Agent returned no text response")
        return text
