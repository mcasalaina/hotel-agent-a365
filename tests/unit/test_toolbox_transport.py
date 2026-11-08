from __future__ import annotations

import asyncio
from contextvars import ContextVar
from types import SimpleNamespace
from typing import Any

import pytest
from agent_framework import FunctionTool
from hotel_servicing_agent.tools.toolbox import FoundryToolboxTransport
from mcp.types import (
    CallToolResult,
    ReadResourceResult,
    ResourceLink,
    TextContent,
    TextResourceContents,
)

PROJECT = "https://target.services.ai.azure.com/api/projects/hotel"
ENDPOINT = f"{PROJECT}/toolboxes/hotel_foundry_toolbox/mcp?api-version=v1"


def _transport(factory: Any) -> FoundryToolboxTransport:
    return FoundryToolboxTransport(
        project_endpoint=PROJECT,
        toolbox_endpoint=ENDPOINT,
        credential=object(),  # type: ignore[arg-type]
        approved_tool_names=("approved-read",),
        toolbox_factory=factory,
    )


def test_toolbox_transport_owns_a_fresh_connection_for_each_caller() -> None:
    caller: ContextVar[str] = ContextVar("caller")
    opened: list[str] = []
    closed: list[str] = []
    arguments_seen: list[dict[str, Any]] = []

    def query(question: str) -> str:
        return question

    class Toolbox:
        def __init__(self, credential: object, **kwargs: Any) -> None:
            assert kwargs["url"] == ENDPOINT
            self.caller = caller.get()
            self.functions = [FunctionTool(name="approved-read", func=query)]
            self.parse_tool_results: Any = None

        async def __aenter__(self) -> Toolbox:
            opened.append(self.caller)
            return self

        async def __aexit__(self, *args: object) -> None:
            closed.append(self.caller)

        async def call_tool(self, name: str, **arguments: Any) -> str:
            assert name == "approved-read"
            arguments_seen.append(arguments)
            return str(
                self.parse_tool_results(
                    CallToolResult(
                        content=[TextContent(type="text", text=self.caller)],
                        structuredContent={"rows": [{"property_id": "HTL-004"}]},
                    )
                )
            )

    async def invoke() -> None:
        transport = _transport(Toolbox)
        for user in ("first-caller", "second-caller"):
            token = caller.set(user)
            try:
                result = await transport.call("approved-read", {"question": "Find my reservation"})
                assert result.content[0].text == user  # type: ignore[union-attr]
                assert result.structuredContent == {"rows": [{"property_id": "HTL-004"}]}
            finally:
                caller.reset(token)

    asyncio.run(invoke())
    assert opened == closed == ["first-caller", "second-caller"]
    assert len(arguments_seen) == 2


def test_toolbox_transport_rejects_unapproved_calls_before_connecting() -> None:
    def must_not_connect(*args: object, **kwargs: object) -> object:
        raise AssertionError("An unapproved call must not open a connection")

    with pytest.raises(ValueError, match="not approved"):
        asyncio.run(_transport(must_not_connect).call("generic-ask-with-actions", {}))


@pytest.mark.parametrize(
    "endpoint",
    [
        ENDPOINT.replace("target.", "old-tenant."),
        ENDPOINT.replace("https://", "http://"),
        ENDPOINT.replace("/api/projects/hotel/", "/api/projects/other/"),
        ENDPOINT.replace("hotel_foundry_toolbox", "other-toolbox"),
        ENDPOINT.replace("api-version=v1", "api-version=unknown"),
        f"{ENDPOINT}#fragment",
    ],
)
def test_toolbox_transport_rejects_unverified_endpoints(endpoint: str) -> None:
    with pytest.raises(ValueError, match="verified HTTPS"):
        FoundryToolboxTransport(
            project_endpoint=PROJECT,
            toolbox_endpoint=endpoint,
            credential=object(),  # type: ignore[arg-type]
            approved_tool_names=("approved-read",),
        )


def test_toolbox_transport_resolves_remote_resources_before_closing() -> None:
    events: list[str] = []

    def query(question: str) -> str:
        return question

    async def read_resource(uri: object) -> ReadResourceResult:
        events.append("read")
        assert str(uri) == "file:///server-owned.csv"
        return ReadResourceResult(
            contents=[
                TextResourceContents(
                    uri=str(uri), mimeType="text/csv", text="reservation_id\nRES-1\n"
                )
            ]
        )

    class Toolbox:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.functions = [FunctionTool(name="approved-read", func=query)]
            self.session = SimpleNamespace(read_resource=read_resource)
            self.parse_tool_results: Any = None

        async def __aenter__(self) -> Toolbox:
            return self

        async def __aexit__(self, *args: object) -> None:
            events.append("close")

        async def call_tool(self, name: str, **kwargs: Any) -> str:
            return str(
                self.parse_tool_results(
                    CallToolResult(
                        content=[
                            ResourceLink(
                                type="resource_link", name="Query", uri="file:///server-owned.csv"
                            )
                        ]
                    )
                )
            )

    result = asyncio.run(
        _transport(Toolbox).call("approved-read", {"question": "Find reservation"})
    )
    assert result.content[0].type == "resource"
    assert events == ["read", "close"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"question": "Find reservation", "wrong": 1}, "Unexpected toolbox arguments"),
        ({}, "Field required"),
    ],
)
def test_toolbox_transport_validates_arguments_before_invocation(
    arguments: dict[str, Any], message: str
) -> None:
    def query(question: str) -> str:
        return question

    class Toolbox:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.functions = [FunctionTool(name="approved-read", func=query)]

        async def __aenter__(self) -> Toolbox:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def call_tool(self, *args: object, **kwargs: object) -> str:
            raise AssertionError("Invalid arguments must not reach tools/call")

    with pytest.raises(ValueError, match=message):
        asyncio.run(_transport(Toolbox).call("approved-read", arguments))


@pytest.mark.parametrize("approved", [(), ("",), ("approved-read", "approved-read")])
def test_toolbox_transport_requires_an_explicit_unique_allowlist(approved: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="allowlist"):
        FoundryToolboxTransport(
            project_endpoint=PROJECT,
            toolbox_endpoint=ENDPOINT,
            credential=object(),  # type: ignore[arg-type]
            approved_tool_names=approved,
        )
