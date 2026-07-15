from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from agent_framework import FunctionTool
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

FABRIC_TOKEN_SCOPE = "https://api.fabric.microsoft.com/.default"
PROPERTY_CONTEXT_DIRECTIVE = (
    " Always include the exact property_id and official property name for every property "
    "mentioned. "
    "For a chain-wide aggregation, query the complete property roster, return an overall total and "
    "a Markdown table with exactly 20 property rows, and include properties with zero matching "
    "records. Never collapse zero-count rows into an 'all other properties' summary. For a "
    "forward-looking reservation window, interpret reservations as arrivals by check_in with "
    "status future or arriving unless the user explicitly asks for records created or booked "
    "during the window; state the date range and interpretation used. For an exact reservation, "
    "folio, dispute, request, or work-order identifier, search the full record history and do not "
    "apply a date window unless the user explicitly requests one."
)
RELATIVE_DATE_PATTERN = re.compile(
    r"\b(today|tomorrow|yesterday|next week|this week|last week|next \d+ days?|upcoming)\b",
    re.IGNORECASE,
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
                "lakehouses, the semantic model, and the ontology. Property results include the "
                "official property name and exact property_id; chain-wide results include a "
                "complete property breakdown."
            ),
            func=self.query,
        )

    async def query(self, question: str) -> str:
        if not question.strip():
            raise ValueError("question must not be empty")
        token = self._credential.get_token(FABRIC_TOKEN_SCOPE)
        headers = {"Authorization": f"Bearer {token.token}"}
        governed_question = _governed_question(question)
        return await self._query_runner(self._mcp_url, headers, governed_question)


def _governed_question(question: str, today: date | None = None) -> str:
    governed_question = f"{question.strip()}{PROPERTY_CONTEXT_DIRECTIVE}"
    if not RELATIVE_DATE_PATTERN.search(question):
        return governed_question
    current_date = today or datetime.now(UTC).date()
    next_week_end = current_date + timedelta(days=6)
    return (
        f"{governed_question} Today's authoritative UTC date is "
        f"{current_date.isoformat()}, and a relative next-7-days window ends "
        f"{next_week_end.isoformat()}, inclusive."
    )


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
