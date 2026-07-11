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


def test_validation_rejects_non_ops_shortcuts(tmp_path: Path) -> None:
    (tmp_path / "fabric" / "semantic-model").mkdir(parents=True)
    (tmp_path / "fabric" / "report").mkdir(parents=True)
    (tmp_path / "fabric" / "ontology").mkdir(parents=True)
    (tmp_path / "fabric" / "data-agent" / "draft").mkdir(parents=True)
    (tmp_path / "fabric" / "notebooks").mkdir(parents=True)
    (tmp_path / "fabric" / "semantic-model" / "blueprint.json").write_text("{}", encoding="utf-8")
    (tmp_path / "fabric" / "report" / "blueprint.json").write_text("{}", encoding="utf-8")
    (tmp_path / "fabric" / "ontology" / "blueprint.json").write_text("{}", encoding="utf-8")
    (tmp_path / "fabric" / "data-agent" / "draft" / "agent.blueprint.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (tmp_path / "fabric" / "notebooks" / "example.ipynb").write_text(
        '{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}',
        encoding="utf-8",
    )
    (tmp_path / "fabric" / "notebooks" / "contracts.json").write_text(
        json.dumps({"ExampleContract": {"parameters": []}}),
        encoding="utf-8",
    )
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
                        "deployable": False,
                        "blockingReason": "schema",
                    },
                    "report": {
                        "displayName": "HotelOperationsReport",
                        "path": "fabric/report/blueprint.json",
                        "deployable": False,
                        "blockingReason": "schema",
                    },
                    "ontology": {
                        "displayName": "HotelOperationsOntology",
                        "path": "fabric/ontology/blueprint.json",
                        "deployable": False,
                        "blockingReason": "schema",
                    },
                    "dataAgent": {
                        "displayName": "HotelOperationsAgent",
                        "path": "fabric/data-agent/draft/agent.blueprint.json",
                        "deployable": False,
                        "blockingReason": "schema",
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
