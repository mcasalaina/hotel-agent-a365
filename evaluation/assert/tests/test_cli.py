from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from hotel_assert import cli


def test_live_forwards_reservation_notebook_to_transactional_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class StopAfterRunArgs(Exception):
        pass

    def capture_run_args(args: argparse.Namespace) -> int:
        captured.update(vars(args))
        raise StopAfterRunArgs

    monkeypatch.setattr(cli, "_command_run", capture_run_args)
    args = argparse.Namespace(
        run_id="run-1",
        artifact_root=tmp_path,
        suite="suite",
        config=tmp_path / "config.yaml",
        assert_command="assert-ai",
        fabric_workspace_id="workspace",
        fabric_operations_lakehouse_id="operations",
        fabric_guest_services_lakehouse_id="guest-services",
        fabric_state_notebook_id="state-notebook",
        fabric_reservation_notebook_id="reservation-notebook",
    )

    with pytest.raises(StopAfterRunArgs):
        cli._command_live(args)

    assert captured["fabric_reservation_notebook_id"] == "reservation-notebook"


def test_trace_retries_preserve_successful_judgments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    scores_path = trace_dir / "scores.jsonl"
    scores_path.write_text(
        "\n".join(
            [
                json.dumps({"test_case_id": "ok", "judge_status": "ok"}),
                json.dumps({"test_case_id": "failed", "judge_status": "judge_failed"}),
            ]
        )
        + "\n"
    )
    (trace_dir / "inference_set.jsonl").write_text("{}\n{}\n")
    calls: list[dict[str, object]] = []

    def repair_failed_judgment(**kwargs: object) -> None:
        calls.append(kwargs)
        with scores_path.open("a") as scores:
            scores.write(json.dumps({"test_case_id": "failed", "judge_status": "ok"}) + "\n")

    monkeypatch.setattr(cli, "_run_judge_stage", repair_failed_judgment)

    cli._retry_trace_judgments(
        assert_command="assert-ai",
        config=tmp_path / "config.yaml",
        suite="suite",
        run_id="run",
        artifact_root=tmp_path,
        trace_dir=trace_dir,
    )

    rows = cli._score_rows(scores_path)
    assert [row["test_case_id"] for row in rows] == ["ok", "failed"]
    assert calls[0]["force"] is False


def test_response_retries_fail_when_malformed_judgment_remains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "scores.jsonl").write_text(
        json.dumps({"test_case_id": "failed", "judge_status": "judge_failed"}) + "\n"
    )
    (run_root / "inference_set.jsonl").write_text("{}\n")
    monkeypatch.setattr(cli, "MAX_JUDGE_RETRIES", 1)
    monkeypatch.setattr(
        cli,
        "_run_judge_stage",
        lambda **_: (run_root / "scores.jsonl").write_text(
            json.dumps({"test_case_id": "failed", "judge_status": "judge_failed"}) + "\n"
        ),
    )

    with pytest.raises(RuntimeError, match="1 response judgment"):
        cli._retry_response_judgments(
            assert_command="assert-ai",
            config=tmp_path / "config.yaml",
            suite="suite",
            run_id="run",
            artifact_root=tmp_path,
            run_root=run_root,
        )
