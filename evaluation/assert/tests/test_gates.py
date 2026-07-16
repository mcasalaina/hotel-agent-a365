from __future__ import annotations

import json
from pathlib import Path

from hotel_assert.cli import _judge_failure_count, _retain_successful_scores
from hotel_assert.gates import evaluate_gates


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def policy(path: Path) -> None:
    dimensions = [
        {
            "name": f"dimension_{index}",
            "weight": 10 if index <= 6 else (6 if index <= 11 else 3),
            "hard_gate": index <= 6,
            "evidence": "response",
        }
        for index in range(1, 14)
    ]
    path.write_text(
        json.dumps({"pass_threshold": 0.68, "dimensions": dimensions}),
        encoding="utf-8",
    )


def test_gates_pass_complete_clear_run(tmp_path: Path) -> None:
    scores = tmp_path / "scores.jsonl"
    policy_path = tmp_path / "policy.json"
    traces = tmp_path / "traces.json"
    policy(policy_path)
    write_jsonl(
        scores,
        [
            {
                "judge_status": "ok",
                "verdict": {"dimensions": {f"dimension_{index}": False for index in range(1, 14)}},
            }
        ],
    )
    traces.write_text('{"complete": true}', encoding="utf-8")
    result = evaluate_gates(
        scores_path=scores,
        policy_path=policy_path,
        trace_completeness_path=traces,
        require_all_cases=1,
    )
    assert result.passed
    assert result.weighted_score == 1.0


def test_weight_ten_failure_fails_even_above_threshold(tmp_path: Path) -> None:
    scores = tmp_path / "scores.jsonl"
    policy_path = tmp_path / "policy.json"
    traces = tmp_path / "traces.json"
    policy(policy_path)
    dimensions = {f"dimension_{index}": False for index in range(1, 14)}
    dimensions["dimension_1"] = True
    write_jsonl(
        scores,
        [{"judge_status": "ok", "verdict": {"dimensions": dimensions}}],
    )
    traces.write_text('{"complete": true}', encoding="utf-8")
    result = evaluate_gates(
        scores_path=scores,
        policy_path=policy_path,
        trace_completeness_path=traces,
    )
    assert result.weighted_score > 0.68
    assert not result.passed
    assert result.hard_gate_failures == {"dimension_1": 1}


def test_failed_judgments_are_removed_before_resume(tmp_path: Path) -> None:
    scores = tmp_path / "scores.jsonl"
    write_jsonl(
        scores,
        [
            {"test_case_id": "case-1", "judge_status": "ok"},
            {"test_case_id": "case-2", "judge_status": "judge_failed"},
            {"test_case_id": "case-3", "judge_status": "ok"},
        ],
    )

    assert _judge_failure_count(scores) == 1
    _retain_successful_scores(scores)
    rows = [json.loads(line) for line in scores.read_text().splitlines()]
    assert [row["test_case_id"] for row in rows] == ["case-1", "case-3"]
