from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from hotel_servicing_agent.tools.fabric_data import (
    FABRIC_TOKEN_SCOPE,
    PROPERTY_ID_DIRECTIVE,
    FabricDataAgentTool,
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
    assert captured["question"] == f"Find reservation RES-1{PROPERTY_ID_DIRECTIVE}"


def test_fabric_data_tool_rejects_empty_questions() -> None:
    adapter = FabricDataAgentTool("https://example.test/mcp", object())

    try:
        asyncio.run(adapter.query(" "))
    except ValueError as error:
        assert str(error) == "question must not be empty"
    else:
        raise AssertionError("Expected an empty question to be rejected")
