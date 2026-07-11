from __future__ import annotations

from fabric.artifacts import (
    SUPPORTED_PARAMETER_TYPES,
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
        if not blueprint.path.is_file():
            problems.append(f"Blueprint {name} is missing file {blueprint.path}.")
        if not blueprint.deployable and not blueprint.blocking_reason:
            problems.append(f"Blueprint {name} must declare a blocking reason when not deployable.")

    for notebook in topology.notebooks:
        if not notebook.definition_path.is_file():
            problems.append(f"Notebook source file does not exist: {notebook.definition_path}.")
        if notebook.contract_key not in contracts:
            problems.append(
                f"Notebook {notebook.display_name} references unknown contract "
                f"{notebook.contract_key}."
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
