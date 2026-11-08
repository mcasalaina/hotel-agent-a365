from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import create_autospec

import pytest
from fabric.artifacts import FabricTopology
from fabric.cli import main
from fabric.client import FabricApiError, FabricOperationFailed, FabricRestClient, HttpResponse
from fabric.deployer import FabricDeployer
from fabric.fab_cli import FabCliTransport

TENANT_ID = "00000000-0000-0000-0000-000000000001"
CAPACITY_ID = "00000000-0000-0000-0000-000000000002"


def test_fab_transport_uses_authenticated_cli_and_private_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    body_paths: list[Path] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[1] == "auth":
            return subprocess.CompletedProcess(command, 0, f"Tenant ID: {TENANT_ID}")
        body_path = Path(command[command.index("-i") + 1])
        body_paths.append(body_path)
        assert json.loads(body_path.read_bytes()) == {"displayName": "Hotel"}
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"status_code": 201, "headers": {}, "text": {"id": "item"}})
        )

    monkeypatch.setattr("fabric.fab_cli.subprocess.run", run)
    client = FabricRestClient(transport=FabCliTransport(TENANT_ID))
    response = client.request_json(
        "POST", "/workspaces", {"displayName": "Hotel"}, expected_statuses={201}
    )

    assert response.json() == {"id": "item"}
    assert calls[1][2] == "workspaces"
    assert not any("Authorization" in arg for arg in calls[1])
    assert not body_paths[0].exists()


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_fab_http_failures_are_not_success(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[1] == "auth":
            return subprocess.CompletedProcess(command, 0, f"Tenant ID: {TENANT_ID}")
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"status_code": status, "text": {"errorCode": "UserNotLicensed"}}),
        )

    monkeypatch.setattr("fabric.fab_cli.subprocess.run", run)
    with pytest.raises(FabricApiError, match=f"HTTP {status}"):
        FabricRestClient(transport=FabCliTransport(TENANT_ID)).list_capacities()


@pytest.mark.parametrize("output", ["Not logged in", "Tenant ID: " + CAPACITY_ID])
def test_fab_wrong_tenant_refuses_api(monkeypatch: pytest.MonkeyPatch, output: str) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, output)

    monkeypatch.setattr("fabric.fab_cli.subprocess.run", run)
    with pytest.raises(FabricOperationFailed, match="requested tenant"):
        FabricRestClient(transport=FabCliTransport(TENANT_ID)).list_workspaces()
    assert len(calls) == 1


@pytest.mark.parametrize(
    "capacity",
    [
        None,
        {"id": CAPACITY_ID, "state": "Paused", "region": "East US 2"},
        {"id": CAPACITY_ID, "state": "Active", "region": "West US 3"},
        {"id": TENANT_ID, "state": "Active", "region": "East US 2"},
    ],
)
def test_apply_capacity_failure_has_no_writes(
    tmp_path: Path, capacity: dict[str, str] | None
) -> None:
    root = Path(__file__).resolve().parents[2]
    topology = FabricTopology.from_file(root / "fabric/topology.json", root)
    topology = replace(topology, workspace=replace(topology.workspace, capacity_id=CAPACITY_ID))
    client = create_autospec(FabricRestClient, instance=True)
    client.list_workspaces.return_value = []
    client.list_capacities.return_value = [] if capacity is None else [capacity]
    state_path = tmp_path / "state.json"

    with pytest.raises(RuntimeError, match="capacity"):
        FabricDeployer(topology, {}, state_path, client=client).apply(dry_run=False)

    assert [call[0] for call in client.method_calls] == ["list_workspaces", "list_capacities"]
    assert not state_path.exists()


def test_paginated_discovery_includes_all_items() -> None:
    client = create_autospec(FabricRestClient, instance=True)
    client._base_url = "https://api.fabric.microsoft.com/v1"
    client.request_json.side_effect = [
        HttpResponse(
            200,
            {},
            json.dumps(
                {
                    "value": [{"id": "first"}],
                    "continuationUri": "https://api.fabric.microsoft.com/v1/items?page=2",
                }
            ),
        ),
        HttpResponse(200, {}, json.dumps({"value": [{"id": "target"}]})),
    ]
    assert FabricRestClient._list_collection(client, "/items") == [
        {"id": "first"},
        {"id": "target"},
    ]


def test_shortcuts_use_native_route_and_creatable_target() -> None:
    client = create_autospec(FabricRestClient, instance=True)
    client.request_json.return_value = HttpResponse(201, {}, '{"name":"ops_properties"}')
    body = {
        "name": "ops_properties",
        "path": "Tables",
        "target": {
            "type": "OneLake",
            "oneLake": {
                "workspaceId": TENANT_ID,
                "itemId": CAPACITY_ID,
                "path": "Tables/properties",
            },
        },
    }
    result = FabricRestClient.create_or_update_shortcut(client, TENANT_ID, CAPACITY_ID, body)

    assert result["name"] == "ops_properties"
    args = client.request_json.call_args.args
    assert args[1].endswith("/shortcuts?shortcutConflictPolicy=CreateOrOverwrite")
    assert args[2]["target"] == {"oneLake": body["target"]["oneLake"]}
    assert body["target"]["type"] == "OneLake"


def test_local_validation_ignores_remote_authentication_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"authMode": "fab", "discoverRemote": True, "tenantId": ""}),
        encoding="utf-8",
    )

    def unexpected_auth(_tenant_id: str) -> None:
        raise AssertionError("Local validation must not authenticate.")

    monkeypatch.setattr("fabric.cli.FabCliTransport", unexpected_auth)
    assert main(["validate", "--config", str(config)]) == 0
