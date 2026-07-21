from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from agent_framework import FunctionTool
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

FABRIC_TOKEN_SCOPE = "https://api.fabric.microsoft.com/.default"
PROPERTY_CONTEXT_DIRECTIVE = (
    " Always include the exact internal property_id with the official property name in this tool "
    "response. The identifier is required for tool coordination but must not be recommended for "
    "display to the user. For a named guest reservation lookup, first resolve the exact guest_id "
    "from the guest's first and last name, then join reservations on that guest_id. A request for "
    "'any reservations' or reservations 'on file' means all dates and statuses, including "
    "completed and cancelled; only filter to active or upcoming reservations when the question "
    "explicitly asks for that filter. For a guest lookup, always return the exact guest_id. For a "
    "hotel and room lookup, always return the exact property_id and room_type_id needed by the "
    "write tool, and limit the result to the requested hotel. "
    "For a chain-wide aggregation, query the complete property roster, return an overall total and "
    "a Markdown table with exactly 20 rows using property name and count only, and include "
    "properties with zero matching records. Never collapse zero-count rows into an 'all other "
    "properties' summary. For a "
    "forward-looking reservation window, interpret reservations as arrivals by check_in with "
    "status future or arriving unless the user explicitly asks for records created or booked "
    "during the window. Return the exact date range without narrating this interpretation. For an "
    "exact reservation, "
    "folio, dispute, request, or work-order identifier, search the full record history and do not "
    "apply a date window unless the user explicitly requests one."
)
RELATIVE_DATE_PATTERN = re.compile(
    r"\b(today|tomorrow|yesterday|next week|this week|last week|next \d+ days?|upcoming)\b",
    re.IGNORECASE,
)
CHAIN_WIDE_PATTERN = re.compile(
    r"\b(chain[- ]wide|all (?:lyrenza )?(?:hotels|properties)|"
    r"every (?:lyrenza )?(?:hotel|property)|each (?:lyrenza )?(?:hotel|property))\b",
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
                "sources. Resolve hotels to their official names and return complete chain-wide "
                "breakdowns when requested. For named guests, resolve the exact guest ID before "
                "querying reservations, and search all statuses unless the caller explicitly asks "
                "for active or upcoming records. Internal identifiers are for tool coordination "
                "only and must not be shown to the user."
            ),
            func=self.query,
        )

    async def query(self, question: str) -> str:
        if not question.strip():
            raise ValueError("question must not be empty")
        token = self._credential.get_token(FABRIC_TOKEN_SCOPE)
        headers = {"Authorization": f"Bearer {token.token}"}
        if CHAIN_WIDE_PATTERN.search(question):
            fact_question = (
                f"{question.strip()} Use HotelGuestServices reservation facts only. Do not query "
                "the property roster. For an active forward-looking reservation window, filter "
                "check_in to the requested inclusive date range and status to future or arriving. "
                "Group by property_id and return property_id and count for every nonzero group."
                f"{_authoritative_date_directive(question)}"
            )
            roster_question = (
                "Use HotelOperations properties only. Return the complete Lyrenza roster as "
                "exactly 20 property_id and official property name pairs. Do not query "
                "reservations."
            )
            fact_answer, roster_answer = await asyncio.gather(
                self._query_runner(self._mcp_url, headers, fact_question),
                self._query_runner(self._mcp_url, headers, roster_question),
            )
            return (
                "Reservation counts by internal property key:\n"
                f"{fact_answer}\n\nOfficial hotel roster:\n{roster_answer}\n\n"
                "Join the two results by property_id. In the final answer, show every official "
                "hotel name and its count, use zero for missing count groups, and do not show IDs."
            )
        governed_question = _governed_question(question)
        return await self._query_runner(self._mcp_url, headers, governed_question)


def _governed_question(question: str, today: date | None = None) -> str:
    governed_question = f"{question.strip()}{PROPERTY_CONTEXT_DIRECTIVE}"
    return f"{governed_question}{_authoritative_date_directive(question, today)}"


def _authoritative_date_directive(question: str, today: date | None = None) -> str:
    if not RELATIVE_DATE_PATTERN.search(question):
        return ""
    current_date = today or datetime.now(UTC).date()
    next_week_end = current_date + timedelta(days=6)
    return (
        " Today's authoritative UTC date is "
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
