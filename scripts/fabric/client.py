from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from azure.core.credentials import TokenCredential

from fabric import FABRIC_API_BASE_URL, FABRIC_API_SCOPE


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    text: str

    def json(self) -> Any:
        if not self.text:
            return None
        return json.loads(self.text)


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> HttpResponse: ...


class UrllibTransport:
    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return HttpResponse(
                    status_code=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    text=response.read().decode("utf-8"),
                )
        except urllib.error.HTTPError as error:
            return HttpResponse(
                status_code=error.code,
                headers={key.lower(): value for key, value in error.headers.items()},
                text=error.read().decode("utf-8"),
            )


class FabricApiError(RuntimeError):
    def __init__(self, method: str, url: str, response: HttpResponse):
        message = f"{method} {url} failed with HTTP {response.status_code}"
        if response.text:
            message = f"{message}: {response.text}"
        super().__init__(message)
        self.method = method
        self.url = url
        self.response = response


class FabricOperationFailed(RuntimeError):
    pass


class FabricRestClient:
    def __init__(
        self,
        credential: TokenCredential,
        transport: HttpTransport | None = None,
        base_url: str = FABRIC_API_BASE_URL,
        scope: str = FABRIC_API_SCOPE,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._credential = credential
        self._transport = transport or UrllibTransport()
        self._base_url = base_url.rstrip("/")
        self._scope = scope
        self._sleeper = sleeper or time.sleep

    def list_workspaces(self) -> list[dict[str, Any]]:
        response = self.request_json("GET", "/workspaces", expected_statuses={200})
        payload = response.json()
        return _value_list(payload)

    def list_items(self, workspace_id: str) -> list[dict[str, Any]]:
        response = self.request_json(
            "GET",
            f"/workspaces/{workspace_id}/items",
            expected_statuses={200},
        )
        payload = response.json()
        return _value_list(payload)

    def create_workspace(self, body: dict[str, Any]) -> dict[str, Any]:
        response = self.request_json("POST", "/workspaces", body, expected_statuses={201})
        payload = response.json()
        if not isinstance(payload, dict):
            raise FabricOperationFailed("Workspace create returned no JSON body.")
        return payload

    def create_lakehouse(self, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self.request_json(
            "POST",
            f"/workspaces/{workspace_id}/lakehouses",
            body,
            expected_statuses={201, 202},
        )
        return self._resolve_lro_result("POST", response)

    def create_item(self, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self.request_json(
            "POST",
            f"/workspaces/{workspace_id}/items",
            body,
            expected_statuses={201, 202},
        )
        return self._resolve_lro_result("POST", response)

    def create_ontology(self, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self.request_json(
            "POST",
            f"/workspaces/{workspace_id}/ontologies",
            body,
            expected_statuses={201, 202},
        )
        return self._resolve_lro_result("POST", response)

    def create_data_agent(self, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self.request_json(
            "POST",
            f"/workspaces/{workspace_id}/dataAgents",
            body,
            expected_statuses={201, 202},
        )
        return self._resolve_lro_result("POST", response)

    def update_item_definition(
        self,
        workspace_id: str,
        item_id: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.request_json(
            "POST",
            f"/workspaces/{workspace_id}/items/{item_id}/updateDefinition?updateMetadata=true",
            {"definition": definition},
            expected_statuses={200, 202},
        )
        return self._resolve_lro_result("POST", response)

    def update_ontology_definition(
        self,
        workspace_id: str,
        ontology_id: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.request_json(
            "POST",
            f"/workspaces/{workspace_id}/ontologies/{ontology_id}/updateDefinition?updateMetadata=true",
            {"definition": definition},
            expected_statuses={200, 202},
        )
        return self._resolve_lro_result("POST", response)

    def update_data_agent_definition(
        self,
        workspace_id: str,
        data_agent_id: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.request_json(
            "POST",
            f"/workspaces/{workspace_id}/dataAgents/{data_agent_id}/updateDefinition?updateMetadata=true",
            {"definition": definition},
            expected_statuses={200, 202},
        )
        return self._resolve_lro_result("POST", response)

    def request_json(
        self,
        method: str,
        path_or_url: str,
        body: dict[str, Any] | None = None,
        expected_statuses: set[int] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        url = self._qualify_url(path_or_url)
        headers = {"Authorization": f"Bearer {self._token()}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        raw_body = json.dumps(body).encode("utf-8") if body is not None else None
        response = self._transport.request(method, url, headers, raw_body)
        if expected_statuses is not None and response.status_code not in expected_statuses:
            raise FabricApiError(method, url, response)
        return response

    def poll_operation(
        self,
        location: str,
        initial_retry_after: int | None = None,
    ) -> dict[str, Any]:
        retry_after = initial_retry_after or 5
        while True:
            self._sleeper(retry_after)
            response = self.request_json("GET", location, expected_statuses={200})
            payload = response.json()
            if not isinstance(payload, dict):
                raise FabricOperationFailed("Fabric LRO response did not return a JSON object.")
            status = str(payload.get("status", ""))
            if status in {"Succeeded", "Completed"}:
                return self._read_operation_result(location, payload)
            if status in {"Failed", "Cancelled"}:
                raise FabricOperationFailed(json.dumps(payload, indent=2, sort_keys=True))
            retry_after = _retry_after_seconds(response.headers) or retry_after

    def _resolve_lro_result(self, method: str, response: HttpResponse) -> dict[str, Any]:
        if response.status_code in {200, 201}:
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {}
        location = response.headers.get("location")
        if not location:
            raise FabricOperationFailed(
                f"{method} returned HTTP {response.status_code} without a Location header."
            )
        return self.poll_operation(location, _retry_after_seconds(response.headers))

    def _read_operation_result(self, location: str, fallback: dict[str, Any]) -> dict[str, Any]:
        result_url = f"{location.rstrip('/')}/result"
        try:
            response = self.request_json("GET", result_url, expected_statuses={200})
        except FabricApiError:
            return fallback
        payload = response.json()
        return payload if isinstance(payload, dict) else fallback

    def _qualify_url(self, path_or_url: str) -> str:
        parsed = urllib.parse.urlparse(path_or_url)
        if parsed.scheme and parsed.netloc:
            return path_or_url
        return f"{self._base_url}{path_or_url}"

    def _token(self) -> str:
        return self._credential.get_token(self._scope).token


def _retry_after_seconds(headers: dict[str, str]) -> int | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(1, int(value))
    except ValueError:
        return None


def _value_list(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    value = payload.get("value")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
