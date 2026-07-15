from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from typing import Any

from hotel_servicing_agent.tools.fabric_data import (
    FABRIC_TOKEN_SCOPE,
    PROPERTY_CONTEXT_DIRECTIVE,
    FabricDataAgentTool,
    _governed_question,
)


def test_fabric_data_tool_queries_published_mcp_endpoint() -> None:
    captured: dict[str, Any] = {}

    class FakeCredential:
        def get_token(self, scope: str) -> SimpleNamespace:
            captured["scope"] = scope
            return SimpleNamespace(token="fabric-token")

    async def fake_query_runner(
        url: str,
        headers: dict[str, str],
        question: str,
    ) -> str:
        captured.update(url=url, headers=headers, question=question)
        return "A governed answer"

    adapter = FabricDataAgentTool(
        "https://api.fabric.microsoft.com/v1/mcp/workspaces/w/dataagents/a/agent",
        FakeCredential(),
        query_runner=fake_query_runner,
    )

    answer = asyncio.run(adapter.query("  Find reservation RES-1  "))
    function_tool = adapter.as_function_tool()

    assert answer == "A governed answer"
    assert function_tool.name == "query_hotel_operations_data"
    assert captured["scope"] == FABRIC_TOKEN_SCOPE
    assert captured["headers"] == {"Authorization": "Bearer fabric-token"}
    assert captured["question"].startswith(f"Find reservation RES-1{PROPERTY_CONTEXT_DIRECTIVE}")
    assert "official property name" in PROPERTY_CONTEXT_DIRECTIVE
    assert "exactly 20 property rows" in PROPERTY_CONTEXT_DIRECTIVE
    assert "Never collapse zero-count rows" in PROPERTY_CONTEXT_DIRECTIVE
    assert "status future or arriving" in PROPERTY_CONTEXT_DIRECTIVE


def test_fabric_data_tool_rejects_empty_questions() -> None:
    adapter = FabricDataAgentTool("https://example.test/mcp", object())

    try:
        asyncio.run(adapter.query(" "))
    except ValueError as error:
        assert str(error) == "question must not be empty"
    else:
        raise AssertionError("Expected an empty question to be rejected")


def test_governed_question_injects_authoritative_relative_date_window() -> None:
    question = _governed_question("Show next week's arrivals", date(2026, 7, 12))

    assert "Today's authoritative UTC date is 2026-07-12" in question
    assert "next-7-days window ends 2026-07-18, inclusive" in question


def test_governed_exact_id_lookup_does_not_inject_date_window() -> None:
    question = _governed_question("Find reservation RES-DEMO-FAMILY", date(2026, 7, 12))

    assert "search the full record history" in question
    assert "Today's authoritative UTC date" not in question
