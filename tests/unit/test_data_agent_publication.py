from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "fabric/notebooks/data_agent_runtime_publish.ipynb"
EXAMPLES = {"How many properties are there?": "SELECT COUNT(*) FROM dbo.properties;"}


def notebook_source() -> str:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    )


def example(status: str, reason: str = "") -> dict[str, object]:
    question, query = next(iter(EXAMPLES.items()))
    return {
        "id": "example-id",
        "question": question,
        "query": query,
        "validationStatus": {"value": status, "reason": reason},
    }


def response(examples: list[dict[str, object]], status_code: int = 200) -> Mock:
    result = Mock(status_code=status_code, text="service error")
    result.json.return_value = {"value": examples}
    return result


def validator(client: Mock):
    function = next(
        node
        for node in ast.parse(notebook_source()).body
        if isinstance(node, ast.FunctionDef) and node.name == "validate_examples"
    )
    namespace = {
        "client": client,
        "base": "/v1/workspaces/workspace/dataAgents/agent",
        "data_agent_id": "agent",
        "time": Mock(),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(NOTEBOOK), "exec"), namespace)
    return namespace["validate_examples"]


def test_publication_waits_until_examples_are_valid() -> None:
    client = Mock()
    client.get.side_effect = [
        response([example("Validating")]),
        response([example("Valid")]),
    ]

    assert validator(client)("source", EXAMPLES) == 1
    assert client.get.call_count == 2
    client.patch.assert_not_called()
    source = notebook_source()
    assert source.index("validated_count = validate_examples(") < source.index(
        "publish = management.publish_staging("
    )


def test_publication_retries_transient_connection_failures_without_changing_sql() -> None:
    client = Mock()
    client.get.side_effect = [
        response([example("Invalid", "Failed to connect to server sql.example")]),
        response([example("Validating")]),
        response([example("Valid")]),
    ]
    client.patch.return_value = response([])

    assert validator(client)("source", EXAMPLES) == 1
    client.patch.assert_called_once_with(
        "/v1/workspaces/workspace/dataAgents/agent/staging/datasources/source/fewshots/example-id",
        json={"question": next(iter(EXAMPLES)), "query": next(iter(EXAMPLES.values()))},
        headers={
            "x-ms-ai-aiskill-stage": "sandbox",
            "x-ms-workload-resource-moniker": "agent",
        },
    )


def test_publication_does_not_retry_invalid_sql() -> None:
    client = Mock()
    client.get.return_value = response([example("Invalid", "Invalid column name 'priority'")])

    with pytest.raises(RuntimeError, match="Invalid column name"):
        validator(client)("source", EXAMPLES)
    client.patch.assert_not_called()


def test_publication_bounds_connection_retries() -> None:
    client = Mock()
    client.get.return_value = response(
        [example("Invalid", "Failed to connect to server sql.example")]
    )
    client.patch.return_value = response([])

    with pytest.raises(RuntimeError, match="failed SQL validation"):
        validator(client)("source", EXAMPLES)
    assert client.patch.call_count == 2


def test_publication_times_out_instead_of_accepting_pending_examples() -> None:
    client = Mock()
    client.get.return_value = response([example("Validating")])

    with pytest.raises(TimeoutError, match="did not complete"):
        validator(client)("source", EXAMPLES, max_polls=2)
    assert client.get.call_count == 2


@pytest.mark.parametrize("examples", [[], [example("Valid"), example("Valid")]])
def test_publication_rejects_missing_or_duplicate_examples(
    examples: list[dict[str, object]],
) -> None:
    client = Mock()
    client.get.return_value = response(examples)

    with pytest.raises(RuntimeError, match="do not match"):
        validator(client)("source", EXAMPLES)


def test_publication_surfaces_validation_read_failures() -> None:
    client = Mock()
    client.get.return_value = response([], status_code=503)

    with pytest.raises(RuntimeError, match="validation read failed: 503"):
        validator(client)("source", EXAMPLES)


def test_publication_surfaces_retry_failures() -> None:
    client = Mock()
    client.get.return_value = response(
        [example("Invalid", "Failed to connect to server sql.example")]
    )
    client.patch.return_value = response([], status_code=503)

    with pytest.raises(RuntimeError, match="validation retry failed: 503"):
        validator(client)("source", EXAMPLES)


def test_publication_rejects_unknown_validation_states() -> None:
    client = Mock()
    client.get.return_value = response([example("Unknown")])

    with pytest.raises(RuntimeError, match="Unexpected example validation status"):
        validator(client)("source", EXAMPLES)


def test_repository_lakehouse_examples_use_tsql() -> None:
    queries = []
    for path in (ROOT / "fabric/data-agent/draft/Files/Config/draft").glob(
        "lakehouse-*/fewshots.json"
    ):
        queries.extend(
            example["query"] for example in json.loads(path.read_text(encoding="utf-8"))["fewShots"]
        )
    configuration = next(
        node.value
        for node in ast.parse(notebook_source()).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "source_configs"
            for target in node.targets
        )
    )
    configs = ast.literal_eval(configuration)
    for config in configs.values():
        queries.extend(config["fewshots"].values())

    assert len(queries) == 14
    for query in queries:
        assert not re.search(r"\bDATE\s*'|\bLIMIT\b|=\s*(true|false)\b", query, re.IGNORECASE)
        tables = re.findall(r"\b(?:FROM|JOIN)\s+([\w.]+)", query, re.IGNORECASE)
        assert tables and all(table.startswith("dbo.") for table in tables)
    assert all(
        "country_code" not in query for query in configs["HotelOperations"]["fewshots"].values()
    )
    maintenance = configs["HotelOperations"]["fewshots"][
        "Which maintenance requests are still open for HTL-004?"
    ]
    assert "priority" not in maintenance
    disputes = configs["HotelGuestServices"]["fewshots"][
        "Which open billing disputes have the highest amounts?"
    ]
    assert "TOP (20)" in disputes and "f.currency" in disputes and "JOIN dbo.folios" in disputes
