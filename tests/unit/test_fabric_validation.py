from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import fabric.validation as fabric_validation
import pytest
from fabric.artifacts import FabricTopology, load_notebook_contracts
from fabric.validation import validate_artifact_spec, validate_topology

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_repository_fabric_topology_is_valid() -> None:
    topology = FabricTopology.from_file(
        REPOSITORY_ROOT / "fabric" / "topology.json",
        REPOSITORY_ROOT,
    )
    contracts = load_notebook_contracts(REPOSITORY_ROOT / "fabric" / "notebooks" / "contracts.json")

    assert validate_topology(topology, contracts) == []


def test_fabric_topology_rejects_previous_tenant_capacity() -> None:
    topology = FabricTopology.from_file(
        REPOSITORY_ROOT / "fabric" / "topology.json",
        REPOSITORY_ROOT,
    )
    contracts = load_notebook_contracts(REPOSITORY_ROOT / "fabric" / "notebooks" / "contracts.json")
    assert topology.workspace.capacity_id == "de2ca443-9cac-49b5-8caa-567682a553c1"
    previous = replace(
        topology,
        workspace=replace(
            topology.workspace,
            capacity_id="ddd12f72-ecd8-471d-a03e-345e8960d6f4",
        ),
    )

    problems = validate_topology(previous, contracts)

    assert any("Capacity ID must be de2ca443-9cac-49b5-8caa-567682a553c1" in p for p in problems)


def test_repository_notebook_code_cells_compile() -> None:
    notebook_dir = REPOSITORY_ROOT / "fabric" / "notebooks"
    for notebook_path in notebook_dir.glob("*.ipynb"):
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        for cell in notebook.get("cells", []):
            if cell.get("cell_type") == "code":
                compile("".join(cell.get("source", [])), str(notebook_path), "exec")


def test_v2_ontology_requires_default_namespace(tmp_path: Path) -> None:
    topology = FabricTopology.from_file(REPOSITORY_ROOT / "fabric/topology.json", REPOSITORY_ROOT)
    original = topology.blueprints["ontology"]
    root = tmp_path / "ontology-v2"
    shutil.copytree(original.definition_root, root)
    (root / "namespaces/default.tmdl").unlink()

    problems = validate_artifact_spec("ontology", replace(original, definition_root=root))

    assert any("missing namespaces/default.tmdl" in problem for problem in problems)


def test_data_agent_publish_verifies_existing_sources_without_rewriting_them() -> None:
    notebook_path = REPOSITORY_ROOT / "fabric" / "notebooks" / "data_agent_runtime_publish.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    source = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook.get("cells", [])
        if cell.get("cell_type") == "code"
    )

    assert "FabricDataAgentManagement" in source
    assert "management.delete_staging_datasource" not in source
    assert "management.add_staging_datasource" not in source
    assert "require_native_readiness" in source
    assert "verify_existing_source(matches[0], display_name, config)" in source
    assert "lakehouse_source_tables(datasource)" in source
    assert "synchronize_source_examples" in source
    assert "is missing required tables" in source
    assert "management.publish_staging" in source
    assert "all 20 properties, including zero-count properties" in source
    assert "status IN ('future', 'arriving')" in source
    assert "official property name" in source
    assert "run_isolation_checks" in source
    assert "/v1/mcp/workspaces/{workspace_id}/dataagents/{data_agent_id}/agent" in source
    assert "known-folio-minibar-dispute" in source
    assert "requires at least 10 distinct native example queries" in source
    assert 'base + "/staging/publish"' not in source


@pytest.mark.parametrize(
    "marker",
    [
        "verify_existing_source",
        "require_native_readiness",
        "missing or mismatched native source metadata",
        "requires at least 10 distinct native example queries",
    ],
)
def test_data_agent_quality_gate_requires_preservation_checks(
    monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    topology = FabricTopology.from_file(
        REPOSITORY_ROOT / "fabric" / "topology.json", REPOSITORY_ROOT
    )
    read_runner = fabric_validation._read_runner_text
    monkeypatch.setattr(
        fabric_validation,
        "_read_runner_text",
        lambda path: read_runner(path).replace(marker, "removed-readback-check"),
    )
    problems = validate_artifact_spec("dataAgent", topology.blueprints["dataAgent"])
    assert any(f"is missing {marker!r}" in problem for problem in problems)


def _copied_data_agent(tmp_path: Path):
    topology = FabricTopology.from_file(
        REPOSITORY_ROOT / "fabric" / "topology.json",
        REPOSITORY_ROOT,
    )
    original = topology.blueprints["dataAgent"]
    copied_root = tmp_path / "draft"
    shutil.copytree(original.definition_root, copied_root)
    return replace(original, definition_root=copied_root), copied_root


def test_data_agent_quality_gate_manifest_is_required(tmp_path: Path) -> None:
    artifact, copied_root = _copied_data_agent(tmp_path)
    (copied_root / "quality-gates.json").unlink()

    problems = validate_artifact_spec("dataAgent", artifact)

    assert any("quality gates" in problem for problem in problems)


def test_data_agent_rejects_weak_source_contracts(tmp_path: Path) -> None:
    artifact, copied_root = _copied_data_agent(tmp_path)
    source_dir = copied_root / "Files" / "Config" / "draft" / "lakehouse-HotelGuestServices"
    datasource_path = source_dir / "datasource.json"
    datasource = json.loads(datasource_path.read_text(encoding="utf-8"))
    datasource["userDescription"] = "Guest data."
    datasource["dataSourceInstructions"] = datasource["dataSourceInstructions"].replace(
        "`balance`", "balance"
    )
    datasource_path.write_text(json.dumps(datasource), encoding="utf-8")
    fewshots_path = source_dir / "fewshots.json"
    fewshots = json.loads(fewshots_path.read_text(encoding="utf-8"))
    fewshots["fewShots"] = fewshots["fewShots"][:9]
    fewshots_path.write_text(json.dumps(fewshots), encoding="utf-8")

    problems = validate_artifact_spec("dataAgent", artifact)

    assert any("userDescription must contain at least" in problem for problem in problems)
    assert any("missing exposed table/field 'balance'" in problem for problem in problems)
    assert any("at least 10 example queries" in problem for problem in problems)


def test_data_agent_rejects_runtime_presentation_labels(tmp_path: Path) -> None:
    artifact, copied_root = _copied_data_agent(tmp_path)
    datasource_path = (
        copied_root / "Files" / "Config" / "draft" / "lakehouse-HotelOperations" / "datasource.json"
    )
    datasource = json.loads(datasource_path.read_text(encoding="utf-8"))
    datasource["userDescription"] = (
        "Authoritative property and operations source containing synthetic hotel records "
        "for governed business questions."
    )
    datasource_path.write_text(json.dumps(datasource), encoding="utf-8")

    problems = validate_artifact_spec("dataAgent", artifact)

    assert any("prohibited presentation term 'synthetic'" in problem for problem in problems)


def test_data_agent_requires_routing_acronyms_fixtures_and_isolation(
    tmp_path: Path,
) -> None:
    artifact, copied_root = _copied_data_agent(tmp_path)
    stage_path = copied_root / "Files" / "Config" / "draft" / "stage_config.json"
    stage = json.loads(stage_path.read_text(encoding="utf-8"))
    stage["aiInstructions"] = "Route HotelOperations."
    stage_path.write_text(json.dumps(stage), encoding="utf-8")
    quality_path = copied_root / "quality-gates.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    quality["businessFixtures"] = []
    quality["isolationChecks"] = []
    quality_path.write_text(json.dumps(quality), encoding="utf-8")

    problems = validate_artifact_spec("dataAgent", artifact)

    assert any("detailed routing guidance" in problem for problem in problems)
    assert any("Acronym compendium" in problem for problem in problems)
    assert any("known business fixture" in problem for problem in problems)
    assert any("published-agent isolation checks" in problem for problem in problems)


def test_validation_rejects_non_ops_shortcuts(tmp_path: Path) -> None:
    (tmp_path / "fabric" / "semantic-model" / "definition" / "tables").mkdir(parents=True)
    (tmp_path / "fabric" / "report" / "definition" / "pages").mkdir(parents=True)
    (tmp_path / "fabric" / "ontology" / "EntityTypes" / "1").mkdir(parents=True)
    (tmp_path / "fabric" / "ontology" / "RelationshipTypes" / "1").mkdir(parents=True)
    (
        tmp_path
        / "fabric"
        / "data-agent"
        / "draft"
        / "Files"
        / "Config"
        / "draft"
        / "lakehouse-Test"
    ).mkdir(parents=True)

    (tmp_path / "fabric" / "semantic-model" / "definition.pbism").write_text("{}", encoding="utf-8")
    (tmp_path / "fabric" / "semantic-model" / "definition" / "database.tmdl").write_text(
        "database Test\n", encoding="utf-8"
    )
    (tmp_path / "fabric" / "semantic-model" / "definition" / "model.tmdl").write_text(
        "{{HOTEL_GUEST_SERVICES_LAKEHOUSE_ID}}\n", encoding="utf-8"
    )
    (tmp_path / "fabric" / "semantic-model" / "definition" / "relationships.tmdl").write_text(
        "relationship r\n", encoding="utf-8"
    )
    for name in ["A.tmdl", "B.tmdl", "C.tmdl", "D.tmdl", "E.tmdl"]:
        (tmp_path / "fabric" / "semantic-model" / "definition" / "tables" / name).write_text(
            "mode: directLake\n", encoding="utf-8"
        )

    (tmp_path / "fabric" / "report" / "definition.pbir").write_text(
        json.dumps(
            {
                "datasetReference": {
                    "byConnection": {"connectionString": "semanticmodelid={{SEMANTICMODEL_ID}}"}
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "fabric" / "report" / "definition" / "pages" / "pages.json").write_text(
        json.dumps({"pageOrder": ["a", "b", "c", "d", "e", "f"]}), encoding="utf-8"
    )
    for page in ["a", "b", "c", "d", "e", "f"]:
        (tmp_path / "fabric" / "report" / "definition" / "pages" / page).mkdir(
            parents=True, exist_ok=True
        )
        (tmp_path / "fabric" / "report" / "definition" / "pages" / page / "page.json").write_text(
            "{}", encoding="utf-8"
        )
        (tmp_path / "fabric" / "report" / "definition" / "pages" / page / "visuals" / "v").mkdir(
            parents=True
        )
        (
            tmp_path
            / "fabric"
            / "report"
            / "definition"
            / "pages"
            / page
            / "visuals"
            / "v"
            / "visual.json"
        ).write_text("{}", encoding="utf-8")

    (tmp_path / "fabric" / "ontology" / "definition.json").write_text("{}", encoding="utf-8")
    for path in [
        tmp_path / "fabric" / "ontology" / "EntityTypes" / "1" / "definition.json",
        tmp_path / "fabric" / "ontology" / "EntityTypes" / "2" / "definition.json",
        tmp_path / "fabric" / "ontology" / "EntityTypes" / "3" / "definition.json",
        tmp_path / "fabric" / "ontology" / "EntityTypes" / "4" / "definition.json",
        tmp_path / "fabric" / "ontology" / "EntityTypes" / "5" / "definition.json",
        tmp_path / "fabric" / "ontology" / "RelationshipTypes" / "1" / "definition.json",
        tmp_path / "fabric" / "ontology" / "RelationshipTypes" / "2" / "definition.json",
        tmp_path / "fabric" / "ontology" / "RelationshipTypes" / "3" / "definition.json",
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    (
        tmp_path / "fabric" / "data-agent" / "draft" / "Files" / "Config" / "data_agent.json"
    ).write_text("{}", encoding="utf-8")
    (
        tmp_path
        / "fabric"
        / "data-agent"
        / "draft"
        / "Files"
        / "Config"
        / "draft"
        / "stage_config.json"
    ).write_text("{}", encoding="utf-8")
    (
        tmp_path
        / "fabric"
        / "data-agent"
        / "draft"
        / "Files"
        / "Config"
        / "draft"
        / "lakehouse-Test"
        / "datasource.json"
    ).write_text("{}", encoding="utf-8")
    (
        tmp_path
        / "fabric"
        / "data-agent"
        / "draft"
        / "Files"
        / "Config"
        / "draft"
        / "lakehouse-Test"
        / "fewshots.json"
    ).write_text("{}", encoding="utf-8")
    for folder in ["lakehouse-Test2", "semantic_model-Test", "graph-Test"]:
        base = tmp_path / "fabric" / "data-agent" / "draft" / "Files" / "Config" / "draft" / folder
        base.mkdir(parents=True, exist_ok=True)
        (base / "datasource.json").write_text("{}", encoding="utf-8")
        (base / "fewshots.json").write_text("{}", encoding="utf-8")

    (tmp_path / "fabric" / "notebooks").mkdir(parents=True)
    (tmp_path / "fabric" / "notebooks" / "example.ipynb").write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "metadata": {"tags": ["parameters"]},
                        "outputs": [],
                        "execution_count": None,
                        "source": ["workspace_id = 'x'\n"],
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "fabric" / "notebooks" / "contracts.json").write_text(
        json.dumps(
            {
                "ExampleContract": {
                    "parameters": [
                        {
                            "name": "workspace_id",
                            "type": "Text",
                            "required": True,
                            "description": "workspace",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    for manifest_path, payload in {
        "fabric/semantic-model/blueprint.json": {
            "displayName": "HotelOperationsModel",
            "description": "desc",
            "itemType": "SemanticModel",
            "definitionFormat": "TMDL",
            "definitionRoot": "fabric/semantic-model",
            "includePaths": ["definition.pbism", "definition/**"],
            "deployable": True,
        },
        "fabric/report/blueprint.json": {
            "displayName": "HotelOperationsReport",
            "description": "desc",
            "itemType": "Report",
            "definitionFormat": "PBIR",
            "definitionRoot": "fabric/report",
            "includePaths": ["definition.pbir", "definition/**"],
            "deployable": True,
        },
        "fabric/ontology/blueprint.json": {
            "displayName": "HotelOperationsOntology",
            "description": "desc",
            "itemType": "Ontology",
            "definitionFormat": "JSON",
            "definitionRoot": "fabric/ontology",
            "includePaths": ["definition.json", "EntityTypes/**", "RelationshipTypes/**"],
            "deployable": True,
        },
        "fabric/data-agent/draft/agent.blueprint.json": {
            "displayName": "HotelOperationsAgent",
            "description": "desc",
            "itemType": "DataAgent",
            "definitionFormat": "JSON",
            "definitionRoot": "fabric/data-agent/draft",
            "includePaths": ["Files/Config/**"],
            "deployable": True,
        },
    }.items():
        path = tmp_path / manifest_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    (tmp_path / "fabric" / "topology.json").write_text(
        json.dumps(
            {
                "workspace": {
                    "displayName": "HotelAgent.Workspace",
                    "description": "ok",
                    "capacityId": "24f6590d-413b-4d9f-9c2b-601d753eda94",
                    "capacityRegion": "East US 2",
                },
                "lakehouses": [
                    {
                        "displayName": "HotelOperations",
                        "description": "ops",
                        "defaultSchema": "dbo",
                        "enableSchemas": False,
                        "authoritativeTables": ["properties"],
                        "shortcuts": [],
                    },
                    {
                        "displayName": "HotelGuestServices",
                        "description": "guest",
                        "defaultSchema": "dbo",
                        "enableSchemas": False,
                        "authoritativeTables": ["guests"],
                        "shortcuts": [
                            {
                                "name": "properties_shortcut",
                                "path": "Tables",
                                "sourceLakehouse": "HotelOperations",
                                "sourcePath": "Tables/properties",
                            }
                        ],
                    },
                ],
                "notebooks": [
                    {
                        "displayName": "ExampleNotebook",
                        "description": "desc",
                        "definitionPath": "fabric/notebooks/example.ipynb",
                        "contractKey": "ExampleContract",
                        "defaultLakehouse": "HotelGuestServices",
                    }
                ],
                "blueprints": {
                    "semanticModel": {
                        "displayName": "HotelOperationsModel",
                        "path": "fabric/semantic-model/blueprint.json",
                        "deployable": True,
                    },
                    "report": {
                        "displayName": "HotelOperationsReport",
                        "path": "fabric/report/blueprint.json",
                        "deployable": True,
                    },
                    "ontology": {
                        "displayName": "HotelOperationsOntology",
                        "path": "fabric/ontology/blueprint.json",
                        "deployable": True,
                    },
                    "dataAgent": {
                        "displayName": "HotelOperationsAgent",
                        "path": "fabric/data-agent/draft/agent.blueprint.json",
                        "deployable": True,
                    },
                },
                "contractFile": "fabric/notebooks/contracts.json",
            }
        ),
        encoding="utf-8",
    )

    topology = FabricTopology.from_file(tmp_path / "fabric" / "topology.json", tmp_path)
    contracts = load_notebook_contracts(tmp_path / "fabric" / "notebooks" / "contracts.json")

    problems = validate_topology(topology, contracts)

    assert any("ops_" in problem for problem in problems)
