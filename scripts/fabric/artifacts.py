from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_PARAMETER_TYPES = frozenset({"Text", "Boolean", "Number", "Integer", "Guid", "DateTime"})


@dataclass(frozen=True, slots=True)
class WorkspaceSpec:
    display_name: str
    description: str
    capacity_id: str
    capacity_region: str


@dataclass(frozen=True, slots=True)
class ShortcutSpec:
    name: str
    path: str
    source_lakehouse: str
    source_path: str


@dataclass(frozen=True, slots=True)
class LakehouseSpec:
    display_name: str
    description: str
    default_schema: str
    enable_schemas: bool
    authoritative_tables: tuple[str, ...]
    shortcuts: tuple[ShortcutSpec, ...]


@dataclass(frozen=True, slots=True)
class NotebookSpec:
    display_name: str
    description: str
    definition_path: Path
    contract_key: str
    default_lakehouse: str


@dataclass(frozen=True, slots=True)
class ArtifactBlueprint:
    display_name: str
    path: Path
    deployable: bool
    blocking_reason: str | None


@dataclass(frozen=True, slots=True)
class NotebookParameterSpec:
    name: str
    type_name: str
    required: bool
    description: str
    allowed_values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FabricTopology:
    repository_root: Path
    source_file: Path
    workspace: WorkspaceSpec
    lakehouses: tuple[LakehouseSpec, ...]
    notebooks: tuple[NotebookSpec, ...]
    blueprints: dict[str, ArtifactBlueprint]
    contract_file: Path

    @classmethod
    def from_file(cls, path: Path, repository_root: Path) -> FabricTopology:
        data = json.loads(path.read_text(encoding="utf-8"))
        workspace_raw = _mapping(data.get("workspace"))
        lakehouses_raw = _sequence(data.get("lakehouses"))
        notebooks_raw = _sequence(data.get("notebooks"))
        blueprints_raw = _mapping(data.get("blueprints"))

        workspace = WorkspaceSpec(
            display_name=_string(workspace_raw, "displayName"),
            description=_string(workspace_raw, "description"),
            capacity_id=_string(workspace_raw, "capacityId"),
            capacity_region=_string(workspace_raw, "capacityRegion"),
        )
        lakehouses = tuple(
            LakehouseSpec(
                display_name=_string(item, "displayName"),
                description=_string(item, "description"),
                default_schema=_string(item, "defaultSchema"),
                enable_schemas=_bool(item.get("enableSchemas")),
                authoritative_tables=tuple(_string_list(item.get("authoritativeTables"))),
                shortcuts=tuple(
                    ShortcutSpec(
                        name=_string(shortcut, "name"),
                        path=_string(shortcut, "path"),
                        source_lakehouse=_string(shortcut, "sourceLakehouse"),
                        source_path=_string(shortcut, "sourcePath"),
                    )
                    for shortcut in _sequence(item.get("shortcuts"))
                ),
            )
            for item in lakehouses_raw
        )
        notebooks = tuple(
            NotebookSpec(
                display_name=_string(item, "displayName"),
                description=_string(item, "description"),
                definition_path=_resolve_path(repository_root, _string(item, "definitionPath")),
                contract_key=_string(item, "contractKey"),
                default_lakehouse=_string(item, "defaultLakehouse"),
            )
            for item in notebooks_raw
        )
        blueprints = {
            name: ArtifactBlueprint(
                display_name=_string(item, "displayName"),
                path=_resolve_path(repository_root, _string(item, "path")),
                deployable=_bool(item.get("deployable")),
                blocking_reason=_optional_string(item.get("blockingReason")),
            )
            for name, item in blueprints_raw.items()
            if isinstance(item, dict)
        }

        return cls(
            repository_root=repository_root,
            source_file=path,
            workspace=workspace,
            lakehouses=lakehouses,
            notebooks=notebooks,
            blueprints=blueprints,
            contract_file=_resolve_path(repository_root, _string(data, "contractFile")),
        )


def load_notebook_contracts(path: Path) -> dict[str, tuple[NotebookParameterSpec, ...]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, tuple[NotebookParameterSpec, ...]] = {}
    for notebook_name, notebook_value in _mapping(raw).items():
        notebook_mapping = _mapping(notebook_value)
        parameters = tuple(
            NotebookParameterSpec(
                name=_string(parameter, "name"),
                type_name=_string(parameter, "type"),
                required=_bool(parameter.get("required")),
                description=_string(parameter, "description"),
                allowed_values=tuple(_string_list(parameter.get("allowedValues"))),
            )
            for parameter in _sequence(notebook_mapping.get("parameters"))
        )
        result[notebook_name] = parameters
    return result


def _resolve_path(root: Path, relative: str) -> Path:
    return (root / relative).resolve()


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sequence(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string(value: dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"Expected non-empty string for {key!r}")
    return raw


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Expected non-empty string entries")
        result.append(item)
    return result


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Expected boolean value")
    return value
