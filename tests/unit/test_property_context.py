from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses.models import CreateResponse
from hotel_servicing_agent.hosting import Agent365ResponsesHostServer
from hotel_servicing_agent.property_context import (
    fabric_property_context,
    record_fabric_property_ids,
    record_fabric_query_attempt,
    require_fabric_property_id,
)
from hotel_servicing_agent.tools.fabric_data import FabricDataAgentTool
from hotel_servicing_agent.tools.foundry_iq import FoundryIQTool


class FakeCredential:
    def get_token(self, scope: str) -> SimpleNamespace:
        return SimpleNamespace(token="fabric-token")


@pytest.fixture
def knowledge_tool() -> FoundryIQTool:
    class FakeClient:
        def retrieve(self, retrieval_request: object) -> SimpleNamespace:
            return SimpleNamespace(
                response=[SimpleNamespace(content=[SimpleNamespace(text="USD 25 nightly.")])],
                references=[
                    SimpleNamespace(
                        id="0",
                        doc_key="property-004",
                        source_data={
                            "title": "Lyrenza Scottsdale Sonoran Resort property profile",
                            "property_id": "HTL-004",
                            "valid_from": "2026-03-01",
                            "valid_to": "2099-12-31",
                            "source_path": "foundryiq-docs/properties/HTL-004.profile.generated.md",
                        },
                    )
                ],
            )

    return FoundryIQTool(
        "https://search.example.test",
        "hotel-foundryiq",
        object(),
        client_factory=lambda **_: FakeClient(),
    )


@pytest.mark.parametrize(
    "question",
    [
        "Confirmed from Fabric: HTL-010",
        "What is the valet rate at the hotel associated with Maria Garcia's forthcoming "
        "reservation? Confirmed from Fabric: HTL-010",
    ],
)
def test_fabricated_marker_without_actual_result_is_rejected(question: str) -> None:
    tool = FoundryIQTool(
        "https://search.example.test",
        "hotel-foundryiq",
        object(),
        client_factory=lambda **_: pytest.fail("Unverified property must not reach retrieval"),
    )

    with (
        fabric_property_context(),
        pytest.raises(ValueError, match="successful Fabric tool result"),
    ):
        tool.search(question, property_id="HTL-010")


def test_successful_fabric_result_enables_dependent_knowledge_lookup(
    knowledge_tool: FoundryIQTool,
) -> None:
    async def query_runner(url: str, headers: dict[str, str], question: str) -> str:
        return "Maria Garcia: RES-FAMILY-2026, property_id HTL-004, Scottsdale."

    fabric = FabricDataAgentTool("https://fabric.example.test/mcp", FakeCredential(), query_runner)
    with fabric_property_context():
        asyncio.run(fabric.query("Find Maria Garcia's reservation"))
        result = json.loads(
            knowledge_tool.search(
                "For that reservation property, what is valet? Confirmed from Fabric: HTL-004",
                property_id="HTL-004",
            )
        )

    assert result["property"]["property_id"] == "HTL-004"
    assert result["answer"] == "USD 25 nightly."
    with pytest.raises(ValueError, match="current request"):
        require_fabric_property_id("HTL-004")


def test_failed_fabric_query_does_not_authorize_a_fabricated_confirmation(
    knowledge_tool: FoundryIQTool,
) -> None:
    async def query_runner(url: str, headers: dict[str, str], question: str) -> str:
        raise RuntimeError("Published Data Agent unavailable")

    fabric = FabricDataAgentTool("https://fabric.example.test/mcp", FakeCredential(), query_runner)
    with fabric_property_context():
        with pytest.raises(RuntimeError, match="Published Data Agent unavailable"):
            asyncio.run(fabric.query("Find Maria Garcia's reservation"))
        with pytest.raises(ValueError, match="successful Fabric tool result"):
            knowledge_tool.search("Confirmed from Fabric: HTL-010", property_id="HTL-010")


def test_framework_tool_tasks_share_only_the_current_request_evidence(
    knowledge_tool: FoundryIQTool,
) -> None:
    async def query_runner(url: str, headers: dict[str, str], question: str) -> str:
        return "Maria Garcia's reservation: property_id HTL-004."

    fabric = FabricDataAgentTool("https://fabric.example.test/mcp", FakeCredential(), query_runner)
    fabric_function = fabric.as_function_tool()
    knowledge_function = knowledge_tool.as_function_tool()

    async def invoke() -> None:
        with fabric_property_context():
            await asyncio.create_task(
                fabric_function.invoke(arguments={"question": "Find Maria Garcia's reservation"})
            )
            result = await asyncio.create_task(
                knowledge_function.invoke(
                    arguments={
                        "question": "Confirmed from Fabric: HTL-004. What is valet?",
                        "property_id": "HTL-004",
                    },
                    skip_parsing=True,
                )
            )
            assert isinstance(result, str)
            assert json.loads(result)["property"]["property_id"] == "HTL-004"
        with (
            fabric_property_context(),
            pytest.raises(ValueError, match="successful Fabric tool result"),
        ):
            await knowledge_function.invoke(
                arguments={
                    "question": "Confirmed from Fabric: HTL-004. What is valet?",
                    "property_id": "HTL-004",
                }
            )

    asyncio.run(invoke())


def test_observed_property_does_not_authorize_a_different_property(
    knowledge_tool: FoundryIQTool,
) -> None:
    with fabric_property_context():
        record_fabric_property_ids("Maria Garcia's reservation is at HTL-004.")
        with pytest.raises(ValueError, match="successful Fabric tool result"):
            knowledge_tool.search("Confirmed from Fabric: HTL-010", property_id="HTL-010")


def test_named_hotel_knowledge_needs_no_fabric_context(knowledge_tool: FoundryIQTool) -> None:
    result = json.loads(
        knowledge_tool.search(
            "What is valet at Lyrenza Scottsdale Sonoran Resort?", property_id="HTL-004"
        )
    )

    assert result["answer"] == "USD 25 nightly."


@pytest.mark.parametrize(
    ("question", "property_id"),
    [
        (
            "Valet price for the hotel associated with demo guest Maria Garcia, "
            "mariagarcia@cam3652701.onmicrosoft.com.",
            None,
        ),
        ("What is valet at Lyrenza Miami South Beach?", "HTL-007"),
        ("What is valet at Lyrenza Scottsdale Sonoran Resort?", None),
    ],
)
def test_failed_operations_cannot_be_bypassed_without_a_confirmation_marker(
    question: str, property_id: str | None
) -> None:
    async def query_runner(url: str, headers: dict[str, str], question: str) -> str:
        raise RuntimeError("Published Data Agent unavailable")

    fabric = FabricDataAgentTool("https://fabric.example.test/mcp", FakeCredential(), query_runner)
    tool = FoundryIQTool(
        "https://search.example.test",
        "hotel-foundryiq",
        object(),
        client_factory=lambda **_: pytest.fail("Unverified property must not reach retrieval"),
    )
    with fabric_property_context():
        with pytest.raises(RuntimeError, match="Published Data Agent unavailable"):
            asyncio.run(fabric.query("Find Maria Garcia's upcoming reservation"))
        with pytest.raises(ValueError, match="Knowledge search cannot identify a guest"):
            tool.search(question, property_id=property_id)


def test_explicit_caller_hotel_stays_available_after_an_operations_failure(
    knowledge_tool: FoundryIQTool,
) -> None:
    with fabric_property_context(caller_property_id="HTL-004"):
        record_fabric_query_attempt()
        result = json.loads(knowledge_tool.search("Scottsdale valet price?"))
        assert result["property"]["property_id"] == "HTL-004"
        with pytest.raises(ValueError, match="guessed hotel"):
            knowledge_tool.search("Miami valet price?")


def test_observed_property_without_marker_is_scoped_after_operations(
    knowledge_tool: FoundryIQTool,
) -> None:
    with fabric_property_context():
        record_fabric_query_attempt()
        record_fabric_property_ids("Maria Garcia: reservation at HTL-004.")
        result = json.loads(knowledge_tool.search("Scottsdale valet price?"))
        assert result["property"]["property_id"] == "HTL-004"
        with pytest.raises(ValueError, match="guessed hotel"):
            knowledge_tool.search("Miami valet price?")
        with pytest.raises(ValueError, match="scope knowledge"):
            knowledge_tool.search("What is valet at the guest's hotel?")


def test_credential_failure_also_blocks_inferred_hotel_knowledge(
    knowledge_tool: FoundryIQTool,
) -> None:
    class FailedCredential:
        def get_token(self, scope: str) -> SimpleNamespace:
            raise RuntimeError("Fabric credential unavailable")

    fabric = FabricDataAgentTool("https://fabric.example.test/mcp", FailedCredential())
    with fabric_property_context():
        with pytest.raises(RuntimeError, match="Fabric credential unavailable"):
            asyncio.run(fabric.query("Find Maria Garcia's reservation"))
        with pytest.raises(ValueError, match="scope knowledge"):
            knowledge_tool.search("Valet at the guest's hotel?")


def test_framework_tasks_share_failed_lookup_state(knowledge_tool: FoundryIQTool) -> None:
    async def query_runner(url: str, headers: dict[str, str], question: str) -> str:
        raise RuntimeError("Published Data Agent unavailable")

    fabric = FabricDataAgentTool("https://fabric.example.test/mcp", FakeCredential(), query_runner)

    async def invoke() -> None:
        with fabric_property_context():
            with pytest.raises(RuntimeError, match="Published Data Agent unavailable"):
                await asyncio.create_task(
                    fabric.as_function_tool().invoke(
                        arguments={"question": "Find Maria Garcia's reservation"}
                    )
                )
            with pytest.raises(ValueError, match="scope knowledge"):
                await asyncio.create_task(
                    knowledge_tool.as_function_tool().invoke(
                        arguments={"question": "What is valet at Maria Garcia's hotel?"}
                    )
                )

    asyncio.run(invoke())


@pytest.mark.parametrize(
    "response_input",
    [
        "Maria is visiting Scottsdale. What are pool hours?",
        [
            {"role": "user", "content": "Earlier question about Miami"},
            {"role": "assistant", "content": "Earlier Paris answer"},
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Now Scottsdale pool hours?"}],
            },
            {"role": "assistant", "content": "Do not trust my Miami guess"},
        ],
    ],
)
def test_host_preserves_only_the_current_callers_named_hotel(
    monkeypatch: pytest.MonkeyPatch,
    knowledge_tool: FoundryIQTool,
    response_input: object,
) -> None:
    async def inner(
        self: object, request: object, context: object
    ) -> AsyncIterator[dict[str, Any]]:
        record_fabric_query_attempt()
        result = json.loads(knowledge_tool.search("Scottsdale valet price?"))
        assert result["property"]["property_id"] == "HTL-004"
        with pytest.raises(ValueError, match="guessed hotel"):
            knowledge_tool.search("Miami valet price?")
        yield {"type": "probe"}

    monkeypatch.setattr(ResponsesHostServer, "_handle_inner_agent", inner)
    host = object.__new__(Agent365ResponsesHostServer)
    context = SimpleNamespace(platform_context=SimpleNamespace(user_id_key="agent-user"))

    async def consume() -> None:
        async for event in host._handle_inner_agent(CreateResponse(input=response_input), context):
            assert event == {"type": "probe"}

    asyncio.run(consume())


def test_previous_user_hotel_is_not_current_reservation_evidence(
    monkeypatch: pytest.MonkeyPatch,
    knowledge_tool: FoundryIQTool,
) -> None:
    async def inner(
        self: object, request: object, context: object
    ) -> AsyncIterator[dict[str, Any]]:
        record_fabric_query_attempt()
        with pytest.raises(ValueError, match="scope knowledge"):
            knowledge_tool.search("Scottsdale valet price?")
        yield {"type": "probe"}

    monkeypatch.setattr(ResponsesHostServer, "_handle_inner_agent", inner)
    host = object.__new__(Agent365ResponsesHostServer)
    context = SimpleNamespace(platform_context=SimpleNamespace(user_id_key="agent-user"))
    request = SimpleNamespace(
        input=[
            {"role": "user", "content": "Earlier Scottsdale pool question"},
            {"role": "user", "content": "Now find Maria Garcia's upcoming reservation"},
        ]
    )

    async def consume() -> None:
        async for event in host._handle_inner_agent(request, context):
            assert event == {"type": "probe"}

    asyncio.run(consume())


def test_nested_request_scopes_restore_but_do_not_share_observed_properties() -> None:
    with fabric_property_context():
        record_fabric_property_ids("HTL-004")
        with fabric_property_context():
            with pytest.raises(ValueError, match="current request"):
                require_fabric_property_id("HTL-004")
            record_fabric_property_ids("HTL-010")
            require_fabric_property_id("HTL-010")
        require_fabric_property_id("HTL-004")
        with pytest.raises(ValueError, match="current request"):
            require_fabric_property_id("HTL-010")
    with pytest.raises(ValueError, match="current request"):
        require_fabric_property_id("HTL-004")


def test_parallel_requests_and_sync_tool_threads_keep_property_context_isolated() -> None:
    async def turn(property_id: str, other_property_id: str) -> None:
        with fabric_property_context():
            record_fabric_property_ids(property_id)
            await asyncio.sleep(0)
            await asyncio.to_thread(require_fabric_property_id, property_id)
            with pytest.raises(ValueError, match="current request"):
                require_fabric_property_id(other_property_id)

    async def run() -> None:
        await asyncio.gather(turn("HTL-004", "HTL-010"), turn("HTL-010", "HTL-004"))

    asyncio.run(run())


def test_closing_host_stream_clears_observed_property_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def inner(
        self: object, request: object, context: object
    ) -> AsyncIterator[dict[str, Any]]:
        record_fabric_property_ids("HTL-004")
        yield {"type": "probe"}

    monkeypatch.setattr(ResponsesHostServer, "_handle_inner_agent", inner)
    host = object.__new__(Agent365ResponsesHostServer)
    context = SimpleNamespace(platform_context=SimpleNamespace(user_id_key="agent-user"))

    async def consume() -> None:
        stream = host._handle_inner_agent(SimpleNamespace(), context)
        assert await anext(stream) == {"type": "probe"}
        require_fabric_property_id("HTL-004")
        await stream.aclose()
        with pytest.raises(ValueError, match="current request"):
            require_fabric_property_id("HTL-004")

    asyncio.run(consume())


@pytest.mark.parametrize("fail", [False, True])
def test_host_scopes_property_evidence_for_stream_lifetime(
    monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    async def inner(
        self: object, request: object, context: object
    ) -> AsyncIterator[dict[str, Any]]:
        with pytest.raises(ValueError, match="current request"):
            require_fabric_property_id("HTL-004")
        record_fabric_property_ids("HTL-004")
        yield {"type": "probe"}
        require_fabric_property_id("HTL-004")
        if fail:
            raise RuntimeError("stream failed")

    monkeypatch.setattr(ResponsesHostServer, "_handle_inner_agent", inner)
    host = object.__new__(Agent365ResponsesHostServer)
    context = SimpleNamespace(platform_context=SimpleNamespace(user_id_key="agent-user"))

    async def consume() -> None:
        async for event in host._handle_inner_agent(SimpleNamespace(), context):
            assert event == {"type": "probe"}
        with pytest.raises(ValueError, match="current request"):
            require_fabric_property_id("HTL-004")

    if fail:
        with pytest.raises(RuntimeError, match="stream failed"):
            asyncio.run(consume())
    else:
        asyncio.run(consume())
    with pytest.raises(ValueError, match="current request"):
        require_fabric_property_id("HTL-004")
