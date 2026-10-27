from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from unittest.mock import create_autospec

import pytest
from azure.core.credentials import AccessToken
from fabric.artifacts import FabricTopology, load_notebook_contracts
from fabric.client import (
    FabricApiError,
    FabricOperationFailed,
    FabricRestClient,
    HttpResponse,
)
from fabric.deployer import FabricDeployer


@dataclass
class FakeCredential:
    def get_token(self, *_scopes: str) -> AccessToken:
        return AccessToken("token", 4_102_444_800)


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = responses
        self.headers: list[dict[str, str]] = []
        self.urls: list[str] = []
        self.bodies: list[bytes | None] = []

    def request(
        self,
        _method: str,
        _url: str,
        headers: dict[str, str],
        _body: bytes | None,
    ) -> HttpResponse:
        self.headers.append(headers)
        self.urls.append(_url)
        self.bodies.append(_body)
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


@pytest.mark.parametrize("operation", ["create", "update"])
def test_ontology_uses_specialized_route_and_parts_only_body_through_lro(
    operation: str,
) -> None:
    transport = FakeTransport(
        [
            HttpResponse(
                status_code=202,
                headers={"location": "https://api.fabric.microsoft.com/v1/operations/123"},
                text="",
            ),
            HttpResponse(status_code=200, headers={}, text='{"status":"Succeeded"}'),
            HttpResponse(status_code=200, headers={}, text='{"id":"ontology-id"}'),
        ]
    )
    client = FabricRestClient(
        credential=FakeCredential(), transport=transport, sleeper=lambda _seconds: None
    )
    parts = [
        {
            "path": "database.tmdl",
            "payload": "ZGF0YWJhc2UK",
            "payloadType": "InlineBase64",
        }
    ]
    definition = {"format": "TMDL", "parts": parts}

    if operation == "create":
        body = {
            "displayName": "HotelOperationsOntology",
            "type": "Ontology",
            "definition": definition,
        }
        result = client.create_ontology("workspace-id", body)
        assert transport.urls[0].endswith("/workspaces/workspace-id/ontologies")
        assert body["type"] == "Ontology"
        assert json.loads(transport.bodies[0] or b"{}")["displayName"] == (
            "HotelOperationsOntology"
        )
    else:
        result = client.update_ontology_definition("workspace-id", "ontology-id", definition)
        assert transport.urls[0].endswith(
            "/workspaces/workspace-id/ontologies/ontology-id/updateDefinition?updateMetadata=true"
        )

    request_body = json.loads(transport.bodies[0] or b"{}")
    assert "type" not in request_body
    assert request_body["definition"] == {"parts": parts}
    assert "format" not in request_body["definition"]
    assert definition == {"format": "TMDL", "parts": parts}
    assert result["id"] == "ontology-id"
    assert transport.urls[1:] == [
        "https://api.fabric.microsoft.com/v1/operations/123",
        "https://api.fabric.microsoft.com/v1/operations/123/result",
    ]
    assert len(transport.headers) == 3
    assert all(
        headers["x-ms-fabric-skill"] == "fabriciq-ontology-cli" for headers in transport.headers
    )


@pytest.mark.parametrize(
    ("operation", "status_code"),
    [("create", 200), ("create", 201), ("update", 200)],
)
def test_ontology_accepts_synchronous_success(operation: str, status_code: int) -> None:
    transport = FakeTransport(
        [HttpResponse(status_code=status_code, headers={}, text='{"id":"ontology-id"}')]
    )
    client = FabricRestClient(credential=FakeCredential(), transport=transport)
    definition = {"format": "TMDL", "parts": []}

    if operation == "create":
        result = client.create_ontology("workspace-id", {"definition": definition})
    else:
        result = client.update_ontology_definition("workspace-id", "ontology-id", definition)

    assert result["id"] == "ontology-id"
    assert json.loads(transport.bodies[0] or b"{}") == {"definition": {"parts": []}}
    assert transport.headers[0]["x-ms-fabric-skill"] == "fabriciq-ontology-cli"


@pytest.mark.parametrize("operation", ["create", "update"])
def test_generic_item_definition_preserves_format(operation: str) -> None:
    transport = FakeTransport(
        [
            HttpResponse(
                status_code=201 if operation == "create" else 200,
                headers={},
                text='{"id":"item-id"}',
            )
        ]
    )
    client = FabricRestClient(credential=FakeCredential(), transport=transport)
    definition = {"format": "TMDL", "parts": []}

    if operation == "create":
        result = client.create_item(
            "workspace-id", {"type": "SemanticModel", "definition": definition}
        )
        assert transport.urls[0].endswith("/workspaces/workspace-id/items")
        assert json.loads(transport.bodies[0] or b"{}")["type"] == "SemanticModel"
    else:
        result = client.update_item_definition("workspace-id", "item-id", definition)
        assert transport.urls[0].endswith(
            "/workspaces/workspace-id/items/item-id/updateDefinition?updateMetadata=true"
        )

    assert result["id"] == "item-id"
    assert json.loads(transport.bodies[0] or b"{}")["definition"] == definition
    assert definition["format"] == "TMDL"
    assert transport.headers[0]["x-ms-fabric-skill"] == "e2e-medallion-architecture"


@pytest.mark.parametrize("ready", [True, False])
def test_ontology_sql_bindings_use_actual_lakehouse_metadata(tmp_path: Path, ready: bool) -> None:
    repository = Path(__file__).resolve().parents[2]
    topology = FabricTopology.from_file(repository / "fabric/topology.json", repository)
    responses = [
        HttpResponse(
            status_code=200,
            headers={},
            text=json.dumps(
                {
                    "properties": {
                        "sqlEndpointProperties": {
                            "id": endpoint,
                            "connectionString": "example.datawarehouse.fabric.microsoft.com",
                            "provisioningStatus": "Success" if ready else "InProgress",
                        }
                    }
                }
            ),
        )
        for endpoint in ("operations-sql-id", "guest-sql-id")
    ]
    transport = FakeTransport(responses)
    client = FabricRestClient(credential=FakeCredential(), transport=transport)
    deployer = FabricDeployer(
        topology,
        load_notebook_contracts(topology.contract_file),
        tmp_path / "state.json",
        client=client,
    )
    lakehouses = {"HotelOperations": "operations-item-id", "HotelGuestServices": "guest-item-id"}

    if not ready:
        with pytest.raises(RuntimeError, match="no ready SQL endpoint"):
            deployer._ontology_sql_values("workspace-id", lakehouses)
        return
    values = deployer._ontology_sql_values("workspace-id", lakehouses)

    assert values["HOTEL_OPERATIONS_SQL_ENDPOINT_ID"] == "operations-sql-id"
    assert values["HOTEL_GUEST_SERVICES_SQL_ENDPOINT_ID"] == "guest-sql-id"
    assert values["FABRIC_SQL_SERVER"] == "example.datawarehouse.fabric.microsoft.com"
    assert all(
        headers["x-ms-fabric-skill"] == "fabriciq-ontology-cli" for headers in transport.headers
    )


def _apply_topology() -> FabricTopology:
    repository = Path(__file__).resolve().parents[2]
    return FabricTopology.from_file(repository / "fabric/topology.json", repository)


@pytest.mark.parametrize("blueprint", ["dataAgent", "semanticModel"])
@pytest.mark.parametrize("saved_state", [False, True])
def test_apply_refuses_protected_replacements_before_any_writes(
    tmp_path: Path, blueprint: str, saved_state: bool
) -> None:
    topology = _apply_topology()
    artifact = topology.blueprints[blueprint]
    client = create_autospec(FabricRestClient, instance=True, spec_set=True)
    client.list_workspaces.return_value = [
        {"id": "workspace-id", "displayName": topology.workspace.display_name}
    ]
    client.list_items.return_value = [
        {"id": "protected-id", "type": artifact.item_type, "displayName": artifact.display_name}
    ]
    state_path = tmp_path / "state" / "fabric-state.json"
    original = b'{"reviewed_state": "preserve exactly"}\n'
    if saved_state:
        state_path.parent.mkdir()
        state_path.write_bytes(original)
    deployer = FabricDeployer(
        topology, load_notebook_contracts(topology.contract_file), state_path, client=client
    )

    with pytest.raises(RuntimeError, match="Refusing unsupported full-definition") as error:
        deployer.apply(dry_run=False)

    assert artifact.display_name in str(error.value)
    assert "native-preserving configuration workflow" in str(error.value)
    assert "HotelDataAgentRuntimePublish" in str(error.value)
    assert "Power BI Prep for AI" in str(error.value)
    assert [call[0] for call in client.method_calls] == ["list_workspaces", "list_items"]
    if saved_state:
        assert state_path.read_bytes() == original
    else:
        assert not state_path.parent.exists()


def test_apply_item_discovery_failure_does_not_write(tmp_path: Path) -> None:
    topology = _apply_topology()
    client = create_autospec(FabricRestClient, instance=True, spec_set=True)
    client.list_workspaces.return_value = [
        {"id": "workspace-id", "displayName": topology.workspace.display_name}
    ]
    client.list_items.side_effect = RuntimeError("Discovery failed")
    state_path = tmp_path / "state.json"

    with pytest.raises(RuntimeError, match="Discovery failed"):
        FabricDeployer(topology, {}, state_path, client=client).apply(dry_run=False)

    assert [call[0] for call in client.method_calls] == ["list_workspaces", "list_items"]
    assert not state_path.exists()


@pytest.mark.parametrize("blueprint", ["dataAgent", "semanticModel"])
@pytest.mark.parametrize("new_workspace", [False, True])
def test_apply_retains_new_protected_item_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blueprint: str,
    new_workspace: bool,
) -> None:
    original = _apply_topology()
    artifact = original.blueprints[blueprint]
    topology = replace(original, lakehouses=(), notebooks=(), blueprints={blueprint: artifact})
    client = create_autospec(FabricRestClient, instance=True, spec_set=True)
    workspace = {"id": "workspace-id", "displayName": topology.workspace.display_name}
    client.list_workspaces.return_value = [] if new_workspace else [workspace]
    client.create_workspace.return_value = workspace
    client.list_items.return_value = [
        {"id": "other-id", "type": artifact.item_type, "displayName": "Unrelated"},
        {"id": "report-id", "type": "Report", "displayName": artifact.display_name},
    ]
    client.create_data_agent.return_value = {"id": "new-agent"}
    client.create_item.return_value = {"id": "new-model"}
    monkeypatch.setattr("fabric.deployer.build_artifact_definition", lambda *_args: {"parts": []})

    state = FabricDeployer(topology, {}, tmp_path / "state.json", client=client).apply(
        dry_run=False
    )

    method = client.create_data_agent if blueprint == "dataAgent" else client.create_item
    method.assert_called_once()
    assert client.create_workspace.call_count == int(new_workspace)
    client.update_data_agent_definition.assert_not_called()
    client.update_item_definition.assert_not_called()
    assert state["items"][f"{artifact.item_type}:{artifact.display_name}"]["id"].startswith("new-")


def test_apply_retains_non_native_updates_with_protected_blueprints_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _apply_topology()
    report = original.blueprints["report"]
    blueprints = {
        key: replace(artifact, deployable=False)
        for key, artifact in original.blueprints.items()
        if key in {"dataAgent", "semanticModel"}
    }
    blueprints["report"] = report
    topology = replace(original, lakehouses=(), notebooks=(), blueprints=blueprints)
    client = create_autospec(FabricRestClient, instance=True, spec_set=True)
    client.list_workspaces.return_value = [
        {"id": "workspace-id", "displayName": topology.workspace.display_name}
    ]
    client.list_items.return_value = [
        {"id": key, "type": artifact.item_type, "displayName": artifact.display_name}
        for key, artifact in blueprints.items()
    ]
    client.update_item_definition.return_value = {"id": "report"}
    monkeypatch.setattr("fabric.deployer.build_artifact_definition", lambda *_args: {"parts": []})

    FabricDeployer(topology, {}, tmp_path / "state.json", client=client).apply(dry_run=False)

    client.update_item_definition.assert_called_once_with("workspace-id", "report", {"parts": []})
    client.update_data_agent_definition.assert_not_called()
    client.create_data_agent.assert_not_called()
    client.create_item.assert_not_called()


def test_apply_dry_run_can_inspect_protected_items_without_replacing_them(tmp_path: Path) -> None:
    topology = _apply_topology()
    client = create_autospec(FabricRestClient, instance=True, spec_set=True)
    client.list_workspaces.return_value = [
        {"id": "workspace-id", "displayName": topology.workspace.display_name}
    ]
    client.list_items.return_value = [
        {"id": key, "type": artifact.item_type, "displayName": artifact.display_name}
        for key, artifact in topology.blueprints.items()
        if artifact.item_type in {"DataAgent", "SemanticModel"}
    ]

    state = FabricDeployer(topology, {}, tmp_path / "state.json", client=client).apply()

    assert [call[0] for call in client.method_calls] == ["list_workspaces", "list_items"]
    assert all(operation["status"] == "planned" for operation in state["operations"])


def test_request_json_uses_credential_token() -> None:
    transport = FakeTransport([HttpResponse(status_code=200, headers={}, text='{"value": []}')])
    client = FabricRestClient(
        credential=FakeCredential(),
        transport=transport,
        sleeper=lambda _seconds: None,
    )

    client.request_json("GET", "/workspaces", expected_statuses={200})

    assert transport.headers[0]["Authorization"] == "Bearer token"
