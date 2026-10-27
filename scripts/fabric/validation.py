from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import UUID

from fabric.artifacts import (
    SUPPORTED_PARAMETER_TYPES,
    ArtifactSpec,
    FabricTopology,
    NotebookParameterSpec,
)
from fabric.payloads import validate_item_display_name

EXPECTED_CAPACITY_ID = "de2ca443-9cac-49b5-8caa-567682a553c1"
EXPECTED_REGION = "Central US"
EXPECTED_WORKSPACE_NAME = "HotelAgent.Workspace"
EXPECTED_LAKEHOUSE_NAMES = {"HotelOperations", "HotelGuestServices"}
EXPECTED_BLUEPRINT_KEYS = {"semanticModel", "report", "ontology", "dataAgent"}
MIN_DATA_SOURCE_DESCRIPTION_WORDS = 10
MIN_DATA_SOURCE_INSTRUCTION_WORDS = 25
MIN_EXAMPLE_QUERIES_PER_SOURCE = 10
PROHIBITED_PRESENTATION_PATTERN = re.compile(
    r"\b(?:synthetic|demo|test|sample|fictional|mock|fake)\w*\b",
    re.IGNORECASE,
)


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
    problems.extend(
        _validate_presentation_text(
            topology.workspace.description,
            "Workspace description",
        )
    )

    lakehouse_names = {lakehouse.display_name for lakehouse in topology.lakehouses}
    if lakehouse_names != EXPECTED_LAKEHOUSE_NAMES:
        problems.append(
            "Topology must define exactly HotelOperations and HotelGuestServices lakehouses."
        )
    if len(topology.lakehouses) != 2:
        problems.append("Topology must define exactly two authoritative lakehouses.")

    for lakehouse in topology.lakehouses:
        problems.extend(
            _validate_presentation_text(
                lakehouse.description,
                f"Lakehouse {lakehouse.display_name} description",
            )
        )
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
        problems.extend(
            _validate_presentation_text(
                notebook.description,
                f"Notebook {notebook.display_name} description",
            )
        )
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
        cell_type = cell.get("cell_type")
        cell_source = "".join(cell.get("source", []))
        if cell_type == "markdown":
            problems.extend(
                _validate_presentation_text(
                    cell_source,
                    f"Notebook {notebook_path.name} markdown",
                )
            )
        elif cell_type == "code":
            for line in cell_source.splitlines():
                if "raise " in line:
                    problems.extend(
                        _validate_presentation_text(
                            line,
                            f"Notebook {notebook_path.name} user-facing error",
                        )
                    )
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
        problems.extend(
            _validate_presentation_text(
                artifact.description,
                f"Blueprint {name} description",
            )
        )
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
    if artifact.item_type in {"SemanticModel", "Report", "Ontology"}:
        problems.extend(_validate_artifact_presentation(artifact))
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
    if artifact.definition_format == "TMDL":
        required = (
            ".platform",
            "database.tmdl",
            "model.tmdl",
            "expressions.tmdl",
            "namespaces/default.tmdl",
            "namespaces/usertypes.tmdl",
            "relationships.tmdl",
            "entityRelationships.tmdl",
        )
        for name in required:
            if not (artifact.definition_root / name).is_file():
                problems.append(f"V2 ontology is missing {name}.")
        if problems:
            return problems
        database = (artifact.definition_root / "database.tmdl").read_text(encoding="utf-8")
        if "compatibilityLevel: 1000000" not in database:
            problems.append("V2 ontology must use compatibility level 1000000.")
        entities = list((artifact.definition_root / "entities").glob("*.tmdl"))
        tables = list((artifact.definition_root / "tables").glob("*.tmdl"))
        if len(entities) < 5 or len(tables) != len(entities):
            problems.append("V2 ontology must define typed backing tables for every entity.")
        for path in entities:
            content = path.read_text(encoding="utf-8")
            if "backingTable:" not in content or "keyProperty:" not in content:
                problems.append(f"V2 ontology entity {path.name} requires a backing table and key.")
        relationships = (artifact.definition_root / "entityRelationships.tmdl").read_text(
            encoding="utf-8"
        )
        if len(re.findall(r"^entityRelationship ", relationships, re.MULTILINE)) < 3:
            problems.append("V2 ontology must define native entity relationships.")
        return problems
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
    datasource_files = sorted(config_root.glob("draft/*/datasource.json"))
    if len(datasource_files) < 4:
        problems.append(
            "Data Agent must define draft datasources for both lakehouses, the "
            "semantic model, and the ontology."
        )
    source_names: set[str] = set()
    for datasource_file in datasource_files:
        fewshots = datasource_file.parent / "fewshots.json"
        if not fewshots.is_file():
            problems.append(f"Missing fewshots.json beside {datasource_file}.")
        datasource = json.loads(datasource_file.read_text(encoding="utf-8"))
        source_name = datasource.get("displayName") if isinstance(datasource, dict) else None
        if not isinstance(source_name, str) or not source_name.strip():
            problems.append(f"{datasource_file} must declare a non-empty displayName.")
        else:
            source_names.add(source_name)
        description = datasource.get("userDescription") if isinstance(datasource, dict) else None
        problems.extend(
            _validate_presentation_text(
                description,
                f"{datasource_file} userDescription",
            )
        )
        if _word_count(description) < MIN_DATA_SOURCE_DESCRIPTION_WORDS:
            problems.append(
                f"{datasource_file} userDescription must contain at least "
                f"{MIN_DATA_SOURCE_DESCRIPTION_WORDS} words."
            )
        instructions = (
            datasource.get("dataSourceInstructions") if isinstance(datasource, dict) else None
        )
        problems.extend(
            _validate_presentation_text(
                instructions,
                f"{datasource_file} dataSourceInstructions",
            )
        )
        if _word_count(instructions) < MIN_DATA_SOURCE_INSTRUCTION_WORDS:
            problems.append(
                f"{datasource_file} dataSourceInstructions must contain at least "
                f"{MIN_DATA_SOURCE_INSTRUCTION_WORDS} words."
            )
        if not isinstance(instructions, str) or "data dictionary" not in instructions.lower():
            problems.append(
                f"{datasource_file} dataSourceInstructions must contain a Data dictionary."
            )
        elements = datasource.get("elements") if isinstance(datasource, dict) else None
        if not isinstance(elements, list):
            problems.append(f"{datasource_file} must contain an elements array.")
            continue
        problems.extend(_validate_data_source_elements(datasource_file, elements))
        if isinstance(instructions, str):
            for exposed_name in _exposed_data_source_names(elements):
                if f"`{exposed_name}`" not in instructions:
                    problems.append(
                        f"{datasource_file} Data dictionary is missing exposed "
                        f"table/field {exposed_name!r}."
                    )
        if fewshots.is_file():
            problems.extend(_validate_fewshots(fewshots))
    problems.extend(_validate_data_agent_quality_gates(artifact, config_root, source_names))
    return problems


def _validate_fewshots(fewshots_file: Path) -> list[str]:
    problems: list[str] = []
    raw = json.loads(fewshots_file.read_text(encoding="utf-8"))
    examples = raw.get("fewShots") if isinstance(raw, dict) else None
    if not isinstance(examples, list):
        return [f"{fewshots_file} must contain a fewShots array."]
    if len(examples) < MIN_EXAMPLE_QUERIES_PER_SOURCE:
        problems.append(
            f"{fewshots_file} must contain at least "
            f"{MIN_EXAMPLE_QUERIES_PER_SOURCE} example queries."
        )
    seen_ids: set[str] = set()
    for index, example in enumerate(examples):
        location = f"{fewshots_file}:fewShots[{index}]"
        if not isinstance(example, dict):
            problems.append(f"{location} must be an object.")
            continue
        example_id = str(example.get("id", ""))
        try:
            UUID(example_id)
        except (ValueError, AttributeError):
            problems.append(f"{location}.id must be a UUID.")
        if example_id in seen_ids:
            problems.append(f"{location}.id must be unique.")
        seen_ids.add(example_id)
        if _word_count(example.get("question")) < 3:
            problems.append(f"{location}.question must be a substantial question.")
        if _word_count(example.get("query")) < 3:
            problems.append(f"{location}.query must be a substantial query.")
        problems.extend(
            _validate_presentation_text(example.get("question"), f"{location}.question")
        )
        problems.extend(_validate_presentation_text(example.get("query"), f"{location}.query"))
    return problems


def _validate_data_agent_quality_gates(
    artifact: ArtifactSpec,
    config_root: Path,
    source_names: set[str],
) -> list[str]:
    quality_path = artifact.definition_root / "quality-gates.json"
    if not quality_path.is_file():
        return [f"Data Agent must contain repository quality gates at {quality_path}."]
    raw = json.loads(quality_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return [f"{quality_path} must contain a JSON object."]

    problems: list[str] = []
    configured_minimum = raw.get("minimumExampleQueriesPerSource")
    if (
        not isinstance(configured_minimum, int)
        or configured_minimum < MIN_EXAMPLE_QUERIES_PER_SOURCE
    ):
        problems.append(
            f"{quality_path} minimumExampleQueriesPerSource must be at least "
            f"{MIN_EXAMPLE_QUERIES_PER_SOURCE}."
        )

    stage_config_path = config_root / "draft" / "stage_config.json"
    stage_config = _read_json_object(stage_config_path)
    global_instructions = stage_config.get("aiInstructions")
    if _word_count(global_instructions) < 100:
        problems.append("Data Agent global instructions must contain at least 100 words.")
    if not isinstance(global_instructions, str):
        global_instructions = ""
    problems.extend(
        _validate_presentation_text(global_instructions, "Data Agent global instructions")
    )
    instruction_lines = global_instructions.splitlines()
    for source_name in sorted(source_names):
        routing_lines = [
            line
            for line in instruction_lines
            if source_name.lower() in line.lower()
            and any(
                verb in line.lower() for verb in ("route", "authoritative", "use ", "relationship")
            )
        ]
        if not routing_lines or max(map(_word_count, routing_lines)) < 10:
            problems.append(
                f"Data Agent global instructions need detailed routing guidance for {source_name}."
            )

    acronyms = raw.get("requiredAcronyms")
    if not isinstance(acronyms, dict) or not acronyms:
        problems.append(f"{quality_path} must declare requiredAcronyms.")
        acronyms = {}
    if "acronym compendium" not in global_instructions.lower():
        problems.append("Data Agent global instructions must contain an Acronym compendium.")
    for acronym, expansion in acronyms.items():
        if (
            not isinstance(acronym, str)
            or not acronym.strip()
            or not isinstance(expansion, str)
            or _word_count(expansion) < 2
        ):
            problems.append(f"{quality_path} contains an invalid acronym definition.")
            continue
        if f"`{acronym}`" not in global_instructions or expansion not in global_instructions:
            problems.append(
                f"Data Agent global instructions must define acronym {acronym} as {expansion}."
            )

    business_fixtures = raw.get("businessFixtures")
    isolation_checks = raw.get("isolationChecks")
    if not isinstance(business_fixtures, list) or not business_fixtures:
        problems.append(f"{quality_path} must declare at least one known business fixture.")
        business_fixtures = []
    if not isinstance(isolation_checks, list) or not isolation_checks:
        problems.append(f"{quality_path} must declare published-agent isolation checks.")
        isolation_checks = []
    isolation_by_name: dict[str, dict[str, object]] = {}
    for isolation_check in isolation_checks:
        if not isinstance(isolation_check, dict):
            continue
        isolation_name = isolation_check.get("name")
        if isinstance(isolation_name, str):
            isolation_by_name[isolation_name] = isolation_check
    for fixture in business_fixtures:
        problems.extend(
            _validate_agent_check(
                fixture,
                quality_path,
                source_names,
                expected_mode=None,
            )
        )
        if isinstance(fixture, dict):
            fixture_name = fixture.get("name")
            matching_isolation = (
                isolation_by_name.get(fixture_name) if isinstance(fixture_name, str) else None
            )
            if matching_isolation is None:
                problems.append(
                    f"Business fixture {fixture_name!r} must be covered by an isolation check."
                )
            elif any(
                matching_isolation.get(field) != fixture.get(field)
                for field in ("source", "question", "expectedTerms")
            ):
                problems.append(
                    f"Business fixture {fixture.get('name')!r} and its isolation check must match."
                )
    for isolation_check in isolation_checks:
        problems.extend(
            _validate_agent_check(
                isolation_check,
                quality_path,
                source_names,
                expected_mode="published-agent-direct",
            )
        )

    runner = raw.get("isolationCheckRunner")
    repository_root = _find_repository_root(artifact.manifest_path)
    runner_path = (
        (repository_root / runner).resolve()
        if repository_root is not None and isinstance(runner, str)
        else None
    )
    if runner_path is None or not runner_path.is_file():
        problems.append(f"{quality_path} must reference an existing isolationCheckRunner.")
    else:
        runner_text = _read_runner_text(runner_path)
        required_markers = (
            "run_isolation_checks",
            "/v1/mcp/workspaces/{workspace_id}/dataagents/{data_agent_id}/agent",
            "management.publish_staging",
            "element_dictionary",
            "verify_existing_source",
            "require_native_readiness",
            "missing or mismatched native source metadata",
            "requires at least 10 distinct native example queries",
            "Acronym compendium",
        )
        for marker in required_markers:
            if marker not in runner_text:
                problems.append(f"Isolation check runner {runner_path} is missing {marker!r}.")
        if runner_text.find("management.publish_staging") > runner_text.rfind(
            "run_isolation_checks("
        ):
            problems.append("Published-agent isolation checks must run after publish_staging.")
        for isolation_name, isolation_check in isolation_by_name.items():
            if isolation_name not in runner_text:
                problems.append(
                    f"Isolation check runner {runner_path} is missing check {isolation_name!r}."
                )
                continue
            runner_values = [isolation_check.get("question")]
            expected_terms = isolation_check.get("expectedTerms")
            if isinstance(expected_terms, list):
                runner_values.extend(expected_terms)
            if any(isinstance(value, str) and value not in runner_text for value in runner_values):
                problems.append(
                    f"Isolation check runner {runner_path} does not match check {isolation_name!r}."
                )
    return problems


def _validate_agent_check(
    raw: object,
    quality_path: Path,
    source_names: set[str],
    expected_mode: str | None,
) -> list[str]:
    if not isinstance(raw, dict):
        return [f"{quality_path} verification cases must be objects."]
    problems: list[str] = []
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        problems.append(f"{quality_path} verification cases must have a non-empty name.")
    source = raw.get("source")
    if source not in source_names:
        problems.append(
            f"{quality_path} verification case {name!r} references unknown source {source!r}."
        )
    if _word_count(raw.get("question")) < 5:
        problems.append(f"{quality_path} verification case {name!r} needs a substantial question.")
    expected_terms = raw.get("expectedTerms")
    if (
        not isinstance(expected_terms, list)
        or not expected_terms
        or any(not isinstance(term, str) or not term.strip() for term in expected_terms)
    ):
        problems.append(f"{quality_path} verification case {name!r} needs expectedTerms.")
    if expected_mode is not None and raw.get("mode") != expected_mode:
        problems.append(f"{quality_path} isolation check {name!r} must use mode {expected_mode!r}.")
    problems.extend(
        _validate_presentation_text(
            raw.get("question"),
            f"{quality_path} verification case {name!r} question",
        )
    )
    if isinstance(expected_terms, list):
        for term in expected_terms:
            problems.extend(
                _validate_presentation_text(
                    term,
                    f"{quality_path} verification case {name!r} expected term",
                )
            )
    return problems


def _exposed_data_source_names(elements: list[object]) -> set[str]:
    names: set[str] = set()

    def visit(raw_elements: list[object], selected: bool = True) -> None:
        for raw_element in raw_elements:
            if not isinstance(raw_element, dict):
                continue
            element_selected = selected and raw_element.get("is_selected") is not False
            element_type = str(raw_element.get("type", "")).lower()
            display_name = raw_element.get("display_name")
            if (
                element_selected
                and isinstance(display_name, str)
                and any(
                    marker in element_type
                    for marker in (".table", ".column", ".measure", ".nodetype", ".edgetype")
                )
            ):
                names.add(display_name)
            children = raw_element.get("children")
            if isinstance(children, list):
                visit(children, element_selected)

    visit(elements)
    return names


def _validate_artifact_presentation(artifact: ArtifactSpec) -> list[str]:
    problems: list[str] = []
    seen_paths: set[Path] = set()
    for include_path in artifact.include_paths:
        for file_path in artifact.definition_root.glob(include_path):
            if not file_path.is_file() or file_path in seen_paths:
                continue
            seen_paths.add(file_path)
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            relative_path = file_path.relative_to(artifact.definition_root)
            problems.extend(
                _validate_presentation_text(
                    content,
                    f"{artifact.item_type} definition {relative_path}",
                )
            )
    return problems


def _validate_presentation_text(value: object, location: str) -> list[str]:
    if not isinstance(value, str):
        return []
    match = PROHIBITED_PRESENTATION_PATTERN.search(value)
    if match is None:
        return []
    return [
        f"{location} contains prohibited presentation term {match.group(0)!r}; "
        "present hotel operations as authoritative business data."
    ]


def _word_count(value: object) -> int:
    if not isinstance(value, str):
        return 0
    return len(re.findall(r"[A-Za-z0-9]+(?:[&'-][A-Za-z0-9]+)*", value))


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _read_runner_text(path: Path) -> str:
    if path.suffix != ".ipynb":
        return path.read_text(encoding="utf-8")
    notebook = _read_json_object(path)
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        return ""
    return "\n".join(
        "".join(str(line) for line in cell.get("source", []))
        for cell in cells
        if isinstance(cell, dict) and isinstance(cell.get("source"), list)
    )


def _find_repository_root(path: Path) -> Path | None:
    for parent in path.resolve().parents:
        if (parent / "fabric" / "topology.json").is_file():
            return parent
    return None


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
