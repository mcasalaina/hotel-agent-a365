from __future__ import annotations

import ast
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "fabric/notebooks/data_agent_runtime_publish.ipynb"


def runtime_helpers() -> SimpleNamespace:
    notebook = json.loads(NOTEBOOK.read_text())
    code = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    )
    names = {
        "all_source_elements",
        "named_source_element",
        "lakehouse_source_tables",
        "discover_source_elements",
        "lakehouse_example_query",
        "synchronize_source_examples",
        "model_example_guidance",
        "draft_definition_sha256",
        "require_native_readiness",
        "verify_existing_source",
    }
    functions = [
        node
        for node in ast.parse(code).body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in functions} == names
    namespace: dict[str, object] = {"re": re, "json": json, "hashlib": hashlib}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(NOTEBOOK), "exec"), namespace)
    return SimpleNamespace(**namespace)


class Source:
    def __init__(self, pages: dict[tuple[str | None, str | None], dict[str, object]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str | None, str | None]] = []

    def get_elements(
        self,
        stage: str,
        root_id: str | None = None,
        continuation_token: str | None = None,
    ) -> dict[str, object]:
        assert stage == "staging"
        self.calls.append((root_id, continuation_token))
        return self.pages[(root_id, continuation_token)]


def test_source_elements_follow_pagination() -> None:
    source = Source(
        {
            (None, None): {"value": [{"id": "first"}], "continuationToken": "next"},
            (None, "next"): {"value": [{"id": "second"}]},
        }
    )
    assert runtime_helpers().all_source_elements(source) == [{"id": "first"}, {"id": "second"}]
    assert source.calls == [(None, None), (None, "next")]


@pytest.mark.parametrize(
    ("second_page", "error"),
    [
        ({"value": [], "continuationToken": "next"}, "repeated a token"),
        (
            {"value": [], "continuationUri": "https://api.fabric.microsoft.com/next"},
            "without its token",
        ),
    ],
)
def test_source_elements_reject_incomplete_or_cyclic_pagination(
    second_page: dict[str, object], error: str
) -> None:
    source = Source(
        {(None, None): {"value": [], "continuationToken": "next"}, (None, "next"): second_page}
    )
    with pytest.raises(RuntimeError, match=error):
        runtime_helpers().all_source_elements(source)


def test_lakehouse_tables_use_names_not_element_order() -> None:
    source = Source(
        {
            (None, None): {
                "value": [
                    {"id": "other", "displayName": "Other"},
                    {"id": "schemas", "displayName": "Schemas"},
                ]
            },
            ("schemas", None): {
                "value": [
                    {"id": "audit", "displayName": "audit"},
                    {"id": "dbo", "displayName": "dbo"},
                ]
            },
            ("dbo", None): {
                "value": [
                    {"id": "views", "displayName": "Views"},
                    {"id": "tables", "displayName": "Tables"},
                ]
            },
            ("tables", None): {"value": [{"id": "properties", "displayName": "properties"}]},
        }
    )
    assert runtime_helpers().lakehouse_source_tables(source) == [
        {"id": "properties", "displayName": "properties"}
    ]
    assert source.calls == [(None, None), ("schemas", None), ("dbo", None), ("tables", None)]


@pytest.mark.parametrize("names", [[], ["Schemas", "Schemas"]])
def test_schema_path_rejects_missing_or_ambiguous_names(names: list[str]) -> None:
    source = Source(
        {
            (None, None): {
                "value": [
                    {"id": str(index), "displayName": name} for index, name in enumerate(names)
                ]
            }
        }
    )
    with pytest.raises(RuntimeError, match="Expected exactly one schema element"):
        runtime_helpers().lakehouse_source_tables(source)


def test_schema_discovery_does_not_request_native_leaf_elements() -> None:
    table = {"id": "table", "displayName": "Property", "type": "Table", "hasSubElements": True}
    column = {"id": "column", "displayName": "Name", "type": "Column", "hasSubElements": False}
    source = Source({(None, None): {"value": [table]}, ("table", None): {"value": [column]}})
    assert runtime_helpers().discover_source_elements(source) == [
        (("Property",), table),
        (("Property", "Name"), column),
    ]
    assert source.calls == [(None, None), ("table", None)]


def test_schema_discovery_surfaces_child_read_failures() -> None:
    source = Source({(None, None): {"value": [{"id": "unavailable", "hasSubElements": True}]}})
    with pytest.raises(KeyError, match="unavailable"):
        runtime_helpers().discover_source_elements(source)


def test_preview_runtime_is_persisted_without_notebook_dependency_downloads() -> None:
    stage = json.loads(
        (ROOT / "fabric/data-agent/draft/Files/Config/draft/stage_config.json").read_text()
    )
    assert stage["experimental"]["enableExperimentalFeatures"] is True
    notebook = json.loads(NOTEBOOK.read_text())
    code = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    )
    assert "subprocess" not in code
    assert "management.get_settings" in code
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            compile(
                "".join(cell["source"]), str(NOTEBOOK), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
            )


def test_lakehouse_examples_use_native_tsql_date_expressions() -> None:
    normalize = runtime_helpers().lakehouse_example_query
    query = "SELECT * FROM reservations WHERE check_in > DATE '2026-09-01';"
    expected = "SELECT * FROM reservations WHERE check_in > CAST('2026-09-01' AS date);"
    assert normalize(query) == expected
    assert normalize(expected) == expected
    assert normalize("SELECT CURRENT_DATE;") == "SELECT CAST(GETDATE() AS date);"
    assert normalize("SELECT property_id FROM properties;") == "SELECT property_id FROM properties;"


class ExampleSource:
    def __init__(self) -> None:
        self.rows = [
            {"id": "retained", "question": "Existing question", "query": "SELECT old_value;"}
        ]
        self.writes: list[str] = []

    def get_fewshots(self, stage: str) -> ExampleSource:
        assert stage == "staging"
        return self

    def to_dict(self, orientation: str) -> list[dict[str, str]]:
        assert orientation == "records"
        return [row.copy() for row in self.rows]

    def add_fewshot(self, question: str, query: str) -> None:
        self.rows.append({"id": "added", "question": question, "query": query})
        self.writes.append("add")

    def update_fewshot(self, identifier: str, *, question: str, query: str) -> None:
        row = next(row for row in self.rows if row["id"] == identifier)
        row.update(question=question, query=query)
        self.writes.append("update")


def test_examples_update_stale_queries_and_remain_idempotent() -> None:
    source = ExampleSource()
    examples = {
        "Existing question": "SELECT DATE '2026-09-01';",
        "New question": "SELECT CURRENT_DATE;",
    }
    synchronize = runtime_helpers().synchronize_source_examples
    assert synchronize(source, examples, lakehouse=True) == 2
    assert source.rows == [
        {
            "id": "retained",
            "question": "Existing question",
            "query": "SELECT CAST('2026-09-01' AS date);",
        },
        {"id": "added", "question": "New question", "query": "SELECT CAST(GETDATE() AS date);"},
    ]
    assert source.writes == ["update", "add"]
    assert synchronize(source, examples, lakehouse=True) == 2
    assert source.writes == ["update", "add"]


def test_examples_reject_duplicate_questions() -> None:
    source = ExampleSource()
    source.rows.append({"id": "duplicate", "question": "existing QUESTION", "query": "SELECT 2;"})
    with pytest.raises(RuntimeError, match="duplicate example questions"):
        runtime_helpers().synchronize_source_examples(source, {"Existing question": "SELECT 1;"})


def test_model_examples_use_explicit_instruction_guidance() -> None:
    examples = {"What is OCC?": 'EVALUATE ROW("OCC", [OCC])'}
    assert runtime_helpers().model_example_guidance(examples) == (
        '## DAX example guidance\n\n### What is OCC?\n\n```dax\nEVALUATE ROW("OCC", [OCC])\n```'
    )


def native_readiness_fixture() -> tuple[dict, dict, dict]:
    definition = {
        "definition": {
            "parts": [{"path": "Files/Config/draft/stage_config.json", "payload": "e30="}]
        }
    }
    sources = {
        "HotelOperations": "operations",
        "HotelGuestServices": "guest-services",
        "HotelOperationsModel": "model",
        "HotelOperationsOntology": "ontology",
    }

    def proof(artifact_id: str) -> dict:
        return {
            "artifactId": artifact_id,
            "verificationMethod": "native-ui-readback",
            "evidenceRef": "retained-native-ui-evidence",
            "evidenceSha256": hashlib.sha256(artifact_id.encode()).hexdigest(),
        }

    evidence = {
        "workspaceId": "workspace",
        "dataAgentId": "agent",
        "draftDefinitionSha256": runtime_helpers().draft_definition_sha256(definition),
        "ontologyContext": proof("ontology"),
        "sqlTopics": {
            "HotelOperations": proof("operations"),
            "HotelGuestServices": proof("guest-services"),
        },
        "modelPrepForAI": {
            **proof("model"),
            "instructionsConfigured": True,
            "verifiedAnswerCount": 11,
        },
    }
    return definition, sources, evidence


def test_native_readiness_requires_bound_external_evidence() -> None:
    definition, sources, evidence = native_readiness_fixture()
    require = runtime_helpers().require_native_readiness
    with pytest.raises(RuntimeError, match="missing or targets another"):
        require("{}", definition, "workspace", "agent", sources)
    assert require(json.dumps(evidence), definition, "workspace", "agent", sources) == evidence
    for key in ("workspaceId", "dataAgentId", "draftDefinitionSha256"):
        changed = deepcopy(evidence)
        changed[key] = "different"
        with pytest.raises(RuntimeError):
            require(json.dumps(changed), definition, "workspace", "agent", sources)


@pytest.mark.parametrize("count", [0, 9, True, "11", None])
def test_stored_model_guidance_cannot_satisfy_native_example_readiness(count: object) -> None:
    definition, sources, evidence = native_readiness_fixture()
    evidence["modelPrepForAI"]["verifiedAnswerCount"] = count
    evidence["modelPrepForAI"]["instructionExampleCount"] = 100
    with pytest.raises(RuntimeError, match="stored instruction guidance does not satisfy"):
        runtime_helpers().require_native_readiness(
            json.dumps(evidence), definition, "workspace", "agent", sources
        )


@pytest.mark.parametrize(
    ("component", "key", "value"),
    [
        ("ontologyContext", "artifactId", "wrong-ontology"),
        ("ontologyContext", "evidenceRef", ""),
        ("ontologyContext", "evidenceSha256", "0" * 64),
        ("modelPrepForAI", "instructionsConfigured", False),
        ("modelPrepForAI", "verificationMethod", "stored-source-instructions"),
    ],
)
def test_native_readiness_rejects_unverified_components(
    component: str, key: str, value: object
) -> None:
    definition, sources, evidence = native_readiness_fixture()
    evidence[component][key] = value
    with pytest.raises(RuntimeError):
        runtime_helpers().require_native_readiness(
            json.dumps(evidence), definition, "workspace", "agent", sources
        )


def test_both_sql_sources_require_topics_evidence() -> None:
    definition, sources, evidence = native_readiness_fixture()
    del evidence["sqlTopics"]["HotelGuestServices"]
    with pytest.raises(RuntimeError, match="Both SQL sources"):
        runtime_helpers().require_native_readiness(
            json.dumps(evidence), definition, "workspace", "agent", sources
        )


class NativeSource(ExampleSource):
    def __init__(self, *, model: bool = False) -> None:
        super().__init__()
        self.stage_reads: list[str] = []
        self.name = "HotelOperationsModel" if model else "HotelOperations"
        self.rows = (
            []
            if model
            else [
                {"id": str(index), "question": f"Native SQL question {index}", "query": "SELECT 1;"}
                for index in range(10)
            ]
        )
        self.elements = [
            {
                "id": "table",
                "displayName": "properties",
                "type": "Table",
                "state": "Available",
                "isSelected": True,
                "hasSubElements": False,
                "description": "Authoritative hotel property business record details",
            }
        ]

    def get_configuration(self, stage: str) -> dict:
        self.stage_reads.append(stage)
        return {
            "displayName": self.name,
            "selectionState": "Selected",
            "description": (
                "Authoritative hotel source for complete operational records "
                "and governed business facts"
            ),
            "instructions": "Complete data dictionary for the connected business schema.",
        }

    def get_elements(
        self,
        stage: str,
        root_id: str | None = None,
        continuation_token: str | None = None,
    ) -> dict:
        self.stage_reads.append(stage)
        assert root_id is None and continuation_token is None
        return {"value": self.elements}

    def get_fewshots(self, stage: str) -> NativeSource:
        self.stage_reads.append(stage)
        return self


@pytest.mark.parametrize("stage", ["staging", "published"])
@pytest.mark.parametrize("model", [False, True])
def test_existing_source_verification_preserves_native_configuration(
    stage: str, model: bool
) -> None:
    source = NativeSource(model=model)
    config = {"artifact_type": "SemanticModel" if model else "Lakehouse", "tables": ["properties"]}
    result = runtime_helpers().verify_existing_source(source, source.name, config, stage=stage)
    assert result["table_count"] == 1
    assert result["fewshot_count"] == (0 if model else 10)
    assert result["native_fewshots_supported"] is not model
    assert source.writes == []
    assert set(source.stage_reads) == {stage}


@pytest.mark.parametrize("problem", ["unselected", "unavailable", "description", "fewshots", "sql"])
def test_existing_source_verification_rejects_native_gaps(problem: str) -> None:
    source = NativeSource()
    if problem == "unselected":
        source.elements[0]["isSelected"] = False
    elif problem == "unavailable":
        source.elements[0]["state"] = "NotAvailable"
    elif problem == "description":
        source.elements[0]["description"] = ""
    elif problem == "fewshots":
        source.rows.pop()
    else:
        source.rows[0]["query"] = "SELECT * FROM properties LIMIT 1;"
    with pytest.raises(RuntimeError):
        runtime_helpers().verify_existing_source(
            source, source.name, {"artifact_type": "Lakehouse", "tables": ["properties"]}
        )
    assert source.writes == []


def test_source_fingerprint_detects_changes_without_relying_on_counts() -> None:
    source = NativeSource()
    verify = runtime_helpers().verify_existing_source
    config = {"artifact_type": "Lakehouse", "tables": ["properties"]}
    original = verify(source, source.name, config)
    source.rows[0]["query"] = "SELECT 2;"
    changed = verify(source, source.name, config)
    assert original["fewshot_count"] == changed["fewshot_count"]
    assert original["configuration_sha256"] != changed["configuration_sha256"]


def test_deploy_adopts_sources_without_resetting_native_ui_configuration() -> None:
    notebook = json.loads(NOTEBOOK.read_text())
    code = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    )
    deploy = next(
        node
        for node in ast.parse(code).body
        if isinstance(node, ast.If) and ast.unparse(node.test) == "publish_mode == 'deploy'"
    )
    calls = [
        node.func.attr
        for node in ast.walk(deploy)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "publish_staging" in calls
    assert not {
        "add_staging_datasource",
        "update_settings",
        "update_configuration",
        "update_element",
        "delete",
        "reset_staging",
    }.intersection(calls)
    publish = next(
        node
        for node in deploy.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "publish" for target in node.targets)
    )
    assert ast.unparse(publish.value) == (
        "management.publish_staging(description=published_description)"
    )


def test_business_descriptions_cover_the_source_table_contract() -> None:
    descriptions = json.loads((ROOT / "fabric/data-agent/schema-descriptions.json").read_text())
    schema = json.loads((ROOT / "data/fixtures/hotel_data_schema.json").read_text())
    assert set(schema["required_tables"]) <= set(descriptions["tables"])
    assert all(len(value.split()) >= 10 for value in descriptions["tables"].values())
    assert all(len(value.split()) >= 5 for value in descriptions["columns"].values())
    assert not re.search(
        r"\b(?:fictional|synthetic|demo)\b", json.dumps(descriptions), flags=re.IGNORECASE
    )


def test_arriving_reservations_follow_the_strict_future_boundary() -> None:
    schema = json.loads((ROOT / "data/fixtures/hotel_data_schema.json").read_text())
    assert schema["temporal_contract"]["arriving"] == "check_in > 2026-09-01"
    assert schema["temporal_contract"]["future"] == "check_in > 2026-09-01"


def test_native_sql_examples_do_not_require_spark_syntax() -> None:
    root = ROOT / "fabric/data-agent/draft/Files/Config/draft"
    normalize = runtime_helpers().lakehouse_example_query
    for path in root.glob("lakehouse-*/fewshots.json"):
        examples = json.loads(path.read_text())["fewShots"]
        assert len(examples) >= 10
        for example in examples:
            query = example["query"]
            assert normalize(query) == query
            assert not re.search(r"\b(?:true|false|LIMIT)\b", query, flags=re.IGNORECASE)


def test_publication_notebook_examples_use_tsql_bit_and_limit_syntax() -> None:
    notebook = json.loads(NOTEBOOK.read_text())
    code = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    )
    assignment = next(
        node
        for node in ast.parse(code).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "source_configs"
            for target in node.targets
        )
    )
    configurations = ast.literal_eval(assignment.value)
    for config in configurations.values():
        for query in config["fewshots"].values():
            assert not re.search(
                r"\bLIMIT\s+\d+|\b=\s*(?:true|false)\b", query, flags=re.IGNORECASE
            )


def test_prepared_topics_use_the_same_reservation_date_field_as_the_contract() -> None:
    topics = (ROOT / "fabric/data-agent/topics/hotel-guest-services.md").read_text()
    assert "Past reservations require `check_in`\nstrictly earlier" in topics
    assert "Upcoming reservations require `check_in` strictly later" in topics


def test_agent_routing_and_iso_date_contract_are_consistent() -> None:
    stage = json.loads(
        (ROOT / "fabric/data-agent/draft/Files/Config/draft/stage_config.json").read_text()
    )
    instructions = (ROOT / "fabric/data-agent/draft/instructions.md").read_text()
    notebook = json.loads(NOTEBOOK.read_text())
    code = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    )
    assignment = next(
        node
        for node in ast.parse(code).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "agent_instructions"
            for target in node.targets
        )
    )
    for text in (stage["aiInstructions"], instructions, ast.literal_eval(assignment.value)):
        assert "semantic context" in text
        assert "authoritative lakehouse SQL sources" in text
        assert "not a query execution endpoint" in text
        assert "Do not claim GQL or GraphModel execution" in text
        assert "ISO 8601 dates" in text
        assert "YYYY-MM-DD" in text
        assert "Preserve the exact source dates." in text


def test_isolation_contract_matches_notebook_and_requests_asserted_identifiers() -> None:
    gates = json.loads((ROOT / "fabric/data-agent/draft/quality-gates.json").read_text())
    notebook = json.loads(NOTEBOOK.read_text())
    code = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    )
    expected_names = {check["name"] for check in gates["isolationChecks"]}
    assignment = next(
        node
        for node in ast.parse(code).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "isolation_checks"
            for target in node.targets
        )
    )
    checks = ast.literal_eval(assignment.value)
    assert {check["name"] for check in checks} == expected_names
    expected = {check["name"]: check for check in gates["isolationChecks"]}
    for check in checks:
        assert check["question"] == expected[check["name"]]["question"]
        assert check["expected_terms"] == expected[check["name"]]["expectedTerms"]
    future = expected["future-maria-reservation-strict-boundary"]
    assert "nearest upcoming" in future["question"]
    assert "reservation identifier" in future["question"]
    assert "official property name" in future["question"]
    assert "internal property identifier" in future["question"]
    assert "Lyrenza Scottsdale Sonoran Resort" in future["expectedTerms"]
