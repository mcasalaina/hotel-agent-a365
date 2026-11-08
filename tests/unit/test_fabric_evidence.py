from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace

import pytest
from hotel_servicing_agent.tools.fabric_data import _serialize_fabric_result
from mcp.types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ReadResourceResult,
    ResourceLink,
    TextContent,
    TextResourceContents,
)


def test_fabric_evidence_preserves_text_only_behavior() -> None:
    result = CallToolResult(content=[TextContent(type="text", text="Grounded answer")])
    assert asyncio.run(_serialize_fabric_result(result, object())) == "Grounded answer"


@pytest.mark.parametrize("binary", [False, True])
def test_fabric_evidence_preserves_complete_csv_and_structured_results(binary: bool) -> None:
    csv = "reservation_id,property_id,check_in\nRES-1,HTL-004,2026-11-10\n"
    resource = (
        BlobResourceContents(
            uri="file:///query.csv",
            mimeType="text/csv",
            blob=base64.b64encode(csv.encode()).decode(),
        )
        if binary
        else TextResourceContents(uri="file:///query.csv", mimeType="text/csv", text=csv)
    )
    result = CallToolResult(
        content=[
            TextContent(type="text", text="A summary is not the complete record set."),
            EmbeddedResource(type="resource", resource=resource),
        ],
        structuredContent={"rows": [{"reservation_id": "RES-1", "property_id": "HTL-004"}]},
    )

    evidence = json.loads(asyncio.run(_serialize_fabric_result(result, object())))

    assert evidence["resources"] == [
        {"uri": "file:///query.csv", "mime_type": "text/csv", "text": csv}
    ]
    assert evidence["structured_content"] == result.structuredContent


def test_fabric_evidence_resolves_link_through_same_mcp_session() -> None:
    calls: list[str] = []

    async def read_resource(uri: object) -> ReadResourceResult:
        calls.append(str(uri))
        return ReadResourceResult(
            contents=[
                TextResourceContents(
                    uri=str(uri), mimeType="text/csv", text="reservation_id\nRES-1\n"
                )
            ]
        )

    result = CallToolResult(
        content=[
            ResourceLink(type="resource_link", uri="file:///remote-only.csv", name="Query records")
        ]
    )
    session = SimpleNamespace(read_resource=read_resource)

    evidence = json.loads(asyncio.run(_serialize_fabric_result(result, session)))

    assert calls == ["file:///remote-only.csv"]
    assert "RES-1" in evidence["resources"][0]["text"]


@pytest.mark.parametrize(
    ("resource", "message"),
    [
        (
            BlobResourceContents(uri="file:///bad.csv", mimeType="text/csv", blob="not-base64!"),
            "Unreadable Fabric resource",
        ),
        (
            BlobResourceContents(uri="file:///image.png", mimeType="image/png", blob=""),
            "Unsupported Fabric resource MIME type",
        ),
        (
            TextResourceContents(uri="file:///empty.csv", mimeType="text/csv", text=""),
            "empty evidence",
        ),
    ],
)
def test_fabric_evidence_fails_closed_for_unreadable_resources(
    resource: BlobResourceContents | TextResourceContents, message: str
) -> None:
    result = CallToolResult(content=[EmbeddedResource(type="resource", resource=resource)])
    with pytest.raises(RuntimeError, match=message):
        asyncio.run(_serialize_fabric_result(result, object()))


def test_fabric_evidence_rejects_server_errors_even_with_content() -> None:
    result = CallToolResult(
        content=[TextContent(type="text", text="Permission denied")], isError=True
    )
    with pytest.raises(RuntimeError, match="query failed: Permission denied"):
        asyncio.run(_serialize_fabric_result(result, object()))


def test_fabric_evidence_accepts_structured_only_results() -> None:
    result = CallToolResult(content=[], structuredContent={"rows": [{"count": 20}]})
    evidence = json.loads(asyncio.run(_serialize_fabric_result(result, object())))
    assert evidence["structured_content"]["rows"] == [{"count": 20}]
