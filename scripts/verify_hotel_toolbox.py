from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from http.client import HTTPMessage, HTTPResponse
from typing import BinaryIO
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: HTTPResponse,
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> None:
        return None


def object_value(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object")
    return value


def read_rpc_response(stream: BinaryIO, content_type: str, request_id: int) -> dict[str, object]:
    if "text/event-stream" not in content_type:
        message = object_value(json.load(stream), "MCP response")
        if message.get("id") != request_id:
            raise ValueError("MCP response ID does not match the request")
        return message

    data: list[str] = []
    for raw_line in stream:
        line = raw_line.decode("utf-8").rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        elif not line and data:
            message = object_value(json.loads("\n".join(data)), "MCP event")
            data.clear()
            if message.get("id") == request_id:
                return message
    raise ValueError("MCP stream ended without the requested response")


def validate_tools(tools: object, required_prefixes: Sequence[str]) -> list[dict[str, object]]:
    if not isinstance(tools, list) or not tools:
        raise ValueError("Toolbox returned no tools")
    validated = [object_value(tool, "Tool definition") for tool in tools]
    names: list[str] = []
    for tool in validated:
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Tool name is missing")
        if name in names:
            raise ValueError(f"Duplicate tool name: {name}")
        names.append(name)
        schema = object_value(tool.get("inputSchema"), f"{name} input schema")
        object_value(schema.get("properties"), f"{name} input properties")
    for prefix in required_prefixes:
        if not any(name.startswith(f"{prefix}___") for name in names):
            raise ValueError(f"Toolbox has no discovered tools for {prefix}")
    return validated


def web_result_count(result: dict[str, object]) -> int:
    if result.get("isError") is True:
        raise ValueError("Web IQ reported a tool error")
    structured = result.get("structuredContent")
    rows = structured.get("webResults") if isinstance(structured, dict) else None
    if isinstance(rows, list):
        return len(rows)
    content = result.get("content")
    if not isinstance(content, list):
        raise ValueError("Web IQ returned no content blocks")
    decoder = json.JSONDecoder()
    for block in content:
        entry = object_value(block, "Content block")
        text = entry.get("text")
        if not isinstance(text, str) or not text.lstrip().startswith(("{", "[")):
            continue
        position = 0
        while position < len(text):
            while position < len(text) and text[position].isspace():
                position += 1
            if position == len(text):
                break
            value, position = decoder.raw_decode(text, position)
            rows = value.get("webResults") if isinstance(value, dict) else None
            if isinstance(rows, list):
                return len(rows)
    raise ValueError("Web IQ returned no structured web results")


def weather_arguments(tool: dict[str, object]) -> dict[str, object]:
    schema = object_value(tool.get("inputSchema"), "Web IQ input schema")
    properties = object_value(schema.get("properties"), "Web IQ input properties")
    required = schema.get("required")
    if not isinstance(required, list) or "query" not in required:
        raise ValueError("Web IQ input schema must require query")
    types = {
        "query": "string",
        "maxResults": "integer",
        "contentFormat": "string",
        "maxLength": "integer",
        "safeSearch": "string",
    }
    for field, expected in types.items():
        definition = object_value(properties.get(field), f"Web IQ {field} schema")
        if definition.get("type") != expected:
            raise ValueError(f"Web IQ {field} schema must have type {expected}")
    return {
        "query": "Seattle Washington weather forecast today",
        "maxResults": 1,
        "contentFormat": "passage",
        "maxLength": 500,
        "safeSearch": "strict",
    }


class ToolboxClient:
    def __init__(self, endpoint: str, token: str) -> None:
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".services.ai.azure.com")
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or "/toolboxes/" not in parsed.path
            or not parsed.path.endswith("/mcp")
        ):
            raise ValueError("A trusted Foundry toolbox HTTPS endpoint is required")
        self.endpoint = endpoint
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self.opener = build_opener(NoRedirect())
        self.request_id = 0

    def post(self, payload: dict[str, object], request_id: int | None) -> dict[str, object]:
        request = Request(
            self.endpoint, json.dumps(payload).encode("utf-8"), self.headers, method="POST"
        )
        try:
            with self.opener.open(request, timeout=120) as response:
                session_id = response.headers.get("mcp-session-id")
                if session_id:
                    self.headers["Mcp-Session-Id"] = session_id
                if request_id is None:
                    if response.status not in (202, 204):
                        raise ValueError("MCP notification was not accepted")
                    return {}
                message = read_rpc_response(
                    response, response.headers.get("Content-Type", ""), request_id
                )
        except HTTPError as error:
            raise RuntimeError(f"MCP {payload['method']} failed with HTTP {error.code}") from None
        return message

    def rpc(self, method: str, params: dict[str, object]) -> dict[str, object]:
        self.request_id += 1
        message = self.post(
            {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": method,
                "params": params,
            },
            self.request_id,
        )
        if "error" in message:
            error = object_value(message["error"], "MCP error")
            raise RuntimeError(f"MCP {method} failed with code {error.get('code')}")
        return object_value(message.get("result"), f"MCP {method} result")

    def initialize(self) -> None:
        result = self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "hotel-toolbox-verifier", "version": "1.0"},
            },
        )
        version = result.get("protocolVersion")
        if not isinstance(version, str) or not version:
            raise ValueError("MCP initialize returned no protocol version")
        self.headers["MCP-Protocol-Version"] = version
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"}, None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a real four-IQ Foundry toolbox")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--expect-prefix", action="append", required=True)
    parser.add_argument("--web-tool", required=True, help="Actual discovered Web IQ web tool name")
    args = parser.parse_args()
    if len(set(args.expect_prefix)) != 4:
        parser.error("Exactly four distinct IQ namespace prefixes are required")
    executable = shutil.which("az")
    if executable is None:
        raise RuntimeError("Azure CLI is required")
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    credential = subprocess.run(
        [
            executable,
            "account",
            "get-access-token",
            "--subscription",
            args.subscription,
            "--resource",
            "https://ai.azure.com",
            "--query",
            "accessToken",
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )
    if credential.returncode or not credential.stdout.strip():
        raise RuntimeError("A subscription-scoped Azure CLI credential is required")
    client = ToolboxClient(args.endpoint, credential.stdout.strip())
    client.initialize()
    tools = validate_tools(client.rpc("tools/list", {}).get("tools"), args.expect_prefix)
    web_name = args.web_tool
    web_tool = next((tool for tool in tools if tool["name"] == web_name), None)
    if web_tool is None:
        raise ValueError("The exact approved Web IQ tool is not in the toolbox")
    result = client.rpc(
        "tools/call",
        {
            "name": web_name,
            "arguments": weather_arguments(web_tool),
        },
    )
    count = web_result_count(result)
    if count < 1:
        raise ValueError("Web IQ completed but returned no results")
    print(
        json.dumps(
            {
                "endpoint": args.endpoint,
                "tools": [tool["name"] for tool in tools],
                "iqNamespacesVerified": 4,
                "webTool": web_name,
                "webResultCount": count,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
