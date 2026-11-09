from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import parse_qs, urlsplit

from agent_framework_foundry_hosting import FoundryToolbox
from azure.core.credentials import TokenCredential
from jsonschema import ValidationError, validate
from mcp.types import CallToolResult, ContentBlock, EmbeddedResource


class FoundryToolboxTransport:
    """Request-owned toolbox transport beneath the hotel's governed function tools."""

    def __init__(
        self,
        *,
        project_endpoint: str,
        toolbox_endpoint: str,
        credential: TokenCredential,
        approved_tool_names: tuple[str, ...],
        toolbox_factory: Callable[..., Any] = FoundryToolbox,
    ) -> None:
        _validate_endpoint(project_endpoint, toolbox_endpoint)
        if not approved_tool_names or any(not name.strip() for name in approved_tool_names):
            raise ValueError("The toolbox requires an explicit nonempty tool allowlist")
        if len(approved_tool_names) != len(set(approved_tool_names)):
            raise ValueError("The toolbox allowlist contains duplicate tool names")
        self._endpoint = toolbox_endpoint
        self._credential = credential
        self._approved_tool_names = frozenset(approved_tool_names)
        self._toolbox_factory = toolbox_factory

    async def verify_tools(self) -> dict[str, dict[str, Any]]:
        """Require every approved binding to exist before activating the hosted runtime."""
        async with self._toolbox_factory(
            self._credential,
            url=self._endpoint,
            name="hotel_foundry_toolbox",
            timeout=300,
        ) as toolbox:
            schemas: dict[str, dict[str, Any]] = {}
            for function in toolbox.functions:
                if function.name not in self._approved_tool_names:
                    continue
                if function.name in schemas:
                    raise RuntimeError(f"Duplicate published toolbox tool: {function.name}")
                schemas[function.name] = function.parameters()
            missing = self._approved_tool_names - schemas.keys()
            if missing:
                raise RuntimeError(f"Missing published toolbox tools: {sorted(missing)}")
            return schemas

    async def call(self, tool_name: str, arguments: Mapping[str, Any]) -> CallToolResult:
        if tool_name not in self._approved_tool_names:
            raise ValueError(f"Toolbox tool is not approved for this operation: {tool_name}")
        # The pinned hosting SDK binds platform headers when its MCP session opens.
        # A new connection per operation prevents reuse of another caller's context.
        async with self._toolbox_factory(
            self._credential,
            url=self._endpoint,
            name="hotel_foundry_toolbox",
            timeout=300,
        ) as toolbox:
            functions = [function for function in toolbox.functions if function.name == tool_name]
            if len(functions) != 1:
                raise RuntimeError(f"Expected exactly one published toolbox tool: {tool_name}")
            function = functions[0]
            schema = function.parameters()
            unknown = set(arguments) - set(schema.get("properties", {}))
            if unknown:
                raise ValueError(f"Unexpected toolbox arguments for {tool_name}: {sorted(unknown)}")
            try:
                validate(dict(arguments), schema)
            except ValidationError as exc:
                raise ValueError(
                    f"Invalid toolbox arguments for {tool_name}: {exc.validator}"
                ) from None
            toolbox.parse_tool_results = lambda result: result.model_dump_json(by_alias=True)
            raw = await toolbox.call_tool(tool_name, **arguments)
            if not isinstance(raw, str):
                raise RuntimeError("The toolbox did not return its complete MCP result")
            result = CallToolResult.model_validate_json(raw)
            if result.isError:
                raise RuntimeError(f"Toolbox call failed: {tool_name}")
            content: list[ContentBlock] = []
            for block in result.content:
                if block.type == "resource_link":
                    linked = await toolbox.session.read_resource(block.uri)
                    if not linked.contents:
                        raise RuntimeError(f"Toolbox resource returned no content: {block.uri}")
                    content.extend(
                        EmbeddedResource(type="resource", resource=resource)
                        for resource in linked.contents
                    )
                else:
                    content.append(block)
            if not content and not result.structuredContent:
                raise RuntimeError(f"Toolbox tool returned no evidence: {tool_name}")
            return result.model_copy(update={"content": content})


def _validate_endpoint(project_endpoint: str, toolbox_endpoint: str) -> None:
    project = urlsplit(project_endpoint)
    toolbox = urlsplit(toolbox_endpoint)
    path_prefix = f"{project.path.rstrip('/')}/toolboxes/hotel_foundry_toolbox"
    suffix = toolbox.path.removeprefix(path_prefix)
    valid_path = toolbox.path.startswith(path_prefix) and (
        suffix == "/mcp"
        or (
            suffix.startswith("/versions/")
            and suffix.endswith("/mcp")
            and len(suffix.split("/")) == 4
            and bool(suffix.split("/")[2])
        )
    )
    if (
        project.scheme != "https"
        or not project.hostname
        or toolbox.scheme != "https"
        or toolbox.netloc != project.netloc
        or toolbox.username is not None
        or toolbox.password is not None
        or toolbox.fragment
        or not valid_path
        or parse_qs(toolbox.query).get("api-version") != ["v1"]
    ):
        raise ValueError("The toolbox endpoint must belong to the verified HTTPS Foundry project")
