from __future__ import annotations

import json
from pathlib import Path

from fabric.artifacts import FabricTopology, load_notebook_contracts
from fabric.validation import validate_topology

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_repository_fabric_topology_is_valid() -> None:
    topology = FabricTopology.from_file(
        REPOSITORY_ROOT / "fabric" / "topology.json",
        REPOSITORY_ROOT,
    )
    contracts = load_notebook_contracts(REPOSITORY_ROOT / "fabric" / "notebooks" / "contracts.json")

    assert validate_topology(topology, contracts) == []


def test_repository_notebook_code_cells_compile() -> None:
    notebook_dir = REPOSITORY_ROOT / "fabric" / "notebooks"
    for notebook_path in notebook_dir.glob("*.ipynb"):
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        for cell in notebook.get("cells", []):
            if cell.get("cell_type") == "code":
                compile("".join(cell.get("source", [])), str(notebook_path), "exec")


def test_data_agent_publish_resynchronizes_lakehouse_schemas() -> None:
    notebook_path = REPOSITORY_ROOT / "fabric" / "notebooks" / "data_agent_runtime_publish.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    source = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook.get("cells", [])
        if cell.get("cell_type") == "code"
    )

    assert "FabricDataAgentManagement" in source
    assert "management.delete_staging_datasource" in source
    assert "management.add_staging_datasource" in source
    assert "management.publish_staging" in source
    assert "all 20 properties, including zero-count properties" in source
    assert "status IN ('future', 'arriving')" in source
    assert "official property name" in source
    assert 'base + "/staging/publish"' not in source


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
