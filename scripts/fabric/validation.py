from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from fabric.artifacts import (
    SUPPORTED_PARAMETER_TYPES,
    ArtifactSpec,
    FabricTopology,
    NotebookParameterSpec,
)
from fabric.payloads import validate_item_display_name

EXPECTED_CAPACITY_ID = "24f6590d-413b-4d9f-9c2b-601d753eda94"
EXPECTED_REGION = "East US 2"
EXPECTED_WORKSPACE_NAME = "HotelAgent.Workspace"
EXPECTED_LAKEHOUSE_NAMES = {"HotelOperations", "HotelGuestServices"}
EXPECTED_BLUEPRINT_KEYS = {"semanticModel", "report", "ontology", "dataAgent"}


def validate_topology(
    topology: FabricTopology,
    contracts: dict[str, tuple[NotebookParameterSpec, ...]],
) -> list[str]:
    problems: list[str] = []
    if topology.workspace.display_name != EXPECTED_WORKSPACE_NAME:
        problems.append(
            f"Workspace name must be {EXPECTED_WORKSPACE_NAME}, "
            f"found {topology.workspace.display_name}."
        )
    if topology.workspace.capacity_id != EXPECTED_CAPACITY_ID:
        problems.append(
            f"Capacity ID must be {EXPECTED_CAPACITY_ID}, found {topology.workspace.capacity_id}."
        )
    if topology.workspace.capacity_region != EXPECTED_REGION:
        problems.append(
            f"Capacity region must be {EXPECTED_REGION}, "
            f"found {topology.workspace.capacity_region}."
        )

    lakehouse_names = {lakehouse.display_name for lakehouse in topology.lakehouses}
    if lakehouse_names != EXPECTED_LAKEHOUSE_NAMES:
        problems.append(
            "Topology must define exactly HotelOperations and HotelGuestServices lakehouses."
        )
    if len(topology.lakehouses) != 2:
        problems.append("Topology must define exactly two authoritative lakehouses.")

    for lakehouse in topology.lakehouses:
        try:
            validate_item_display_name("Lakehouse", lakehouse.display_name)
        except ValueError as error:
            problems.append(str(error))
        if not lakehouse.authoritative_tables:
            problems.append(
                f"Lakehouse {lakehouse.display_name} must declare authoritative tables."
            )
        if lakehouse.display_name == "HotelOperations" and lakehouse.shortcuts:
            problems.append("HotelOperations should not own inbound ops_ shortcuts.")
        if lakehouse.display_name == "HotelGuestServices":
            for shortcut in lakehouse.shortcuts:
                if not shortcut.name.startswith("ops_"):
                    problems.append(
                        f"Shortcut {shortcut.name} must use the ops_ prefix in HotelGuestServices."
                    )
                if shortcut.source_lakehouse != "HotelOperations":
                    problems.append(
                        f"Shortcut {shortcut.name} must point to HotelOperations, "
                        f"found {shortcut.source_lakehouse}."
                    )
                if shortcut.path != "Tables":
                    problems.append(
                        f"Shortcut {shortcut.name} must land under Tables, found {shortcut.path}."
                    )
                if not shortcut.source_path.startswith("Tables/"):
                    problems.append(f"Shortcut {shortcut.name} must target a OneLake table path.")

    missing_blueprints = EXPECTED_BLUEPRINT_KEYS.difference(topology.blueprints)
    if missing_blueprints:
        problems.append(
            f"Missing future-artifact blueprints: {', '.join(sorted(missing_blueprints))}."
        )
    for name, blueprint in topology.blueprints.items():
        problems.extend(validate_artifact_spec(name, blueprint))

    for notebook in topology.notebooks:
        if not notebook.definition_path.is_file():
            problems.append(f"Notebook source file does not exist: {notebook.definition_path}.")
            continue
        if notebook.contract_key not in contracts:
            problems.append(
                f"Notebook {notebook.display_name} references unknown contract "
                f"{notebook.contract_key}."
            )
            continue
        problems.extend(
            validate_notebook_definition(
                notebook.definition_path,
                contracts[notebook.contract_key],
            )
        )

    if not topology.contract_file.is_file():
        problems.append(f"Notebook contract file does not exist: {topology.contract_file}.")

    problems.extend(validate_contracts(contracts))
    return problems


def validate_contracts(contracts: dict[str, tuple[NotebookParameterSpec, ...]]) -> list[str]:
    problems: list[str] = []
    for contract_name, parameters in contracts.items():
        seen_names: set[str] = set()
        for parameter in parameters:
            if parameter.name.lower() in seen_names:
                problems.append(f"Contract {contract_name} repeats parameter {parameter.name}.")
            seen_names.add(parameter.name.lower())
            if parameter.type_name not in SUPPORTED_PARAMETER_TYPES:
                problems.append(
                    f"Contract {contract_name} uses unsupported type {parameter.type_name}."
                )
    return problems


def validate_notebook_definition(
    notebook_path: Path,
    contract: tuple[NotebookParameterSpec, ...],
) -> list[str]:
    problems: list[str] = []
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    cells = notebook.get("cells", [])
    if not cells:
        return [f"Notebook {notebook_path.name} has no cells."]
    parameter_cells = [
        cell for cell in cells if "parameters" in cell.get("metadata", {}).get("tags", [])
    ]
    if len(parameter_cells) != 1:
        problems.append(f"Notebook {notebook_path.name} must contain exactly one parameters cell.")
        return problems
    parameter_source = "\n".join(parameter_cells[0].get("source", []))
    for parameter in contract:
        if f"{parameter.name} =" not in parameter_source:
            problems.append(
                f"Notebook {notebook_path.name} parameters cell is missing {parameter.name}."
            )
    full_text = notebook_path.read_text(encoding="utf-8")
    if "NotImplementedError" in full_text:
        problems.append(
            f"Notebook {notebook_path.name} still contains NotImplementedError placeholders."
        )
    for cell in cells:
        if cell.get("cell_type") == "code" and (
            "outputs" not in cell or "execution_count" not in cell
        ):
            problems.append(
                f"Notebook {notebook_path.name} has a code cell without outputs/execution_count."
            )
            break
    return problems


def validate_artifact_spec(name: str, artifact: ArtifactSpec) -> list[str]:
    problems: list[str] = []
    if not artifact.manifest_path.is_file():
        return [f"Blueprint {name} is missing file {artifact.manifest_path}."]
    if artifact.deployable and not artifact.item_type:
        problems.append(f"Blueprint {name} must declare itemType when deployable.")
    if not artifact.deployable and not artifact.blocking_reason:
        problems.append(f"Blueprint {name} must declare a blocking reason when not deployable.")
    if artifact.deployable:
        if not artifact.definition_root.is_dir():
            problems.append(
                f"Blueprint {name} definitionRoot does not exist: {artifact.definition_root}."
            )
        if not artifact.include_paths:
            problems.append(f"Blueprint {name} must declare includePaths.")
        for include_path in artifact.include_paths:
            if not list(artifact.definition_root.glob(include_path)):
                problems.append(f"Blueprint {name} include path {include_path!r} matched no files.")
    if artifact.item_type == "SemanticModel":
        problems.extend(_validate_semantic_model(artifact))
    elif artifact.item_type == "Report":
        problems.extend(_validate_report(artifact))
    elif artifact.item_type == "Ontology":
        problems.extend(_validate_ontology(artifact))
    elif artifact.item_type == "DataAgent":
        problems.extend(_validate_data_agent(artifact))
    return problems


def _validate_semantic_model(artifact: ArtifactSpec) -> list[str]:
    problems: list[str] = []
    required = [
        artifact.definition_root / "definition.pbism",
        artifact.definition_root / "definition" / "database.tmdl",
        artifact.definition_root / "definition" / "model.tmdl",
        artifact.definition_root / "definition" / "relationships.tmdl",
    ]
    for path in required:
        if not path.is_file():
            problems.append(f"Semantic model is missing {path}.")
    table_files = list((artifact.definition_root / "definition" / "tables").glob("*.tmdl"))
    if len(table_files) < 5:
        problems.append("Semantic model must define multiple TMDL tables.")
    if table_files:
        all_table_text = "\n".join(path.read_text(encoding="utf-8") for path in table_files)
        if "mode: directLake" not in all_table_text:
            problems.append("Semantic model must use Direct Lake partitions.")
    model_text = (artifact.definition_root / "definition" / "model.tmdl").read_text(
        encoding="utf-8"
    )
    if "{{HOTEL_GUEST_SERVICES_LAKEHOUSE_ID}}" not in model_text:
        problems.append("Semantic model must template the HotelGuestServices lakehouse ID.")
    return problems


def _validate_report(artifact: ArtifactSpec) -> list[str]:
    problems: list[str] = []
    definition_pbir = artifact.definition_root / "definition.pbir"
    if not definition_pbir.is_file():
        return [f"Report is missing {definition_pbir}."]
    pbir = json.loads(definition_pbir.read_text(encoding="utf-8"))
    by_connection = pbir.get("datasetReference", {}).get("byConnection", {})
    if by_connection.get("connectionString") != "semanticmodelid={{SEMANTICMODEL_ID}}":
        problems.append(
            "Report definition.pbir must bind byConnection using the semantic model ID placeholder."
        )
    pages_metadata_path = artifact.definition_root / "definition" / "pages" / "pages.json"
    if not pages_metadata_path.is_file():
        problems.append("Report is missing definition/pages/pages.json.")
        return problems
    pages_metadata = json.loads(pages_metadata_path.read_text(encoding="utf-8"))
    page_order = pages_metadata.get("pageOrder", [])
    if len(page_order) < 6:
        problems.append("Report must define at least six pages.")
    for page_name in page_order:
        page_dir = artifact.definition_root / "definition" / "pages" / page_name
        if not (page_dir / "page.json").is_file():
            problems.append(f"Report page {page_name} is missing page.json.")
            continue
        visuals = list(page_dir.glob("visuals/*/visual.json"))
        if not visuals:
            problems.append(f"Report page {page_name} must define at least one visual.")
    return problems


def _validate_ontology(artifact: ArtifactSpec) -> list[str]:
    problems: list[str] = []
    if not (artifact.definition_root / "definition.json").is_file():
        problems.append("Ontology must contain definition.json.")
    entity_defs = list(artifact.definition_root.glob("EntityTypes/*/definition.json"))
    relationship_defs = list(artifact.definition_root.glob("RelationshipTypes/*/definition.json"))
    if len(entity_defs) < 5:
        problems.append("Ontology must define multiple entity types.")
    if len(relationship_defs) < 3:
        problems.append("Ontology must define relationship types.")
    return problems


def _validate_data_agent(artifact: ArtifactSpec) -> list[str]:
    problems: list[str] = []
    config_root = artifact.definition_root / "Files" / "Config"
    if not (config_root / "data_agent.json").is_file():
        problems.append("Data Agent must contain Files/Config/data_agent.json.")
    if not (config_root / "draft" / "stage_config.json").is_file():
        problems.append("Data Agent must contain Files/Config/draft/stage_config.json.")
    datasource_files = list(config_root.glob("draft/*/datasource.json"))
    if len(datasource_files) < 4:
        problems.append(
            "Data Agent must define draft datasources for both lakehouses, the "
            "semantic model, and the ontology."
        )
    for datasource_file in datasource_files:
        fewshots = datasource_file.parent / "fewshots.json"
        if not fewshots.is_file():
            problems.append(f"Missing fewshots.json beside {datasource_file}.")
        datasource = json.loads(datasource_file.read_text(encoding="utf-8"))
        elements = datasource.get("elements") if isinstance(datasource, dict) else None
        if not isinstance(elements, list):
            problems.append(f"{datasource_file} must contain an elements array.")
            continue
        problems.extend(_validate_data_source_elements(datasource_file, elements))
    return problems


def _validate_data_source_elements(
    datasource_file: Path,
    elements: list[object],
    path: str = "elements",
) -> list[str]:
    problems: list[str] = []
    for index, raw_element in enumerate(elements):
        element_path = f"{path}[{index}]"
        if not isinstance(raw_element, dict):
            problems.append(f"{datasource_file}:{element_path} must be an object.")
            continue
        element_id = raw_element.get("id")
        try:
            UUID(str(element_id))
        except (TypeError, ValueError, AttributeError):
            problems.append(f"{datasource_file}:{element_path}.id must be a UUID.")
        children = raw_element.get("children")
        if children is not None:
            if not isinstance(children, list):
                problems.append(f"{datasource_file}:{element_path}.children must be an array.")
            else:
                problems.extend(
                    _validate_data_source_elements(
                        datasource_file,
                        children,
                        f"{element_path}.children",
                    )
                )
    return problems
