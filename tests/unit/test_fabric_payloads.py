from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fabric.artifacts import (
    LakehouseSpec,
    NotebookParameterSpec,
    NotebookSpec,
    ShortcutSpec,
)
from fabric.payloads import (
    build_lakehouse_payload,
    build_notebook_job_request,
    build_notebook_payload,
    validate_item_display_name,
)


def test_build_lakehouse_payload_includes_shortcuts() -> None:
    lakehouse = LakehouseSpec(
        display_name="HotelGuestServices",
        description="guest",
        default_schema="dbo",
        enable_schemas=False,
        authoritative_tables=("guests",),
        shortcuts=(
            ShortcutSpec(
                name="ops_properties",
                path="Tables",
                source_lakehouse="HotelOperations",
                source_path="Tables/properties",
            ),
        ),
    )

    payload = build_lakehouse_payload(
        lakehouse,
        workspace_id="workspace-id",
        lakehouse_ids={"HotelOperations": "operations-id"},
    )

    assert payload["displayName"] == "HotelGuestServices"
    parts = payload["definition"]["parts"]
    assert [part["path"] for part in parts] == [
        "lakehouse.metadata.json",
        "shortcuts.metadata.json",
        ".platform",
    ]
    shortcut_payload = json.loads(base64.b64decode(parts[1]["payload"]).decode("utf-8"))
    assert shortcut_payload[0]["target"]["oneLake"]["itemId"] == "operations-id"


def test_build_notebook_payload_uses_expected_definition_part(tmp_path: Path) -> None:
    notebook_path = tmp_path / "example.ipynb"
    notebook_path.write_text(
        '{"cells":[],"metadata":{"language_info":{"name":"python"}},"nbformat":4,"nbformat_minor":5}',
        encoding="utf-8",
    )
    notebook = NotebookSpec(
        display_name="ExampleNotebook",
        description="desc",
        definition_path=notebook_path,
        contract_key="Contract",
        default_lakehouse="HotelGuestServices",
    )

    payload = build_notebook_payload(notebook)

    assert payload["type"] == "Notebook"
    assert payload["definition"]["format"] == "ipynb"
    assert payload["definition"]["parts"][0]["path"] == "artifact.content.ipynb"


def test_build_notebook_job_request_validates_types() -> None:
    parameters = (
        NotebookParameterSpec(
            name="confirmation_id",
            type_name="Guid",
            required=True,
            description="id",
        ),
        NotebookParameterSpec(
            name="request_timestamp_utc",
            type_name="DateTime",
            required=True,
            description="when",
        ),
    )

    payload = build_notebook_job_request(
        parameters,
        {
            "confirmation_id": "00000000-0000-0000-0000-000000000001",
            "request_timestamp_utc": datetime(2026, 7, 11, 18, 0, tzinfo=UTC),
        },
    )

    assert payload["parameters"][1]["value"] == "2026-07-11T18:00:00Z"


def test_validate_item_display_name_rejects_ontology_spaces() -> None:
    with pytest.raises(ValueError, match="Ontology"):
        validate_item_display_name("Ontology", "Hotel Operations Ontology")
