from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fabric import ZERO_UUID
from fabric.artifacts import (
    ArtifactSpec,
    LakehouseSpec,
    NotebookParameterSpec,
    NotebookSpec,
    ShortcutSpec,
)

ONTOLOGY_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,89}$")
TEMPLATE_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
TEXT_EXTENSIONS = {".json", ".tmdl", ".pbir", ".pbism", ".md", ".txt"}


def build_workspace_payload(
    display_name: str,
    description: str,
    capacity_id: str,
) -> dict[str, str]:
    return {
        "displayName": display_name,
        "description": description,
        "capacityId": capacity_id,
    }


def build_lakehouse_payload(
    lakehouse: LakehouseSpec,
    workspace_id: str,
    lakehouse_ids: dict[str, str],
) -> dict[str, Any]:
    parts = [
        _definition_part("lakehouse.metadata.json", {}),
        _definition_part(".platform", _platform_payload("Lakehouse", lakehouse.display_name)),
    ]
    shortcut_definitions = _build_shortcut_definitions(
        lakehouse.shortcuts,
        workspace_id,
        lakehouse_ids,
    )
    if shortcut_definitions:
        parts.insert(1, _definition_part("shortcuts.metadata.json", shortcut_definitions))
    return {
        "displayName": lakehouse.display_name,
        "description": lakehouse.description,
        "creationPayload": {"enableSchemas": lakehouse.enable_schemas},
        "definition": {
            "format": "LakehouseDefinitionV1",
            "parts": parts,
        },
    }


def build_lakehouse_creation_body(payload: dict[str, Any]) -> dict[str, Any]:
    body = {
        "displayName": payload["displayName"],
        "description": payload["description"],
    }
    if payload["creationPayload"].get("enableSchemas") is True:
        body["creationPayload"] = payload["creationPayload"]
    return body


def build_notebook_payload(
    notebook: NotebookSpec,
    workspace_id: str,
    lakehouse_ids: dict[str, str],
) -> dict[str, Any]:
    content = json.loads(notebook.definition_path.read_text(encoding="utf-8"))
    metadata = content.setdefault("metadata", {})
    metadata["dependencies"] = {
        "lakehouse": {
            "default_lakehouse": lakehouse_ids[notebook.default_lakehouse],
            "default_lakehouse_workspace_id": workspace_id,
            "default_lakehouse_name": notebook.default_lakehouse,
        }
    }
    return {
        "displayName": notebook.display_name,
        "description": notebook.description,
        "type": "Notebook",
        "definition": {
            "format": "ipynb",
            "parts": [
                _definition_part("notebook-content.ipynb", content),
                _definition_part(".platform", _platform_payload("Notebook", notebook.display_name)),
            ],
        },
    }


def build_artifact_definition(
    artifact: ArtifactSpec,
    template_values: dict[str, str],
) -> dict[str, Any]:
    parts = []
    seen_paths: set[str] = set()
    for include_path in artifact.include_paths:
        for file_path in sorted(artifact.definition_root.glob(include_path)):
            if not file_path.is_file():
                continue
            part_path = file_path.relative_to(artifact.definition_root).as_posix()
            if part_path in seen_paths:
                continue
            seen_paths.add(part_path)
            parts.append(
                _file_definition_part(
                    file_path,
                    artifact.definition_root,
                    template_values,
                )
            )
    if ".platform" not in seen_paths:
        parts.append(
            _definition_part(
                ".platform",
                _platform_payload(artifact.item_type, artifact.display_name),
            )
        )
    definition: dict[str, Any] = {"parts": parts}
    if artifact.item_type not in {"Ontology", "DataAgent"} or (
        artifact.item_type == "Ontology" and artifact.definition_format == "TMDL"
    ):
        definition["format"] = artifact.definition_format
    return definition


def build_artifact_create_body(
    artifact: ArtifactSpec,
    definition: dict[str, Any],
    *,
    specialized_endpoint: bool,
) -> dict[str, Any]:
    payload = {
        "displayName": artifact.display_name,
        "description": artifact.description,
        "definition": definition,
    }
    if not specialized_endpoint:
        payload["type"] = artifact.item_type
    return payload


def build_notebook_job_request(
    parameters: tuple[NotebookParameterSpec, ...],
    values: dict[str, Any],
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    notebook_types = {
        "Text": "string",
        "Guid": "string",
        "DateTime": "string",
        "Boolean": "bool",
        "Integer": "int",
        "Number": "float",
    }
    payload: dict[str, dict[str, Any]] = {}
    for parameter in parameters:
        if parameter.name not in values:
            if parameter.required:
                raise ValueError(f"Missing required parameter: {parameter.name}")
            continue
        coerced = _coerce_parameter_value(parameter, values[parameter.name])
        payload[parameter.name] = {
            "type": notebook_types[parameter.type_name],
            "value": coerced,
        }
    return {"executionData": {"parameters": payload}}


def validate_item_display_name(item_type: str, display_name: str) -> None:
    if not display_name.strip():
        raise ValueError("Item display name cannot be empty.")
    if item_type == "Ontology" and not ONTOLOGY_NAME_PATTERN.fullmatch(display_name):
        raise ValueError(
            "Ontology display names must start with a letter and contain only letters, "
            "numbers, and underscores."
        )


def _build_shortcut_definitions(
    shortcuts: tuple[ShortcutSpec, ...],
    workspace_id: str,
    lakehouse_ids: dict[str, str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for shortcut in shortcuts:
        source_lakehouse_id = lakehouse_ids.get(shortcut.source_lakehouse)
        if source_lakehouse_id is None:
            raise ValueError(
                "Shortcut "
                f"{shortcut.name} references unknown lakehouse "
                f"{shortcut.source_lakehouse!r}."
            )
        result.append(
            {
                "name": shortcut.name,
                "path": shortcut.path,
                "target": {
                    "type": "OneLake",
                    "oneLake": {
                        "workspaceId": workspace_id or ZERO_UUID,
                        "itemId": source_lakehouse_id,
                        "path": shortcut.source_path,
                    },
                },
            }
        )
    return result


def _coerce_parameter_value(parameter: NotebookParameterSpec, value: Any) -> Any:
    if parameter.allowed_values and str(value) not in parameter.allowed_values:
        raise ValueError(
            f"Parameter {parameter.name} must be one of {parameter.allowed_values}, "
            f"found {value!r}."
        )
    if parameter.type_name == "Text":
        if not isinstance(value, str):
            raise ValueError(f"Parameter {parameter.name} must be a string.")
        return value
    if parameter.type_name == "Boolean":
        if not isinstance(value, bool):
            raise ValueError(f"Parameter {parameter.name} must be a boolean.")
        return value
    if parameter.type_name == "Integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"Parameter {parameter.name} must be an integer.")
        return value
    if parameter.type_name == "Number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"Parameter {parameter.name} must be numeric.")
        return value
    if parameter.type_name == "Guid":
        if not isinstance(value, str) or not _is_guid(value):
            raise ValueError(f"Parameter {parameter.name} must be a GUID string.")
        return value
    if parameter.type_name == "DateTime":
        if isinstance(value, datetime):
            return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not isinstance(value, str) or not _looks_like_utc_datetime(value):
            raise ValueError(f"Parameter {parameter.name} must be a UTC ISO-8601 datetime string.")
        return value
    raise ValueError(f"Unsupported parameter type: {parameter.type_name}")


def _definition_part(path: str, payload: Any) -> dict[str, str]:
    return {
        "path": path,
        "payload": _encode_payload(payload),
        "payloadType": "InlineBase64",
    }


def _file_definition_part(
    file_path: Path,
    definition_root: Path,
    template_values: dict[str, str],
) -> dict[str, str]:
    relative_path = file_path.relative_to(definition_root).as_posix()
    suffix = file_path.suffix.lower()
    if suffix in TEXT_EXTENSIONS or file_path.name.startswith("definition"):
        text = file_path.read_text(encoding="utf-8")
        rendered = _render_template(text, template_values)
        return _definition_part(relative_path, rendered)
    return {
        "path": relative_path,
        "payload": base64.b64encode(file_path.read_bytes()).decode("utf-8"),
        "payloadType": "InlineBase64",
    }


def _render_template(text: str, template_values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in template_values:
            raise ValueError(f"Missing template value for {key!r}.")
        return template_values[key]

    return TEMPLATE_PATTERN.sub(replace, text)


def _encode_payload(payload: Any) -> str:
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, sort_keys=True)
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def _platform_payload(item_type: str, display_name: str) -> dict[str, Any]:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
        "gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {
            "type": item_type,
            "displayName": display_name,
        },
        "config": {
            "version": "2.0",
            "logicalId": ZERO_UUID,
        },
    }


def _is_guid(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            value,
        )
    )


def _looks_like_utc_datetime(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True
