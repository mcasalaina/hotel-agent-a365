from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from hotel_servicing_agent.tools.fabric_data import (
    CHAIN_WIDE_PATTERN,
    FABRIC_TOKEN_SCOPE,
    PROPERTY_CONTEXT_DIRECTIVE,
    FabricDataAgentTool,
    _governed_question,
)


@pytest.mark.parametrize(
    "question",
    (
        "Show reservations at all hotels",
        "Show reservations at all properties",
        "Show reservations at all Hotel properties",
        "Show reservations at every hotel",
        "Show reservations at every Hotel property",
        "Show reservations at each hotel",
        "Show reservations at each Hotel property",
        "Show reservations chain-wide",
    ),
)
def test_generic_hotel_chain_wide_queries_are_recognized(question: str) -> None:
    assert CHAIN_WIDE_PATTERN.search(question)


@pytest.mark.parametrize(
    "question",
    (
        "Show every reservation at Hotel Scottsdale Sonoran Resort",
        "Show all reservations at Hotel Paris Left Bank",
    ),
)
def test_named_hotel_queries_are_not_treated_as_chain_wide(question: str) -> None:
    assert CHAIN_WIDE_PATTERN.search(question) is None


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
    assert "first resolve the exact guest_id" in PROPERTY_CONTEXT_DIRECTIVE
    assert "'any reservations' or reservations 'on file'" in PROPERTY_CONTEXT_DIRECTIVE
    assert "all dates and statuses" in PROPERTY_CONTEXT_DIRECTIVE
    assert "only filter to active or upcoming" in PROPERTY_CONTEXT_DIRECTIVE
    assert "always return the exact guest_id" in PROPERTY_CONTEXT_DIRECTIVE
    assert "exact property_id and room_type_id" in PROPERTY_CONTEXT_DIRECTIVE
    assert "exactly 20 rows" in PROPERTY_CONTEXT_DIRECTIVE
    assert "property name and count only" in PROPERTY_CONTEXT_DIRECTIVE
    assert "Never collapse zero-count rows" in PROPERTY_CONTEXT_DIRECTIVE
    assert "status future or arriving" in PROPERTY_CONTEXT_DIRECTIVE
    assert "without narrating this interpretation" in PROPERTY_CONTEXT_DIRECTIVE


def test_fabric_data_tool_rejects_empty_questions() -> None:
    adapter = FabricDataAgentTool("https://example.test/mcp", object())

    try:
        asyncio.run(adapter.query(" "))
    except ValueError as error:
        assert str(error) == "question must not be empty"
    else:
        raise AssertionError("Expected an empty question to be rejected")


def test_chain_wide_query_fans_out_facts_and_roster() -> None:
    captured_questions: list[str] = []

    class FakeCredential:
        def get_token(self, scope: str) -> SimpleNamespace:
            return SimpleNamespace(token="fabric-token")

    async def fake_query_runner(
        url: str,
        headers: dict[str, str],
        question: str,
    ) -> str:
        captured_questions.append(question)
        if "reservation facts only" in question:
            return "HTL-001: 10"
        return "HTL-001: Hotel Seattle Waterfront"

    adapter = FabricDataAgentTool(
        "https://example.test/mcp",
        FakeCredential(),
        query_runner=fake_query_runner,
    )

    answer = asyncio.run(
        adapter.query("Show active reservations at every Hotel property next week")
    )

    assert len(captured_questions) == 2
    assert any("HotelGuestServices reservation facts only" in item for item in captured_questions)
    assert any("HotelOperations properties only" in item for item in captured_questions)
    assert any("Today's authoritative UTC date" in item for item in captured_questions)
    assert "HTL-001: 10" in answer
    assert "Hotel Seattle Waterfront" in answer
    assert "do not show IDs" in answer


def test_governed_question_injects_authoritative_relative_date_window() -> None:
    question = _governed_question("Show next week's arrivals", date(2026, 7, 12))

    assert "Today's authoritative UTC date is 2026-07-12" in question
    assert "next-7-days window ends 2026-07-18, inclusive" in question


def test_governed_exact_id_lookup_does_not_inject_date_window() -> None:
    question = _governed_question("Find reservation RES-DEMO-FAMILY", date(2026, 7, 12))

    assert "search the full record history" in question
    assert "Today's authoritative UTC date" not in question
