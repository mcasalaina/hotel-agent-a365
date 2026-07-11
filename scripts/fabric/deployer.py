from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fabric.artifacts import ArtifactSpec, FabricTopology, NotebookParameterSpec
from fabric.client import FabricRestClient
from fabric.discovery import SourceDiscoveryResult, discover_source_files
from fabric.payloads import (
    build_artifact_create_body,
    build_artifact_definition,
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
        operations.extend(self._plan_artifacts(items))
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
            payload = build_notebook_payload(notebook, workspace_id, lakehouse_ids)
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

        for artifact in self._ordered_artifacts():
            if not artifact.deployable:
                continue
            existing = current_items.get((artifact.item_type, artifact.display_name))
            definition = build_artifact_definition(
                artifact,
                self._template_values(workspace_id, lakehouse_ids, current_items),
            )
            specialized = artifact.item_type in {"Ontology", "DataAgent"}
            body = build_artifact_create_body(
                artifact,
                definition,
                specialized_endpoint=specialized,
            )
            if existing is None:
                created = self._create_artifact(workspace_id, artifact, body)
                current_items[(artifact.item_type, artifact.display_name)] = created
                append_operation(
                    state,
                    "create",
                    artifact.item_type,
                    artifact.display_name,
                    "created",
                )
                record_item(state, artifact.item_type, artifact.display_name, str(created["id"]))
            else:
                updated = self._update_artifact(
                    workspace_id,
                    artifact,
                    str(existing["id"]),
                    definition,
                )
                append_operation(
                    state,
                    "update",
                    artifact.item_type,
                    artifact.display_name,
                    "updated",
                )
                record_item(state, artifact.item_type, artifact.display_name, str(existing["id"]))
                if updated.get("id"):
                    current_items[(artifact.item_type, artifact.display_name)] = updated

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
        derived_tables = {
            "reservation_guests",
            "room_assignments",
            "adjustments",
            "action_sagas",
            "rate_plans",
            "action_confirmations",
            "idempotency_records",
            "audit_events",
        }
        tables: list[str] = []
        for lakehouse in self._topology.lakehouses:
            tables.extend(
                table
                for table in lakehouse.authoritative_tables
                if not table.startswith("agg_") and table not in derived_tables
            )
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

    def _ordered_artifacts(self) -> tuple[ArtifactSpec, ...]:
        order = {"SemanticModel": 0, "Report": 1, "Ontology": 2, "DataAgent": 3}
        return tuple(
            sorted(
                self._topology.blueprints.values(),
                key=lambda item: order.get(item.item_type, 100),
            )
        )

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

    def _plan_artifacts(self, items: list[dict[str, Any]]) -> list[PlannedOperation]:
        index = {(str(item.get("type")), str(item.get("displayName"))): item for item in items}
        operations: list[PlannedOperation] = []
        for artifact in self._ordered_artifacts():
            if not artifact.deployable:
                continue
            existing = index.get((artifact.item_type, artifact.display_name))
            action = "update" if existing is not None else "create"
            detail = artifact.definition_format or "Definition"
            if existing is not None:
                detail = f"{detail}; item ID {existing.get('id')}"
            operations.append(
                PlannedOperation(
                    action,
                    artifact.item_type,
                    artifact.display_name,
                    detail,
                )
            )
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

    def _template_values(
        self,
        workspace_id: str,
        lakehouse_ids: dict[str, str],
        current_items: dict[tuple[str, str], dict[str, Any]],
    ) -> dict[str, str]:
        values = {
            "WORKSPACE_ID": workspace_id,
            "WORKSPACE_NAME": self._topology.workspace.display_name,
            "HOTEL_OPERATIONS_LAKEHOUSE_ID": lakehouse_ids.get("HotelOperations", ""),
            "HOTEL_GUEST_SERVICES_LAKEHOUSE_ID": lakehouse_ids.get("HotelGuestServices", ""),
        }
        semantic_model = current_items.get(("SemanticModel", "HotelOperationsModel"))
        if semantic_model is not None:
            values["SEMANTICMODEL_ID"] = str(semantic_model.get("id", ""))
        ontology = current_items.get(("Ontology", "HotelOperationsOntology"))
        if ontology is not None:
            values["ONTOLOGY_ID"] = str(ontology.get("id", ""))
        data_agent = current_items.get(("DataAgent", "HotelOperationsAgent"))
        if data_agent is not None:
            values["DATAAGENT_ID"] = str(data_agent.get("id", ""))
        report = current_items.get(("Report", "HotelOperationsReport"))
        if report is not None:
            values["REPORT_ID"] = str(report.get("id", ""))
        return values

    def _create_artifact(
        self,
        workspace_id: str,
        artifact: ArtifactSpec,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Fabric client is required for artifact creation.")
        if artifact.item_type == "Ontology":
            return self._client.create_ontology(workspace_id, body)
        if artifact.item_type == "DataAgent":
            return self._client.create_data_agent(workspace_id, body)
        return self._client.create_item(workspace_id, body)

    def _update_artifact(
        self,
        workspace_id: str,
        artifact: ArtifactSpec,
        item_id: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Fabric client is required for artifact update.")
        if artifact.item_type == "Ontology":
            return self._client.update_ontology_definition(workspace_id, item_id, definition)
        if artifact.item_type == "DataAgent":
            return self._client.update_data_agent_definition(workspace_id, item_id, definition)
        return self._client.update_item_definition(workspace_id, item_id, definition)


def _source_state_payload(discovery: SourceDiscoveryResult) -> dict[str, Any]:
    return {
        "root": str(discovery.root),
        "matches": {
            table: [str(path) for path in paths] for table, paths in discovery.matches.items()
        },
        "missingTables": list(discovery.missing_tables),
    }
