from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from hotel_assert.config_validation import validate_repository
from hotel_assert.gates import evaluate_gates, write_gate_result
from hotel_assert.preflight import run_preflight

MAX_JUDGE_RETRIES = 3


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _score_rows(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _judge_failure_count(path: Path) -> int:
    return sum(row.get("judge_status") != "ok" for row in _score_rows(path))


def _retain_successful_scores(path: Path) -> None:
    successful = [row for row in _score_rows(path) if row.get("judge_status") == "ok"]
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in successful),
        encoding="utf-8",
    )


def _run_judge_stage(
    *,
    assert_command: str,
    config: Path,
    suite: str,
    run_id: str,
    artifact_root: Path,
    inference_set: Path,
    save_dir: Path,
    force: bool,
    tolerate_viewer_failure: bool,
) -> None:
    command = [
        assert_command,
        "run",
        "--config",
        str(config),
        "--override",
        f"suite={suite}",
        "--override",
        f"run={run_id}",
        "--override",
        f"artifacts_root={artifact_root / '.judge-retries'}",
        "--override",
        "inference.enabled=false",
        "--override",
        f"judge.inference_set_path={inference_set}",
        "--override",
        f"judge.save_dir={save_dir}",
    ]
    if force:
        command.extend(["--force-stage", "judge"])
    process = subprocess.run(command, check=False, env=os.environ.copy())
    if process.returncode == 0:
        return
    inference_count = sum(1 for line in inference_set.read_text().splitlines() if line)
    scores_path = save_dir / "scores.jsonl"
    score_count = (
        sum(1 for line in scores_path.read_text().splitlines() if line)
        if scores_path.is_file()
        else 0
    )
    if not tolerate_viewer_failure or score_count != inference_count:
        raise subprocess.CalledProcessError(process.returncode, process.args)


def _retry_response_judgments(
    *,
    assert_command: str,
    config: Path,
    suite: str,
    run_id: str,
    artifact_root: Path,
    run_root: Path,
) -> None:
    scores_path = run_root / "scores.jsonl"
    for attempt in range(1, MAX_JUDGE_RETRIES + 1):
        failures = _judge_failure_count(scores_path)
        if failures == 0:
            return
        print(f"Retrying {failures} malformed response judgment(s), attempt {attempt}")
        _retain_successful_scores(scores_path)
        _run_judge_stage(
            assert_command=assert_command,
            config=config,
            suite=f"{suite}-response-retry",
            run_id=f"{run_id}-{attempt}",
            artifact_root=artifact_root,
            inference_set=run_root / "inference_set.jsonl",
            save_dir=run_root,
            force=False,
            tolerate_viewer_failure=False,
        )


def _retry_trace_judgments(
    *,
    assert_command: str,
    config: Path,
    suite: str,
    run_id: str,
    artifact_root: Path,
    trace_dir: Path,
) -> None:
    scores_path = trace_dir / "scores.jsonl"
    for attempt in range(1, MAX_JUDGE_RETRIES + 1):
        failures = _judge_failure_count(scores_path)
        if failures == 0:
            return
        print(f"Retrying trace judgments after {failures} malformed row(s), attempt {attempt}")
        _run_judge_stage(
            assert_command=assert_command,
            config=config,
            suite=f"{suite}-trace-retry",
            run_id=f"{run_id}-{attempt}",
            artifact_root=artifact_root,
            inference_set=trace_dir / "inference_set.jsonl",
            save_dir=trace_dir,
            force=True,
            tolerate_viewer_failure=True,
        )


def _command_validate(_: argparse.Namespace) -> int:
    errors = validate_repository(_repository_root())
    if errors:
        for error in errors:
            print(error)
        return 1
    print("ASSERT configuration is valid.")
    return 0


def _command_preflight(args: argparse.Namespace) -> int:
    result = asyncio.run(run_preflight(args.output))
    print(json.dumps({"passed": result.passed, "timestamp": result.timestamp}))
    return 0


def _command_run(args: argparse.Namespace) -> int:
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_root = args.artifact_root.resolve()
    ledger = args.ledger or artifact_root / "correlation" / f"{run_id}.jsonl"
    preflight_output = args.preflight_output or (
        artifact_root / "results" / args.suite / run_id / "preflight.json"
    )
    os.environ["ASSERT_RUN_ID"] = run_id
    os.environ["ASSERT_CORRELATION_LEDGER"] = str(ledger)
    asyncio.run(run_preflight(preflight_output))
    environment = os.environ.copy()
    subprocess.run(
        [
            args.assert_command,
            "run",
            "--config",
            str(args.config),
            "--override",
            f"suite={args.suite}",
            "--override",
            f"run={run_id}",
            "--override",
            f"artifacts_root={artifact_root}",
        ],
        check=True,
        env=environment,
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "ledger": str(ledger),
                "run_root": str(artifact_root / "results" / args.suite / run_id),
            }
        )
    )
    return 0


def _command_import(args: argparse.Namespace) -> int:
    from hotel_assert.app_insights import query_and_import

    result = query_and_import(
        workspace_id=args.workspace_id,
        ledger_path=args.ledger,
        output_directory=args.output,
        include_content=args.include_content,
    )
    print(
        json.dumps(
            {
                "complete": result.complete,
                "expected_turns": result.expected_turns,
                "correlated_turns": result.correlated_turns,
                "otlp_path": str(result.otlp_path),
            }
        )
    )
    return 0 if result.complete else 1


def _command_gate(args: argparse.Namespace) -> int:
    result = evaluate_gates(
        scores_path=args.scores,
        policy_path=args.policy,
        trace_completeness_path=args.trace_completeness,
        trace_scores_path=args.trace_scores,
        require_all_cases=args.require_all_cases,
    )
    write_gate_result(result, args.output)
    print(json.dumps({"passed": result.passed, "weighted_score": result.weighted_score}))
    return 0 if result.passed else 1


def _command_live(args: argparse.Namespace) -> int:
    from hotel_assert.app_insights import query_and_import

    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_root = args.artifact_root.resolve()
    run_root = artifact_root / "results" / args.suite / run_id
    ledger = artifact_root / "correlation" / f"{run_id}.jsonl"
    run_args = argparse.Namespace(
        config=args.config,
        suite=args.suite,
        run_id=run_id,
        assert_command=args.assert_command,
        ledger=ledger,
        preflight_output=run_root / "preflight.json",
        artifact_root=artifact_root,
    )
    _command_run(run_args)
    _retry_response_judgments(
        assert_command=args.assert_command,
        config=args.config,
        suite=args.suite,
        run_id=run_id,
        artifact_root=artifact_root,
        run_root=run_root,
    )
    time.sleep(args.telemetry_delay)
    trace_result = query_and_import(
        workspace_id=args.workspace_id,
        ledger_path=ledger,
        output_directory=run_root / "trace-import",
        include_content=False,
    )
    if not trace_result.complete:
        raise RuntimeError("Trace correlation is incomplete")
    trace_dir = run_root / "trace-judge"
    trace_scores = trace_dir / "scores.jsonl"
    subprocess.run(
        [
            args.assert_command,
            "judge-traces",
            "--traces",
            str(trace_result.otlp_path),
            "--config",
            str(args.config),
            "--group-by",
            "session.id",
            "--output",
            str(trace_dir),
        ],
        check=True,
        env=os.environ.copy(),
    )
    _run_judge_stage(
        assert_command=args.assert_command,
        config=args.config,
        suite=f"{args.suite}-traces",
        run_id=run_id,
        artifact_root=artifact_root,
        inference_set=trace_dir / "inference_set.jsonl",
        save_dir=trace_dir,
        force=True,
        tolerate_viewer_failure=True,
    )
    _retry_trace_judgments(
        assert_command=args.assert_command,
        config=args.config,
        suite=args.suite,
        run_id=run_id,
        artifact_root=artifact_root,
        trace_dir=trace_dir,
    )
    result = evaluate_gates(
        scores_path=run_root / "scores.jsonl",
        policy_path=args.policy,
        trace_completeness_path=trace_result.completeness_path,
        trace_scores_path=trace_scores,
        require_all_cases=args.require_all_cases,
    )
    write_gate_result(result, run_root / "gate-result.json")
    print(
        json.dumps(
            {
                "passed": result.passed,
                "run_id": run_id,
                "run_root": str(run_root),
                "weighted_score": result.weighted_score,
            }
        )
    )
    return 0 if result.passed else 1


def build_parser() -> argparse.ArgumentParser:
    root = _repository_root()
    evaluation = root / "evaluation" / "assert"
    parser = argparse.ArgumentParser(description="Run Hotel Guest Services ASSERT evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.set_defaults(func=_command_validate)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--output", type=Path)
    preflight.set_defaults(func=_command_preflight)

    run = subparsers.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--suite", required=True)
    run.add_argument("--run-id")
    run.add_argument("--assert-command", default="assert-ai")
    run.add_argument("--ledger", type=Path)
    run.add_argument("--preflight-output", type=Path)
    run.add_argument("--artifact-root", type=Path, default=root / "artifacts")
    run.set_defaults(func=_command_run)

    trace_import = subparsers.add_parser("import-traces")
    trace_import.add_argument("--workspace-id", required=True)
    trace_import.add_argument("--ledger", type=Path, required=True)
    trace_import.add_argument("--output", type=Path, required=True)
    trace_import.add_argument("--include-content", action="store_true")
    trace_import.set_defaults(func=_command_import)

    gate = subparsers.add_parser("gate")
    gate.add_argument("--scores", type=Path, required=True)
    gate.add_argument(
        "--policy",
        type=Path,
        default=evaluation / "policies" / "rubric-policy.json",
    )
    gate.add_argument("--trace-completeness", type=Path, required=True)
    gate.add_argument("--trace-scores", type=Path)
    gate.add_argument("--require-all-cases", type=int)
    gate.add_argument("--output", type=Path, required=True)
    gate.set_defaults(func=_command_gate)

    live = subparsers.add_parser("live")
    live.add_argument("--config", type=Path, required=True)
    live.add_argument("--suite", required=True)
    live.add_argument("--run-id")
    live.add_argument("--assert-command", default="assert-ai")
    live.add_argument("--artifact-root", type=Path, default=root / "artifacts")
    live.add_argument(
        "--workspace-id",
        default=os.getenv("APPLICATIONINSIGHTS_WORKSPACE_ID"),
        required=os.getenv("APPLICATIONINSIGHTS_WORKSPACE_ID") is None,
    )
    live.add_argument("--telemetry-delay", type=int, default=60)
    live.add_argument("--require-all-cases", type=int)
    live.add_argument(
        "--policy",
        type=Path,
        default=evaluation / "policies" / "rubric-policy.json",
    )
    live.set_defaults(func=_command_live)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))
