from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from fabric.artifacts import FabricTopology, load_notebook_contracts
from fabric.client import FabricRestClient
from fabric.deployer import FabricDeployer
from fabric.discovery import discover_source_files
from fabric.state import append_operation, load_state, record_item, record_workspace, save_state

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class DiscoveryOnlyClient:
    def __init__(self, workspaces: list[dict[str, Any]]) -> None:
        self.workspaces = workspaces
        self.create_calls = 0

    def list_workspaces(self) -> list[dict[str, Any]]:
        return self.workspaces

    def list_items(self, _workspace_id: str) -> list[dict[str, Any]]:
        return []

    def create_workspace(self, _body: dict[str, Any]) -> dict[str, Any]:
        self.create_calls += 1
        raise AssertionError("Dry run must not create a workspace.")


def _deployer(
    tmp_path: Path,
    client: DiscoveryOnlyClient,
    workspace_id: str | None = None,
) -> FabricDeployer:
    topology = FabricTopology.from_file(
        REPOSITORY_ROOT / "fabric" / "topology.json",
        REPOSITORY_ROOT,
    )
    contracts = load_notebook_contracts(topology.contract_file)
    return FabricDeployer(
        topology,
        contracts,
        tmp_path / "fabric-state.json",
        client=cast(FabricRestClient, client),
        workspace_id_override=workspace_id,
    )


def test_discover_source_files_matches_composite_suffix(tmp_path: Path) -> None:
    source_root = tmp_path / "generated"
    source_root.mkdir()
    (source_root / "properties.snappy.parquet").write_text("data", encoding="utf-8")
    (source_root / "guests.csv").write_text("data", encoding="utf-8")

    result = discover_source_files(source_root, ("properties", "guests", "folios"))

    assert [path.name for path in result.matches["properties"]] == ["properties.snappy.parquet"]
    assert result.missing_tables == ("folios",)


def test_state_round_trip(tmp_path: Path) -> None:
    state_path = tmp_path / "deployment-state.json"
    state = load_state(state_path, tmp_path / "fabric" / "topology.json")
    record_workspace(
        state,
        {
            "displayName": "HotelAgent.Workspace",
            "id": "workspace-id",
            "capacityId": "capacity-id",
            "capacityRegion": "East US 2",
        },
    )
    record_item(state, "Lakehouse", "HotelOperations", "item-id")
    append_operation(state, "create", "Lakehouse", "HotelOperations", "created")

    save_state(state_path, state)
    reloaded = load_state(state_path, tmp_path / "fabric" / "topology.json")

    assert reloaded["workspace"]["id"] == "workspace-id"
    assert reloaded["items"]["Lakehouse:HotelOperations"]["id"] == "item-id"
    assert reloaded["operations"][0]["action"] == "create"


def test_apply_defaults_to_non_mutating_dry_run(tmp_path: Path) -> None:
    client = DiscoveryOnlyClient([])

    state = _deployer(tmp_path, client).apply()

    assert client.create_calls == 0
    assert state["operations"][0]["status"] == "planned"


def test_explicit_unknown_workspace_id_fails_loudly(tmp_path: Path) -> None:
    client = DiscoveryOnlyClient([])

    with pytest.raises(RuntimeError, match="was not found"):
        _deployer(tmp_path, client, workspace_id="missing-workspace").build_plan(
            discover_remote=True
        )
