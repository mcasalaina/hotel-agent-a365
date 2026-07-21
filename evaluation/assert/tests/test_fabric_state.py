from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hotel_assert.fabric_state import (
    FabricStateConfig,
    FabricStateError,
    FabricStateLifecycle,
    preserve_fabric_state,
    snapshot_id_for_run,
)


def config() -> FabricStateConfig:
    return FabricStateConfig(
        workspace_id="workspace",
        operations_lakehouse_id="operations",
        guest_services_lakehouse_id="guest-services",
        notebook_id="notebook",
        reservation_notebook_id="reservation-notebook",
    )


def result(action: str, snapshot_id: str) -> dict[str, Any]:
    value: dict[str, Any] = {
        "action": action,
        "snapshot_id": snapshot_id,
        "table_count": 10,
        "tables": [],
    }
    if action == "restore":
        value["verified"] = True
    return value


def test_fabric_state_is_restored_after_success(tmp_path: Path) -> None:
    calls: list[str] = []
    snapshot_id = snapshot_id_for_run("20260720T101500Z")

    def runner(_: FabricStateConfig, action: str, received_id: str) -> dict[str, Any]:
        calls.append(action)
        return result(action, received_id)

    artifact = tmp_path / "fabric-state.json"
    lifecycle = FabricStateLifecycle(
        config=config(),
        snapshot_id=snapshot_id,
        artifact_path=artifact,
        job_runner=runner,
    )

    with preserve_fabric_state(lifecycle):
        assert calls == ["snapshot"]

    assert calls == ["snapshot", "seal", "restore"]
    persisted = json.loads(artifact.read_text())
    assert persisted["status"] == "restored"
    assert persisted["restore"]["verified"] is True


def test_fabric_state_is_restored_after_evaluation_failure(tmp_path: Path) -> None:
    calls: list[str] = []

    def runner(_: FabricStateConfig, action: str, snapshot_id: str) -> dict[str, Any]:
        calls.append(action)
        return result(action, snapshot_id)

    lifecycle = FabricStateLifecycle(
        config=config(),
        snapshot_id="assert-failing-run",
        artifact_path=tmp_path / "fabric-state.json",
        job_runner=runner,
    )

    with (
        pytest.raises(ValueError, match="evaluation failed"),
        preserve_fabric_state(lifecycle),
    ):
        raise ValueError("evaluation failed")

    assert calls == ["snapshot", "seal", "restore"]
    assert lifecycle.state.status == "restored"


def test_restore_failure_is_never_hidden(tmp_path: Path) -> None:
    def runner(_: FabricStateConfig, action: str, snapshot_id: str) -> dict[str, Any]:
        if action == "restore":
            raise FabricStateError("restore unavailable")
        return result(action, snapshot_id)

    lifecycle = FabricStateLifecycle(
        config=config(),
        snapshot_id="assert-restore-failure",
        artifact_path=tmp_path / "fabric-state.json",
        job_runner=runner,
    )

    with (
        pytest.raises(BaseExceptionGroup) as captured,
        preserve_fabric_state(lifecycle),
    ):
        raise ValueError("evaluation failed")

    assert len(captured.value.exceptions) == 2
    assert lifecycle.state.status == "restore_failed"


def test_restore_requires_explicit_verification(tmp_path: Path) -> None:
    def runner(_: FabricStateConfig, action: str, snapshot_id: str) -> dict[str, Any]:
        value = result(action, snapshot_id)
        value.pop("verified", None)
        return value

    lifecycle = FabricStateLifecycle(
        config=config(),
        snapshot_id="assert-unverified",
        artifact_path=tmp_path / "fabric-state.json",
        job_runner=runner,
    )
    lifecycle.snapshot()

    with pytest.raises(FabricStateError, match="verified=true"):
        lifecycle.restore()


def test_notebook_error_result_is_rejected(tmp_path: Path) -> None:
    def runner(_: FabricStateConfig, action: str, snapshot_id: str) -> dict[str, Any]:
        return {
            "action": action,
            "snapshot_id": snapshot_id,
            "table_count": 0,
            "error": "Could not access the evaluation lakehouse",
        }

    lifecycle = FabricStateLifecycle(
        config=config(),
        snapshot_id="assert-notebook-error",
        artifact_path=tmp_path / "fabric-state.json",
        job_runner=runner,
    )

    with pytest.raises(FabricStateError, match="Could not access"):
        lifecycle.snapshot()


def test_restore_seals_and_waits_before_restoring(tmp_path: Path) -> None:
    events: list[str] = []

    def runner(_: FabricStateConfig, action: str, snapshot_id: str) -> dict[str, Any]:
        events.append(action)
        return result(action, snapshot_id)

    def waiter(_: FabricStateConfig) -> None:
        events.append("wait")

    lifecycle = FabricStateLifecycle(
        config=config(),
        snapshot_id="assert-ordered-restore",
        artifact_path=tmp_path / "fabric-state.json",
        job_runner=runner,
        mutation_waiter=waiter,
    )
    lifecycle.snapshot()
    lifecycle.restore()

    assert events == ["snapshot", "seal", "wait", "restore"]


def test_artifact_failure_does_not_prevent_remote_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def runner(_: FabricStateConfig, action: str, snapshot_id: str) -> dict[str, Any]:
        calls.append(action)
        return result(action, snapshot_id)

    lifecycle = FabricStateLifecycle(
        config=config(),
        snapshot_id="assert-artifact-failure",
        artifact_path=tmp_path / "fabric-state.json",
        job_runner=runner,
    )
    lifecycle.snapshot()

    def fail_write() -> None:
        raise OSError("artifact mount unavailable")

    monkeypatch.setattr(lifecycle, "_write", fail_write)
    with pytest.raises(BaseExceptionGroup, match="cleanup status"):
        lifecycle.restore()

    assert calls == ["snapshot", "seal", "restore"]
    assert lifecycle.state.status == "restored"


def test_snapshot_artifact_failure_still_restores_remote_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    write_calls = 0

    def runner(_: FabricStateConfig, action: str, snapshot_id: str) -> dict[str, Any]:
        calls.append(action)
        return result(action, snapshot_id)

    lifecycle = FabricStateLifecycle(
        config=config(),
        snapshot_id="assert-snapshot-artifact-failure",
        artifact_path=tmp_path / "fabric-state.json",
        job_runner=runner,
    )
    original_write = lifecycle._write

    def fail_snapshot_completion_write() -> None:
        nonlocal write_calls
        write_calls += 1
        if write_calls == 2:
            raise OSError("artifact mount unavailable")
        original_write()

    monkeypatch.setattr(lifecycle, "_write", fail_snapshot_completion_write)
    with (
        pytest.raises(OSError, match="artifact mount unavailable"),
        preserve_fabric_state(lifecycle),
    ):
        raise AssertionError("evaluation body must not run")

    assert calls == ["snapshot", "seal", "restore"]
    assert lifecycle.state.status == "restored"
