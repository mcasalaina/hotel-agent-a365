from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fabric.artifacts import FabricTopology, NotebookParameterSpec
from fabric.client import FabricRestClient
from fabric.discovery import SourceDiscoveryResult, discover_source_files
from fabric.payloads import (
    build_lakehouse_payload,
    build_notebook_payload,
    build_workspace_payload,
)
from fabric.state import (
    append_operation,
    load_state,
    record_item,
    record_workspace,
    save_state,
)


@dataclass(frozen=True, slots=True)
class PlannedOperation:
    action: str
    item_type: str
    display_name: str
    detail: str


class FabricDeployer:
    def __init__(
        self,
        topology: FabricTopology,
        contracts: dict[str, tuple[NotebookParameterSpec, ...]],
        state_path: Path,
        client: FabricRestClient | None = None,
        source_root: Path | None = None,
        workspace_id_override: str | None = None,
    ) -> None:
        self._topology = topology
        self._contracts = contracts
        self._state_path = state_path
        self._client = client
        self._source_root = source_root
        self._workspace_id_override = workspace_id_override

    def build_plan(self, discover_remote: bool) -> tuple[list[PlannedOperation], dict[str, Any]]:
        state = load_state(self._state_path, self._topology.source_file)
        workspace = None
        items: list[dict[str, Any]] = []
        if discover_remote:
            if self._client is None:
                raise RuntimeError("Remote discovery requested without a Fabric client.")
            workspace = self._resolve_workspace()
            if workspace is not None:
                items = self._client.list_items(str(workspace["id"]))
        if workspace is None:
            state["workspace"] = {
                "displayName": self._topology.workspace.display_name,
                "id": self._workspace_id_override,
            }
        else:
            record_workspace(state, workspace)

        if self._source_root is not None:
            discovery = self.discover_sources()
            state["sourceDiscovery"] = _source_state_payload(discovery)

        operations: list[PlannedOperation] = []
        operations.extend(self._plan_workspace(workspace))
        operations.extend(self._plan_lakehouses(items))
        operations.extend(self._plan_notebooks(items))
        operations.extend(self._plan_blocked_blueprints())
        state["pendingArtifacts"] = {
            name: blueprint.blocking_reason or ""
            for name, blueprint in self._topology.blueprints.items()
            if not blueprint.deployable
        }
        save_state(self._state_path, state)
        return operations, state

    def apply(self, dry_run: bool = True) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Fabric client is required for apply.")
        if dry_run:
            operations, state = self.build_plan(discover_remote=True)
            for operation in operations:
                append_operation(
                    state,
                    operation.action,
                    operation.item_type,
                    operation.display_name,
                    "planned",
                )
            save_state(self._state_path, state)
            return state

        state = load_state(self._state_path, self._topology.source_file)
        workspace = self._resolve_workspace()
        if workspace is None:
            workspace = self._client.create_workspace(
                build_workspace_payload(
                    self._topology.workspace.display_name,
                    self._topology.workspace.description,
                    self._topology.workspace.capacity_id,
                )
            )
            append_operation(
                state,
                "create",
                "Workspace",
                self._topology.workspace.display_name,
                "created",
            )
        record_workspace(state, workspace)

        workspace_id = str(workspace["id"])
        current_items = {
            (str(item.get("type")), str(item.get("displayName"))): item
            for item in self._client.list_items(workspace_id)
        }
        lakehouse_ids: dict[str, str] = {
            display_name: str(item.get("id"))
            for (item_type, display_name), item in current_items.items()
            if item_type == "Lakehouse"
        }
        for lakehouse in self._ordered_lakehouses():
            existing = current_items.get(("Lakehouse", lakehouse.display_name))
            payload = build_lakehouse_payload(lakehouse, workspace_id, lakehouse_ids)
            if existing is None:
                created = self._client.create_lakehouse(workspace_id, payload)
                current_items[("Lakehouse", lakehouse.display_name)] = created
                lakehouse_ids[lakehouse.display_name] = str(created["id"])
                append_operation(state, "create", "Lakehouse", lakehouse.display_name, "created")
                record_item(state, "Lakehouse", lakehouse.display_name, str(created["id"]))
            else:
                updated = self._client.update_item_definition(
                    workspace_id,
                    str(existing["id"]),
                    payload["definition"],
                )
                lakehouse_ids[lakehouse.display_name] = str(existing["id"])
                append_operation(state, "update", "Lakehouse", lakehouse.display_name, "updated")
                record_item(
                    state,
                    "Lakehouse",
                    lakehouse.display_name,
                    str(existing["id"]),
                )
                if updated.get("id"):
                    current_items[("Lakehouse", lakehouse.display_name)] = updated

        for notebook in self._topology.notebooks:
            existing = current_items.get(("Notebook", notebook.display_name))
            payload = build_notebook_payload(notebook)
            if existing is None:
                created = self._client.create_item(workspace_id, payload)
                current_items[("Notebook", notebook.display_name)] = created
                append_operation(state, "create", "Notebook", notebook.display_name, "created")
                record_item(state, "Notebook", notebook.display_name, str(created["id"]))
            else:
                self._client.update_item_definition(
                    workspace_id,
                    str(existing["id"]),
                    payload["definition"],
                )
                append_operation(state, "update", "Notebook", notebook.display_name, "updated")
                record_item(state, "Notebook", notebook.display_name, str(existing["id"]))

        if self._source_root is not None:
            state["sourceDiscovery"] = _source_state_payload(self.discover_sources())
        state["pendingArtifacts"] = {
            name: blueprint.blocking_reason or ""
            for name, blueprint in self._topology.blueprints.items()
            if not blueprint.deployable
        }
        save_state(self._state_path, state)
        return state

    def discover_sources(self) -> SourceDiscoveryResult:
        tables: list[str] = []
        for lakehouse in self._topology.lakehouses:
            tables.extend(lakehouse.authoritative_tables)
        if self._source_root is None:
            raise RuntimeError("Source discovery requested without a source root.")
        return discover_source_files(self._source_root, tuple(sorted(set(tables))))

    def _resolve_workspace(self) -> dict[str, Any] | None:
        if self._client is None:
            raise RuntimeError("Fabric client is required for workspace discovery.")
        if self._workspace_id_override:
            matches = [
                workspace
                for workspace in self._client.list_workspaces()
                if str(workspace.get("id")) == self._workspace_id_override
            ]
            if not matches:
                raise RuntimeError(
                    f"Fabric workspace ID {self._workspace_id_override!r} was not found."
                )
            return self._validate_workspace(matches[0])
        matches = [
            workspace
            for workspace in self._client.list_workspaces()
            if workspace.get("displayName") == self._topology.workspace.display_name
        ]
        if len(matches) > 1:
            raise RuntimeError(
                f"Multiple Fabric workspaces are named "
                f"{self._topology.workspace.display_name!r}; provide --workspace-id."
            )
        return self._validate_workspace(matches[0]) if matches else None

    def _validate_workspace(self, workspace: dict[str, Any]) -> dict[str, Any]:
        display_name = workspace.get("displayName")
        if display_name != self._topology.workspace.display_name:
            raise RuntimeError(
                f"Fabric workspace {workspace.get('id')!r} is named {display_name!r}, "
                f"not {self._topology.workspace.display_name!r}."
            )
        capacity_id = workspace.get("capacityId")
        if capacity_id and capacity_id != self._topology.workspace.capacity_id:
            raise RuntimeError(
                f"Fabric workspace {workspace.get('id')!r} uses capacity {capacity_id!r}, "
                f"not {self._topology.workspace.capacity_id!r}."
            )
        return workspace

    def _ordered_lakehouses(self) -> tuple[Any, ...]:
        order = {"HotelOperations": 0, "HotelGuestServices": 1}
        return tuple(sorted(self._topology.lakehouses, key=lambda item: order[item.display_name]))

    def _plan_workspace(self, workspace: dict[str, Any] | None) -> list[PlannedOperation]:
        if workspace is None:
            return [
                PlannedOperation(
                    "create",
                    "Workspace",
                    self._topology.workspace.display_name,
                    f"Capacity {self._topology.workspace.capacity_id}",
                )
            ]
        return [
            PlannedOperation(
                "reuse",
                "Workspace",
                self._topology.workspace.display_name,
                f"Workspace ID {workspace.get('id')}",
            )
        ]

    def _plan_lakehouses(self, items: list[dict[str, Any]]) -> list[PlannedOperation]:
        index = {(str(item.get("type")), str(item.get("displayName"))): item for item in items}
        operations: list[PlannedOperation] = []
        for lakehouse in self._ordered_lakehouses():
            existing = index.get(("Lakehouse", lakehouse.display_name))
            if existing is None:
                operations.append(
                    PlannedOperation(
                        "create",
                        "Lakehouse",
                        lakehouse.display_name,
                        f"{len(lakehouse.authoritative_tables)} authoritative tables",
                    )
                )
            else:
                operations.append(
                    PlannedOperation(
                        "update",
                        "Lakehouse",
                        lakehouse.display_name,
                        f"Item ID {existing.get('id')}",
                    )
                )
        return operations

    def _plan_notebooks(self, items: list[dict[str, Any]]) -> list[PlannedOperation]:
        index = {(str(item.get("type")), str(item.get("displayName"))): item for item in items}
        operations: list[PlannedOperation] = []
        for notebook in self._topology.notebooks:
            existing = index.get(("Notebook", notebook.display_name))
            action = "update" if existing is not None else "create"
            detail = f"Contract {notebook.contract_key}"
            if existing is not None:
                detail = f"{detail}; item ID {existing.get('id')}"
            operations.append(PlannedOperation(action, "Notebook", notebook.display_name, detail))
        return operations

    def _plan_blocked_blueprints(self) -> list[PlannedOperation]:
        return [
            PlannedOperation(
                "blocked",
                "Blueprint",
                blueprint.display_name,
                blueprint.blocking_reason or "Not deployable in this slice.",
            )
            for blueprint in self._topology.blueprints.values()
            if not blueprint.deployable
        ]


def _source_state_payload(discovery: SourceDiscoveryResult) -> dict[str, Any]:
    return {
        "root": str(discovery.root),
        "matches": {
            table: [str(path) for path in paths] for table, paths in discovery.matches.items()
        },
        "missingTables": list(discovery.missing_tables),
    }
