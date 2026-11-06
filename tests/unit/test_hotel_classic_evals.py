from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from run_hotel_classic_evals import (
    METRICS,
    NAME,
    annotation_schema,
    build_item,
    evaluation_body,
    load_cases,
    source_tool_definitions,
    summarize,
)


def test_dataset_is_twenty_independent_realistic_interactions() -> None:
    cases = load_cases()
    assert len(cases) == 20
    assert len({case["query"] for case in cases}) == 20
    assert all("bank-servicing-agent" not in case["query"].lower() for case in cases)


def test_registered_tool_definitions_preserve_real_signatures() -> None:
    definitions = {tool["function"]["name"]: tool["function"] for tool in source_tool_definitions()}
    assert len(definitions) == 7
    mutation = definitions["manage_reservation"]["parameters"]
    assert mutation["properties"]["room_count"] == {"type": "integer"}
    assert mutation["properties"]["rate_total"] == {"type": "number"}
    assert "reservation_id" not in mutation["required"]
    search = definitions["search_hotel_knowledge"]["parameters"]
    assert search["required"] == ["question"]
    assert len(search["properties"]["property_id"]["anyOf"][0]["enum"]) == 20
    assert definitions["check_work_context_access"]["parameters"]["properties"] == {}
    with pytest.raises(ValueError, match="Unsupported"):
        annotation_schema("Unrecognized")


def completed_response() -> dict[str, Any]:
    return {
        "status": "completed",
        "output": [
            {"type": "function_call", "name": "search_hotel_knowledge", "call_id": "call_real",
             "arguments": '{"question":"parking"}'},
            {"type": "function_call_output", "call_id": "call_real",
             "output": '{"answer":"Valet USD 52 nightly","references":[{"title":"Real source"}]}'},
            {"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "Valet parking costs USD 52 nightly."},
            ]},
        ],
    }


def test_capture_maps_only_observed_answer_and_tool_evidence() -> None:
    response = completed_response()
    item = build_item({"case_id": "example", "query": "Parking?"}, response, [])
    assert item["quality_response"] == "Valet parking costs USD 52 nightly."
    assert json.loads(item["evidence_response"])["observed_response_output"] == response["output"]
    context = json.loads(item["grounding_context"])
    assert context["observed_tool_outputs"] == [response["output"][1]["output"]]
    assert context["observed_user_query"] == "Parking?"
    assert item["quality_query"] == "Parking?"
    response["status"] = "failed"
    with pytest.raises(ValueError, match="not complete"):
        build_item({"case_id": "example"}, response, [])


def test_no_tool_evidence_is_not_fabricated() -> None:
    response = completed_response()
    response["output"] = response["output"][2:]
    item = build_item({"case_id": "example", "query": "Clarify dates?"}, response, [])
    assert json.loads(item["grounding_context"]) == {
        "observed_user_query": "Clarify dates?", "observed_tool_outputs": [],
    }
    assert json.loads(item["evidence_response"])["observed_response_output"] == response["output"]


def test_reference_metrics_and_initialization_are_copied_without_mutation() -> None:
    criteria = [
        {"id": f"generated-{name}", "name": name, "type": "azure_ai_evaluator",
         "evaluator_name": f"builtin.{name}", "evaluator_version": "",
         "data_mapping": {"response": "{{item.evidence_response}}"},
         "initialization_parameters": {"deployment_name": "gpt-5.4-mini"}}
        for name in METRICS
    ]
    reference: dict[str, Any] = {
        "testing_criteria": criteria,
        "data_source_config": {"schema": {"item": {"type": "object"}}},
    }
    original = copy.deepcopy(reference)
    body = evaluation_body(reference, "8")
    assert body["name"] == NAME
    assert reference == original
    assert body["testing_criteria"] == [
        {key: value for key, value in criterion.items() if key != "id"}
        for criterion in criteria
    ]
    reference["testing_criteria"].pop()
    with pytest.raises(ValueError, match="metric list"):
        evaluation_body(reference, "8")


def test_summary_distinguishes_quality_failures_from_execution_errors() -> None:
    results = [
        {"name": name, "score": 5, "passed": True, "reason": "Observed evidence supports this."}
        for name in METRICS
    ]
    good: dict[str, Any] = {"datasource_item": {"case_id": "good"}, "results": results}
    quality_failure = copy.deepcopy(good)
    quality_failure["results"][0]["passed"] = False
    quality_failure["results"][0]["score"] = 1
    error = copy.deepcopy(good)
    error["results"][0]["reason"] = None
    missing = copy.deepcopy(good)
    missing["results"].pop()
    summary = summarize([good, quality_failure, error, missing])
    assert summary["total"] == 4
    assert summary["passed"] == 1
    assert summary["quality_failed"] == 1
    assert summary["incomplete"] == 2


@pytest.mark.parametrize("score", [None, float("nan"), float("inf"), True])
def test_summary_rejects_non_numeric_or_non_finite_scores(score: Any) -> None:
    results = [
        {"name": name, "score": 5, "passed": True, "reason": "Observed evidence."}
        for name in METRICS
    ]
    results[0]["score"] = score
    assert summarize([{"results": results}])["incomplete"] == 1


def test_composite_metric_subscores_remain_separate() -> None:
    results = [
        {"name": name, "metric": name, "score": 5, "passed": True, "reason": "Observed evidence."}
        for name in METRICS
    ]
    results.append({
        "name": "tool_use_quality", "metric": "tool_input_accuracy",
        "score": 1, "passed": False, "reason": "Observed incorrect argument.",
    })
    summary = summarize([{"results": results}])
    assert summary["metrics"]["tool_use_quality"]["passed"] == 1
    assert summary["metrics"]["tool_use_quality/tool_input_accuracy"]["failed"] == 1
    assert summary["quality_failed"] == 1
