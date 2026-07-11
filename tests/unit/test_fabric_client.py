from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from azure.core.credentials import AccessToken
from fabric.client import (
    FabricApiError,
    FabricOperationFailed,
    FabricRestClient,
    HttpResponse,
)


@dataclass
class FakeCredential:
    def get_token(self, *_scopes: str) -> AccessToken:
        return AccessToken("token", 4_102_444_800)


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = responses
        self.headers: list[dict[str, str]] = []

    def request(
        self,
        _method: str,
        _url: str,
        headers: dict[str, str],
        _body: bytes | None,
    ) -> HttpResponse:
        self.headers.append(headers)
        if not self._responses:
            raise AssertionError("No fake responses left.")
        return self._responses.pop(0)


def test_poll_operation_reads_result_after_success() -> None:
    responses = [
        HttpResponse(
            status_code=200,
            headers={"retry-after": "1"},
            text=json.dumps({"status": "Running"}),
        ),
        HttpResponse(
            status_code=200,
            headers={},
            text=json.dumps({"status": "Succeeded"}),
        ),
        HttpResponse(
            status_code=200,
            headers={},
            text=json.dumps({"id": "created-item-id"}),
        ),
    ]
    sleeps: list[float] = []
    client = FabricRestClient(
        credential=FakeCredential(),
        transport=FakeTransport(responses),
        sleeper=sleeps.append,
    )

    payload = client.poll_operation("https://api.fabric.microsoft.com/v1/operations/123", 1)

    assert payload["id"] == "created-item-id"
    assert sleeps == [1, 1]


def test_poll_operation_raises_on_failed_status() -> None:
    responses = [
        HttpResponse(
            status_code=200,
            headers={},
            text=json.dumps({"status": "Failed", "message": "boom"}),
        ),
    ]
    client = FabricRestClient(
        credential=FakeCredential(),
        transport=FakeTransport(responses),
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(FabricOperationFailed, match="boom"):
        client.poll_operation("https://api.fabric.microsoft.com/v1/operations/123", 1)


def test_request_json_raises_for_unexpected_status() -> None:
    responses = [
        HttpResponse(status_code=500, headers={}, text="server error"),
    ]
    client = FabricRestClient(
        credential=FakeCredential(),
        transport=FakeTransport(responses),
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(FabricApiError, match="HTTP 500"):
        client.request_json("GET", "/workspaces", expected_statuses={200})


def test_request_json_uses_credential_token() -> None:
    transport = FakeTransport([HttpResponse(status_code=200, headers={}, text='{"value": []}')])
    client = FabricRestClient(
        credential=FakeCredential(),
        transport=transport,
        sleeper=lambda _seconds: None,
    )

    client.request_json("GET", "/workspaces", expected_statuses={200})

    assert transport.headers[0]["Authorization"] == "Bearer token"
