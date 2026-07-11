from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_state(topology_path: Path) -> dict[str, Any]:
    return {
        "topologyPath": str(topology_path),
        "workspace": {},
        "items": {},
        "sourceDiscovery": {},
        "operations": [],
        "pendingArtifacts": {},
    }


def load_state(path: Path, topology_path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_state(topology_path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Deployment state must be a JSON object: {path}")
    return loaded


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record_item(
    state: dict[str, Any],
    item_type: str,
    display_name: str,
    item_id: str,
) -> None:
    items = state.setdefault("items", {})
    assert isinstance(items, dict)
    items[f"{item_type}:{display_name}"] = {
        "id": item_id,
        "type": item_type,
        "displayName": display_name,
    }


def record_workspace(state: dict[str, Any], workspace: dict[str, Any]) -> None:
    state["workspace"] = {
        "displayName": workspace.get("displayName"),
        "id": workspace.get("id"),
        "capacityId": workspace.get("capacityId"),
        "capacityRegion": workspace.get("capacityRegion"),
    }


def append_operation(
    state: dict[str, Any],
    action: str,
    item_type: str,
    display_name: str,
    status: str,
) -> None:
    operations = state.setdefault("operations", [])
    assert isinstance(operations, list)
    operations.append(
        {
            "action": action,
            "itemType": item_type,
            "displayName": display_name,
            "status": status,
        }
    )
