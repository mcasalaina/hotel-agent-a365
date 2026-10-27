from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DimensionPolicy:
    name: str
    weight: int
    hard_gate: bool
    evidence: str


@dataclass(frozen=True)
class GateResult:
    passed: bool
    scored_cases: int
    judge_failures: int
    weighted_score: float
    threshold: float
    hard_gate_failures: dict[str, int]
    trace_complete: bool
    reasons: list[str]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSONL line {line_number}: {path}") from exc
    return rows


def load_policy(path: Path) -> tuple[list[DimensionPolicy], float]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    dimensions = [
        DimensionPolicy(
            name=item["name"],
            weight=int(item["weight"]),
            hard_gate=bool(item["hard_gate"]),
            evidence=item["evidence"],
        )
        for item in raw["dimensions"]
    ]
    if len(dimensions) != 15 or len({item.name for item in dimensions}) != 15:
        raise ValueError("Rubric policy must define exactly 15 unique dimensions")
    return dimensions, float(raw["pass_threshold"])


def evaluate_gates(
    *,
    scores_path: Path,
    policy_path: Path,
    trace_completeness_path: Path,
    trace_scores_path: Path | None = None,
    require_all_cases: int | None = None,
) -> GateResult:
    policies, threshold = load_policy(policy_path)
    rows = _read_jsonl(scores_path)
    scored_rows = [
        row
        for row in rows
        if row.get("judge_status") == "ok"
        and isinstance(row.get("verdict", {}).get("dimensions"), dict)
    ]
    judge_failures = len(rows) - len(scored_rows)
    trace_rows = _read_jsonl(trace_scores_path) if trace_scores_path is not None else []
    scored_trace_rows = [
        row
        for row in trace_rows
        if row.get("judge_status") == "ok"
        and isinstance(row.get("verdict", {}).get("dimensions"), dict)
    ]
    judge_failures += len(trace_rows) - len(scored_trace_rows)
    failures = {policy.name: 0 for policy in policies}
    applicable = {policy.name: 0 for policy in policies}

    for row in scored_rows:
        dimensions = row["verdict"]["dimensions"]
        for policy in policies:
            verdict = dimensions.get(policy.name)
            if isinstance(verdict, bool):
                applicable[policy.name] += 1
                failures[policy.name] += int(verdict)

    trace_failures = {policy.name: 0 for policy in policies}
    trace_applicable = {policy.name: 0 for policy in policies}
    for row in scored_trace_rows:
        dimensions = row["verdict"]["dimensions"]
        for policy in policies:
            verdict = dimensions.get(policy.name)
            if isinstance(verdict, bool):
                trace_applicable[policy.name] += 1
                trace_failures[policy.name] += int(verdict)

    weighted_success = 0.0
    weighted_total = 0.0
    for policy in policies:
        if policy.evidence == "response_and_trace" and trace_scores_path is not None:
            if not applicable[policy.name] or not trace_applicable[policy.name]:
                continue
            response_success = 1 - failures[policy.name] / applicable[policy.name]
            trace_success = 1 - trace_failures[policy.name] / trace_applicable[policy.name]
            success_rate = min(response_success, trace_success)
        elif applicable[policy.name]:
            success_rate = 1 - failures[policy.name] / applicable[policy.name]
        else:
            continue
        weighted_success += success_rate * policy.weight
        weighted_total += policy.weight
    weighted_score = weighted_success / weighted_total if weighted_total else 0.0
    hard_gate_failures = {
        policy.name: failures[policy.name] + trace_failures[policy.name]
        for policy in policies
        if policy.hard_gate and (failures[policy.name] or trace_failures[policy.name])
    }
    completeness = json.loads(trace_completeness_path.read_text(encoding="utf-8"))
    trace_complete = bool(completeness.get("complete"))

    reasons: list[str] = []
    if judge_failures:
        reasons.append(f"{judge_failures} case(s) were not judged")
    if require_all_cases is not None and len(scored_rows) != require_all_cases:
        reasons.append(f"Expected {require_all_cases} scored cases but found {len(scored_rows)}")
    if weighted_score < threshold:
        reasons.append(f"Weighted score {weighted_score:.3f} is below threshold {threshold:.3f}")
    if hard_gate_failures:
        reasons.append("One or more weight-10 hard-gate dimensions failed")
    if not trace_complete:
        reasons.append("Trace correlation is incomplete")

    return GateResult(
        passed=not reasons,
        scored_cases=len(scored_rows),
        judge_failures=judge_failures,
        weighted_score=weighted_score,
        threshold=threshold,
        hard_gate_failures=hard_gate_failures,
        trace_complete=trace_complete,
        reasons=reasons,
    )


def write_gate_result(result: GateResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
