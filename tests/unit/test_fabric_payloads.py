from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fabric.artifacts import (
    ArtifactSpec,
    FabricTopology,
    LakehouseSpec,
    NotebookParameterSpec,
    NotebookSpec,
    ShortcutSpec,
)
from fabric.payloads import (
    build_artifact_definition,
    build_lakehouse_creation_body,
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
    creation_body = build_lakehouse_creation_body(payload)
    assert "definition" not in creation_body
    assert "creationPayload" not in creation_body
    payload["creationPayload"]["enableSchemas"] = True
    assert build_lakehouse_creation_body(payload)["creationPayload"] == {"enableSchemas": True}


def test_build_notebook_payload_injects_default_lakehouse_metadata(tmp_path: Path) -> None:
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

    payload = build_notebook_payload(
        notebook,
        workspace_id="workspace-id",
        lakehouse_ids={"HotelGuestServices": "guest-lakehouse-id"},
    )

    part = payload["definition"]["parts"][0]
    assert part["path"] == "notebook-content.ipynb"
    decoded = json.loads(base64.b64decode(part["payload"]).decode("utf-8"))
    assert (
        decoded["metadata"]["dependencies"]["lakehouse"]["default_lakehouse"]
        == "guest-lakehouse-id"
    )


def test_build_artifact_definition_substitutes_placeholders(tmp_path: Path) -> None:
    root = tmp_path / "report"
    (root / "definition" / "pages").mkdir(parents=True)
    (root / "definition.pbir").write_text(
        '{"datasetReference":{"byConnection":{"connectionString":"semanticmodelid={{SEMANTICMODEL_ID}}"}}}',
        encoding="utf-8",
    )
    (root / "definition" / "report.json").write_text(
        '{"name":"{{WORKSPACE_ID}}"}',
        encoding="utf-8",
    )
    artifact = ArtifactSpec(
        display_name="HotelOperationsReport",
        manifest_path=tmp_path / "blueprint.json",
        deployable=True,
        blocking_reason=None,
        item_type="Report",
        definition_format="PBIR",
        definition_root=root,
        include_paths=("definition.pbir", "definition/**"),
        description="desc",
    )

    definition = build_artifact_definition(
        artifact,
        {"SEMANTICMODEL_ID": "model-id", "WORKSPACE_ID": "workspace-id"},
    )

    parts = {part["path"]: part for part in definition["parts"]}
    pbir = json.loads(base64.b64decode(parts["definition.pbir"]["payload"]).decode("utf-8"))
    report = json.loads(
        base64.b64decode(parts["definition/report.json"]["payload"]).decode("utf-8")
    )
    assert (
        pbir["datasetReference"]["byConnection"]["connectionString"] == "semanticmodelid=model-id"
    )
    assert report["name"] == "workspace-id"
    assert ".platform" in parts


def test_build_specialized_artifact_definition_omits_format(tmp_path: Path) -> None:
    root = tmp_path / "ontology"
    root.mkdir()
    (root / "definition.json").write_text("{}", encoding="utf-8")
    artifact = ArtifactSpec(
        display_name="HotelOperationsOntology",
        manifest_path=root / "blueprint.json",
        deployable=True,
        blocking_reason=None,
        item_type="Ontology",
        definition_format="JSON",
        definition_root=root,
        include_paths=("definition.json",),
        description="desc",
    )

    definition = build_artifact_definition(artifact, {})

    assert "format" not in definition


def test_repository_ontology_is_complete_v2_with_typed_sources() -> None:
    repository = Path(__file__).resolve().parents[2]
    topology = FabricTopology.from_file(repository / "fabric/topology.json", repository)
    artifact = topology.blueprints["ontology"]
    definition = build_artifact_definition(
        artifact,
        {
            "FABRIC_SQL_SERVER": "example.datawarehouse.fabric.microsoft.com",
            "HOTEL_OPERATIONS_SQL_ENDPOINT_ID": "operations-sql-id",
            "HOTEL_GUEST_SERVICES_SQL_ENDPOINT_ID": "guest-sql-id",
        },
    )
    parts = {
        part["path"]: base64.b64decode(part["payload"]).decode() for part in definition["parts"]
    }

    assert definition["format"] == "TMDL"
    assert len(definition["parts"]) == len(parts) == 28
    assert len([name for name in parts if name.startswith("entities/")]) == 10
    assert len([name for name in parts if name.startswith("tables/")]) == 10
    assert "compatibilityLevel: 1000000" in parts["database.tmdl"]
    assert "ref namespace default" in parts["model.tmdl"]
    assert "ref namespace usertypes" in parts["model.tmdl"]
    assert parts["entityRelationships.tmdl"].count("\nentityRelationship ") == 8
    assert "property Balance\n\t\tdataType: decimal" in parts["entities/usertypes#Folio.tmdl"]
    assert "column balance\n\t\tdataType: decimal" in parts["tables/folios.tmdl"]
    assert "operations-sql-id" in parts["expressions.tmdl"]
    assert "guest-sql-id" in parts["expressions.tmdl"]
    assert "{{" not in "".join(parts.values())
    assert not any(name.startswith(("EntityTypes/", "RelationshipTypes/")) for name in parts)
    platform = json.loads(parts[".platform"])
    assert platform["config"]["logicalId"] != "00000000-0000-0000-0000-000000000000"


def test_repository_ontology_rejects_missing_sql_binding() -> None:
    repository = Path(__file__).resolve().parents[2]
    topology = FabricTopology.from_file(repository / "fabric/topology.json", repository)

    with pytest.raises(ValueError, match="Missing template value"):
        build_artifact_definition(topology.blueprints["ontology"], {})


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

    request_parameters = payload["executionData"]["parameters"]
    assert request_parameters["confirmation_id"]["type"] == "string"
    assert request_parameters["request_timestamp_utc"]["value"] == "2026-07-11T18:00:00Z"


def test_validate_item_display_name_rejects_ontology_spaces() -> None:
    with pytest.raises(ValueError, match="Ontology"):
        validate_item_display_name("Ontology", "Hotel Operations Ontology")
