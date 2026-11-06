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
    definitions = {tool["name"]: tool for tool in source_tool_definitions()}
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


def no_tool_skip_item() -> dict[str, Any]:
    results = [
        {"name": name, "score": 5, "passed": True, "reason": "Observed evidence."}
        for name in METRICS
    ]
    for result in results:
        if result["name"] in {"tool_call_accuracy", "tool_selection", "tool_use_quality"}:
            result.update(score=None, passed=None, reason="Not applicable: no tool calls.")
    composite = next(result for result in results if result["name"] == "tool_use_quality")
    composite["properties"] = {
        "failed_evaluators": [],
        "skipped_evaluators": [
            "tool_call_accuracy", "tool_selection", "tool_input_accuracy",
            "tool_output_utilization", "tool_call_success",
        ],
    }
    results.append({
        "name": "tool_use_quality", "metric": "tool_selection",
        "score": None, "passed": None, "reason": "No tools were selected.",
    })
    return {
        "datasource_item": {
            "case_id": "clarification",
            "evidence_response": json.dumps({"observed_response_output": [
                {"type": "message", "role": "assistant", "content": []},
            ]}),
        },
        "results": results,
    }


def test_native_tool_skips_require_explicit_reasons_and_actual_no_tool_evidence() -> None:
    summary = summarize([no_tool_skip_item()])
    assert summary["incomplete"] == 0
    assert summary["passed"] == 1
    assert summary["not_applicable_rows"] == 1
    assert summary["not_applicable"] == 4
    assert summary["metrics"]["tool_call_accuracy"]["not_applicable"] == 1
    assert summary["metrics"]["tool_call_accuracy"]["passed"] == 0
    assert summary["metrics"]["tool_use_quality/tool_selection"]["not_applicable"] == 1


@pytest.mark.parametrize("output_type", [None, "function_call", "unknown"])
def test_missing_or_conflicting_tool_evidence_cannot_turn_null_scores_into_skips(
    output_type: str | None,
) -> None:
    item = no_tool_skip_item()
    if output_type is None:
        item["datasource_item"].pop("evidence_response")
    else:
        item["datasource_item"]["evidence_response"] = json.dumps({
            "observed_response_output": [{"type": output_type}],
        })
    summary = summarize([item])
    assert summary["incomplete"] == 1
    assert summary["not_applicable"] == 0


def test_quality_metric_null_is_not_a_tool_skip() -> None:
    item = no_tool_skip_item()
    item["results"][0].update(score=None, passed=None, reason="Not applicable: no tools.")
    assert summarize([item])["incomplete"] == 1


def test_composite_skip_cannot_hide_failed_evaluators() -> None:
    item = no_tool_skip_item()
    composite = next(result for result in item["results"] if result["name"] == "tool_use_quality")
    composite["properties"]["failed_evaluators"] = ["tool_selection"]
    summary = summarize([item])
    assert summary["incomplete"] == 1
    assert summary["metrics"]["tool_use_quality"]["incomplete"] == 1
    assert summary["metrics"]["tool_use_quality/tool_selection"]["incomplete"] == 1


def test_unexplained_null_tool_score_is_still_incomplete() -> None:
    item = no_tool_skip_item()
    item["results"][4]["reason"] = "Could not produce a score."
    assert summarize([item])["incomplete"] == 1


def test_native_tool_skip_does_not_hide_an_evaluator_error() -> None:
    item = no_tool_skip_item()
    item["results"][4]["error"] = {"message": "Judge failed"}
    assert summarize([item])["incomplete"] == 1


def test_native_tool_skip_cannot_mask_an_invalid_duplicate_result() -> None:
    item = no_tool_skip_item()
    item["results"].append({
        "name": "tool_call_accuracy", "score": None, "passed": None,
        "reason": "Not applicable: no tool calls.", "error": {"message": "Judge failed"},
    })
    summary = summarize([item])
    assert summary["incomplete"] == 1
    assert summary["metrics"]["tool_call_accuracy"]["incomplete"] == 1
    assert summary["metrics"]["tool_call_accuracy"]["not_applicable"] == 1


def test_composite_skip_requires_native_skipped_evaluator_metadata() -> None:
    item = no_tool_skip_item()
    composite = next(result for result in item["results"] if result["name"] == "tool_use_quality")
    composite.pop("properties")
    assert summarize([item])["incomplete"] == 1


@pytest.mark.parametrize("evidence", ["not JSON", "[]"])
def test_malformed_tool_skip_evidence_is_an_explicit_error(evidence: str) -> None:
    item = no_tool_skip_item()
    item["datasource_item"]["evidence_response"] = evidence
    with pytest.raises(ValueError):
        summarize([item])
