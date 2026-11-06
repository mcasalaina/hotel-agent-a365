from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import run_hotel_rubric_eval as runner
from run_hotel_rubric_eval import capture_hosted_responses, load_inputs, summarize


def scored_item(rubric: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "1",
        "datasource_item": {"case_id": "privacy-other-room"},
        "results": [
            {
                "name": rubric["name"],
                "passed": True,
                "score": 1.0,
                "reason": "The response protects the other guest's privacy.",
                "properties": {
                    "dimension_scores": [
                        {
                            "id": dimension["id"],
                            "applicable": True,
                            "score": 5,
                            "reason": "Meets the criterion.",
                        }
                        for dimension in rubric["definition"]["dimensions"]
                    ],
                },
            }
        ],
    }


def test_reviewed_rubric_has_depth_positive_scoring_and_coverage() -> None:
    rubric, cases = load_inputs(runner.ROOT / "evaluation/hotel-servicing-rubric-cases.jsonl")
    dimensions = rubric["definition"]["dimensions"]
    assert len(dimensions) >= 20
    assert rubric["definition"]["pass_threshold"] == 0.9
    assert all(len(d["description"].split()) >= 60 for d in dimensions)
    assert all("Score 5" in d["description"] and "1 for" in d["description"] for d in dimensions)
    assert not any("flags " in d["description"].lower() for d in dimensions)
    assert {
        "privacy-other-room",
        "privacy-booking-existence",
        "privacy-synthetic-bypass",
        "compliance-hidden-fees",
        "compliance-service-animal",
        "correctness-price-arithmetic",
        "correctness-date-boundary",
    } <= {case["case_id"] for case in cases}
    assert all(case["query"] and case["expected_behavior"] for case in cases)


def test_realistic_customer_dataset_has_exactly_ten_distinct_interactions() -> None:
    _, cases = load_inputs()
    assert len(cases) == 10
    assert len({case["query"] for case in cases}) == 10
    assert all(case["query"] and case["expected_behavior"] for case in cases)
    items = runner.evaluation_items(cases)
    assert all(item["expected_behavior"] in item["evaluation_query"] for item in items)
    assert all(item["query"] == case["query"] for item, case in zip(items, cases, strict=True))


@pytest.mark.parametrize("registered_dataset", [False, True])
@pytest.mark.parametrize("reuse_evaluation", [False, True])
@pytest.mark.parametrize("result_variant", ["complete", "missing", "wrong-case"])
def test_native_run_uses_exact_name_full_rubric_and_ten_cases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    registered_dataset: bool,
    reuse_evaluation: bool,
    result_variant: str,
) -> None:
    rubric, cases = load_inputs(
        runner.ROOT / "evaluation/hotel-servicing-customer-interactions.jsonl"
    )
    requests: list[tuple[str, str, dict[str, Any] | None]] = []
    items = []
    for case in cases:
        item = scored_item(rubric)
        item["datasource_item"]["case_id"] = case["case_id"]
        items.append(item)
    if result_variant == "missing":
        items.pop()
    elif result_variant == "wrong-case":
        items[0]["datasource_item"]["case_id"] = "unexpected"

    def request(method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        requests.append((method, url, body))
        if "/agents/" in url:
            return {"status": "active"}
        if "/evaluators/" in url:
            return rubric
        if url.endswith("/evals"):
            return {"id": "eval_test", **(body or {})}
        if url.endswith("/evals/eval_test"):
            return {
                "id": "eval_test",
                "name": "Hotel Servicing Rubric v9",
                "testing_criteria": [
                    {
                        "id": "service-assigned-criterion-id",
                        "type": "azure_ai_evaluator",
                        "name": rubric["name"],
                        "evaluator_name": rubric["name"],
                        "evaluator_version": "9",
                        "initialization_parameters": {"model": "gpt-5.4-mini"},
                        "data_mapping": {
                            "query": "{{item.evaluation_query}}",
                            "response": "{{item.response}}",
                        },
                    }
                ],
            }
        if method == "post" and url.endswith("/runs"):
            return {"id": "run_test"}
        if "/output_items?" in url:
            return {"data": items, "has_more": False}
        return {"status": "completed", "result_counts": {"total": 10, "errored": 0}}

    monkeypatch.setattr(runner, "az_rest", request)
    monkeypatch.setattr(
        runner,
        "capture_hosted_responses",
        lambda *_: [{**case, "response": "Actual captured output"} for case in cases],
    )
    argv = [
        "run_hotel_rubric_eval.py",
        "--endpoint",
        "https://example.test/project",
        "--agent-version",
        "8",
        "--evaluator-version",
        "9",
        "--capture-hosted",
        "--cases",
        str(runner.ROOT / "evaluation/hotel-servicing-customer-interactions.jsonl"),
        "--output",
        str(tmp_path),
    ]
    if registered_dataset:
        argv.extend(["--dataset-id", "azureai://reviewed/dataset/versions/9.0"])
    if reuse_evaluation:
        argv.extend(["--evaluation-id", "eval_test"])
    monkeypatch.setattr("sys.argv", argv)
    if result_variant != "complete":
        with pytest.raises(RuntimeError, match="Evaluation incomplete"):
            runner.main()
        summary = json.loads((tmp_path / "summary.json").read_text())
        assert summary["incomplete"] == 1
        assert len(summary["missing_case_ids"]) == 1
        return
    runner.main()
    if reuse_evaluation:
        assert not any(url.endswith("/evals") for _, url, _ in requests)
        evaluation = request("get", "https://example.test/project/openai/v1/evals/eval_test")
    else:
        evaluation = next(body for _, url, body in requests if url.endswith("/evals"))
    run = next(body for method, url, body in requests if method == "post" and url.endswith("/runs"))
    assert evaluation is not None and run is not None
    assert evaluation["name"] == run["name"] == "Hotel Servicing Rubric v9"
    assert evaluation["testing_criteria"][0]["evaluator_version"] == "9"
    assert evaluation["testing_criteria"][0]["evaluator_name"] == rubric["name"]
    source = run["data_source"]["source"]
    if registered_dataset:
        assert source == {"type": "file_id", "id": "azureai://reviewed/dataset/versions/9.0"}
    else:
        assert len(source["content"]) == 10
    assert json.loads((tmp_path / "summary.json").read_text())["incomplete"] == 0


def test_fully_scored_safe_response_passes() -> None:
    rubric, _ = load_inputs()
    summary = summarize([scored_item(rubric)], rubric)
    assert summary["passed"] == 1
    assert summary["incomplete"] == 0
    assert summary["rows"][0]["case_id"] == "privacy-other-room"


def test_privacy_hard_gate_cannot_be_averaged_away() -> None:
    rubric, _ = load_inputs()
    item = scored_item(rubric)
    item["results"][0]["properties"]["dimension_scores"][0]["score"] = 1
    summary = summarize([item], rubric)
    assert summary["passed"] == 0
    assert summary["rows"][0]["aggregate_passed"] is True
    assert summary["rows"][0]["hard_gate_failures"] == ["authorized_guest_and_reservation_scope"]


@pytest.mark.parametrize("missing", ["score", "reason"])
def test_missing_dimension_evidence_is_incomplete(missing: str) -> None:
    rubric, _ = load_inputs()
    item = scored_item(rubric)
    del item["results"][0]["properties"]["dimension_scores"][0][missing]
    summary = summarize([item], rubric)
    assert summary["incomplete"] == 1
    assert summary["passed"] == 0


def test_missing_result_does_not_pass() -> None:
    rubric, _ = load_inputs()
    summary = summarize([{"results": []}], rubric)
    assert summary["incomplete"] == 1
    assert summary["passed"] == 0


def test_nonapplicable_dimensions_are_not_failures() -> None:
    rubric, _ = load_inputs()
    item = scored_item(rubric)
    dimension = next(
        d
        for d in item["results"][0]["properties"]["dimension_scores"]
        if d["id"] == "payment_card_and_financial_data_protection"
    )
    dimension.update(applicable=False, score=None, reason="No payment data involved.")
    assert summarize([item], rubric)["passed"] == 1


def test_always_applicable_dimension_cannot_be_skipped() -> None:
    rubric, _ = load_inputs()
    item = scored_item(rubric)
    item["results"][0]["properties"]["dimension_scores"][0]["applicable"] = False
    assert summarize([item], rubric)["incomplete"] == 1


def test_missing_optional_dimension_is_incomplete_not_a_pass() -> None:
    rubric, _ = load_inputs()
    item = scored_item(rubric)
    dimensions = item["results"][0]["properties"]["dimension_scores"]
    dimensions[:] = [
        d for d in dimensions if d["id"] != "payment_card_and_financial_data_protection"
    ]
    assert summarize([item], rubric)["incomplete"] == 1


def test_duplicate_dimension_is_incomplete() -> None:
    rubric, _ = load_inputs()
    item = scored_item(rubric)
    dimensions = item["results"][0]["properties"]["dimension_scores"]
    dimensions.append(deepcopy(dimensions[0]))
    assert summarize([item], rubric)["incomplete"] == 1


def test_service_failure_remains_a_failure_with_perfect_dimensions() -> None:
    rubric, _ = load_inputs()
    item = scored_item(rubric)
    original = deepcopy(item)
    item["results"][0]["passed"] = False
    assert summarize([item], rubric)["passed"] == 0
    assert original["results"][0]["passed"] is True


def test_hosted_capture_preserves_tool_evidence_without_sending_judge_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_rest(
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append((method, url, body))
        if method == "get":
            return {"versions": {"latest": {"version": "8"}}}
        return {
            "status": "completed",
            "output": [
                {"type": "function_call", "name": "search_hotel_knowledge"},
                {"type": "message", "content": [{"text": "Verified answer."}]},
            ],
        }

    monkeypatch.setattr(runner, "az_rest", fake_rest)
    cases = [{"case_id": "test", "query": "Guest question", "expected_behavior": "Judge only"}]
    captured = capture_hosted_responses("https://example", "hotel", "8", cases, tmp_path)
    assert "function_call" in captured[0]["response"]
    assert [body for method, _, body in calls if method == "post"] == [
        {"input": "Guest question", "store": False}
    ]
    assert len([c for c in calls if c[0] == "get"]) == 2
    with pytest.raises(ValueError, match="different target"):
        capture_hosted_responses("https://other", "hotel", "8", cases, tmp_path)


def test_hosted_capture_rejects_version_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_rest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"versions": {"latest": {"version": "9"}}}

    monkeypatch.setattr(runner, "az_rest", fake_rest)
    with pytest.raises(ValueError, match="differs"):
        capture_hosted_responses("https://example", "hotel", "8", [], tmp_path)


@pytest.mark.parametrize("provider_blocked", [True, False])
def test_hosted_capture_preserves_filter_blocks_but_rejects_other_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_blocked: bool,
) -> None:
    def fake_rest(
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method == "get":
            return {"versions": {"latest": {"version": "8"}}}
        return {
            "status": "failed",
            "error": {"message": "content_filter" if provider_blocked else "upstream timeout"},
            "output": [],
        }

    monkeypatch.setattr(runner, "az_rest", fake_rest)
    cases = [{"case_id": "test", "query": "Guest question", "expected_behavior": "Judge only"}]
    if provider_blocked:
        captured = capture_hosted_responses("https://example", "hotel", "8", cases, tmp_path)
        assert captured[0]["provider_blocked"] is True
        assert "response" not in captured[0]
    else:
        with pytest.raises(RuntimeError, match="incomplete"):
            capture_hosted_responses("https://example", "hotel", "8", cases, tmp_path)


def test_direct_judge_uses_reviewed_weights_and_enforces_privacy_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rubric, _ = load_inputs()
    cases = [{"case_id": "test", "query": "Guest question", "expected_behavior": "Protect privacy"}]
    capture = tmp_path / "capture"
    output = tmp_path / "scoring"
    runner.write_json(
        capture / "capture-target.json",
        {
            "endpoint": "https://example",
            "agent_version": "8",
            "agent_name": "hotel",
            "cases": cases,
        },
    )
    runner.write_json(
        capture / "responses/test.json",
        {
            "status": "completed",
            "output": [{"type": "message", "content": "Captured answer"}],
        },
    )
    dimensions = scored_item(rubric)["results"][0]["properties"]["dimension_scores"]
    dimensions[0]["score"] = 1

    def fake_rest(
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert body is not None
        assert body["model"] == "judge"
        assert "Captured answer" in body["messages"][1]["content"]
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "reason": "The answer discloses another guest's booking.",
                                "dimension_scores": dimensions,
                            }
                        )
                    },
                }
            ]
        }

    monkeypatch.setattr(runner, "az_rest", fake_rest)
    runner.judge_captured("https://example", "8", "judge", capture, output, rubric, cases)
    summary = json.loads((output / "summary.json").read_text())
    assert summary["rows"][0]["aggregate_passed"] is True
    assert summary["passed"] == 0
    assert summary["incomplete"] == 0
    assert summary["execution"] == "direct-judge-native-backend-fallback"
