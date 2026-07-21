from __future__ import annotations

import hashlib
import json
import re
import signal
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from azure.identity import DefaultAzureCredential

FABRIC_API_SCOPE = "https://api.fabric.microsoft.com/.default"
TERMINAL_JOB_STATUSES = {"Completed", "Failed", "Cancelled", "Deduped"}
FabricStateJobRunner = Callable[["FabricStateConfig", str, str], dict[str, Any]]
FabricMutationWaiter = Callable[["FabricStateConfig"], None]


class FabricStateError(RuntimeError):
    """Raised when evaluation state cannot be captured or restored exactly."""


@dataclass(frozen=True)
class FabricStateConfig:
    workspace_id: str
    operations_lakehouse_id: str
    guest_services_lakehouse_id: str
    notebook_id: str
    reservation_notebook_id: str


@dataclass
class FabricStateStatus:
    snapshot_id: str
    status: str
    snapshot_started_at: str | None = None
    remote_snapshot_attempted_at: str | None = None
    snapshot_completed_at: str | None = None
    restore_started_at: str | None = None
    sealed_at: str | None = None
    mutations_quiesced_at: str | None = None
    restore_completed_at: str | None = None
    snapshot: dict[str, Any] | None = None
    seal: dict[str, Any] | None = None
    restore: dict[str, Any] | None = None
    error: str | None = None


def snapshot_id_for_run(run_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", run_id).strip("-") or "run"
    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:12]
    return f"assert-{safe[:48]}-{digest}"


class FabricStateLifecycle:
    def __init__(
        self,
        *,
        config: FabricStateConfig,
        snapshot_id: str,
        artifact_path: Path,
        job_runner: FabricStateJobRunner | None = None,
        mutation_waiter: FabricMutationWaiter | None = None,
    ) -> None:
        self.config = config
        self.snapshot_id = snapshot_id
        self.artifact_path = artifact_path
        self.job_runner = job_runner or run_fabric_state_job
        self.mutation_waiter = mutation_waiter or (
            wait_for_fabric_mutations if job_runner is None else lambda _: None
        )
        self.state = FabricStateStatus(snapshot_id=snapshot_id, status="not_started")

    def snapshot(self) -> None:
        self.state.status = "snapshotting"
        self.state.snapshot_started_at = _now()
        self._write()
        try:
            self.state.remote_snapshot_attempted_at = _now()
            result = self.job_runner(self.config, "snapshot", self.snapshot_id)
            self._validate_result(result, action="snapshot")
        except BaseException as exc:
            self.state.status = "snapshot_failed"
            self.state.error = _error_text(exc)
            self._write()
            raise
        self.state.snapshot = result
        self.state.snapshot_completed_at = _now()
        self.state.status = "snapshotted"
        self._write()

    def restore(self) -> None:
        artifact_errors: list[BaseException] = []
        self.state.status = "sealing"
        self.state.restore_started_at = _now()
        self.state.error = None
        try:
            self._write()
        except BaseException as exc:
            artifact_errors.append(exc)
        try:
            sealed = self.job_runner(self.config, "seal", self.snapshot_id)
            self._validate_result(sealed, action="seal")
            self.state.seal = sealed
            self.state.sealed_at = _now()
            self.mutation_waiter(self.config)
            self.state.mutations_quiesced_at = _now()
            self.state.status = "restoring"
            try:
                self._write()
            except BaseException as exc:
                artifact_errors.append(exc)
            result = self.job_runner(self.config, "restore", self.snapshot_id)
            self._validate_result(result, action="restore")
            if result.get("verified") is not True:
                raise FabricStateError("Fabric restore did not return verified=true")
        except BaseException as exc:
            self.state.status = "restore_failed"
            self.state.error = _error_text(exc)
            try:
                self._write()
            except BaseException as artifact_error:
                artifact_errors.append(artifact_error)
            if artifact_errors:
                raise BaseExceptionGroup(
                    "Fabric restoration and cleanup artifact persistence failed",
                    [exc, *artifact_errors],
                ) from None
            raise
        self.state.restore = result
        self.state.restore_completed_at = _now()
        self.state.status = "restored"
        try:
            self._write()
        except BaseException as exc:
            artifact_errors.append(exc)
        if artifact_errors:
            raise BaseExceptionGroup(
                "Fabric state was restored but cleanup status could not be persisted",
                artifact_errors,
            )

    def _validate_result(self, result: dict[str, Any], *, action: str) -> None:
        if result.get("action") != action:
            raise FabricStateError(f"Fabric state notebook returned the wrong action for {action}")
        if result.get("snapshot_id") != self.snapshot_id:
            raise FabricStateError("Fabric state notebook returned the wrong snapshot ID")
        error = result.get("error")
        if isinstance(error, str) and error:
            raise FabricStateError(f"Fabric state {action} failed: {error}")
        table_count = result.get("table_count")
        if not isinstance(table_count, int) or table_count < 1:
            raise FabricStateError("Fabric state notebook returned no protected tables")

    def _write(self) -> None:
        self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.artifact_path.with_suffix(self.artifact_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(self.state), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.artifact_path)


@contextmanager
def preserve_fabric_state(lifecycle: FabricStateLifecycle) -> Iterator[None]:
    with _termination_as_exception():
        try:
            lifecycle.snapshot()
            yield
        except BaseException as evaluation_error:
            # Once remote execution starts, a client-side failure cannot prove that no lock exists.
            if lifecycle.state.remote_snapshot_attempted_at is None:
                raise
            try:
                lifecycle.restore()
            except BaseException as restore_error:
                raise BaseExceptionGroup(
                    "ASSERT evaluation failed and Fabric state restoration also failed",
                    [evaluation_error, restore_error],
                ) from None
            raise
        else:
            lifecycle.restore()


def run_fabric_state_job(
    config: FabricStateConfig,
    action: str,
    snapshot_id: str,
) -> dict[str, Any]:
    parameters = [
        {"name": "action", "value": action, "type": "Text"},
        {"name": "snapshot_id", "value": snapshot_id, "type": "Text"},
        {"name": "workspace_id", "value": config.workspace_id, "type": "Text"},
        {
            "name": "hotel_operations_lakehouse_id",
            "value": config.operations_lakehouse_id,
            "type": "Text",
        },
        {
            "name": "hotel_guest_services_lakehouse_id",
            "value": config.guest_services_lakehouse_id,
            "type": "Text",
        },
    ]
    with DefaultAzureCredential() as credential:
        token = credential.get_token(FABRIC_API_SCOPE).token
    headers = {"Authorization": f"Bearer {token}"}
    submit_url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{config.workspace_id}"
        f"/items/{config.notebook_id}/jobs/RunNotebook/instances"
    )
    execution_parameters = {
        str(parameter["name"]): {
            "value": parameter["value"],
            "type": "string",
        }
        for parameter in parameters
    }
    with httpx.Client(headers=headers, timeout=30) as client:
        response = client.post(
            submit_url,
            json={"executionData": {"parameters": execution_parameters}},
        )
        if response.status_code != httpx.codes.ACCEPTED:
            raise FabricStateError(_fabric_error(f"start {action}", response))
        location = response.headers.get("Location")
        if not location:
            raise FabricStateError("Fabric state job response did not include a Location header")
        job_id = Path(urlparse(location).path).name
        if not job_id:
            raise FabricStateError("Fabric state job response did not include a job instance ID")
        # Managed identity submits through the generic API, while only the notebook beta API
        # exposes the notebook exit value after the generic job reaches a terminal state.
        status_url = (
            f"https://api.fabric.microsoft.com/v1/workspaces/{config.workspace_id}"
            f"/notebooks/{config.notebook_id}/jobs/execute/instances/{job_id}"
        )
        deadline = time.monotonic() + 1800
        retry_after = _retry_after(response)
        while time.monotonic() < deadline:
            time.sleep(retry_after)
            status_response = client.get(location)
            if status_response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                retry_after = _retry_after(status_response)
                continue
            if not status_response.is_success:
                raise FabricStateError(_fabric_error(f"read {action} status", status_response))
            raw_job: object = status_response.json()
            if not isinstance(raw_job, dict):
                raise FabricStateError("Fabric state notebook returned an invalid status response")
            job = {str(key): value for key, value in raw_job.items()}
            status = job.get("status")
            if status not in TERMINAL_JOB_STATUSES:
                retry_after = _retry_after(status_response)
                continue
            if status != "Completed":
                reason = job.get("failureReason") or "No failure details were returned"
                raise FabricStateError(f"Fabric state notebook {status}: {reason}")
            break
        else:
            raise TimeoutError(f"Fabric state {action} did not finish within 30 minutes")
        while time.monotonic() < deadline:
            detail_response = client.get(status_url, params={"beta": "true"})
            if detail_response.status_code in {
                httpx.codes.NOT_FOUND,
                httpx.codes.TOO_MANY_REQUESTS,
            }:
                time.sleep(_retry_after(detail_response))
                continue
            if not detail_response.is_success:
                raise FabricStateError(_fabric_error(f"read {action} result", detail_response))
            raw_detail: object = detail_response.json()
            if not isinstance(raw_detail, dict):
                raise FabricStateError("Fabric state notebook returned an invalid result response")
            detail = {str(key): value for key, value in raw_detail.items()}
            return _parse_exit_value(_job_exit_value(detail))
    raise TimeoutError(f"Fabric state {action} did not finish within 30 minutes")


def wait_for_fabric_mutations(config: FabricStateConfig) -> None:
    with DefaultAzureCredential() as credential:
        token = credential.get_token(FABRIC_API_SCOPE).token
    headers = {"Authorization": f"Bearer {token}"}
    url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{config.workspace_id}"
        f"/items/{config.reservation_notebook_id}/jobs/instances"
    )
    deadline = time.monotonic() + 900
    with httpx.Client(headers=headers, timeout=30) as client:
        while time.monotonic() < deadline:
            response = client.get(url)
            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                time.sleep(_retry_after(response))
                continue
            if not response.is_success:
                raise FabricStateError(_fabric_error("list reservation jobs", response))
            raw: object = response.json()
            if not isinstance(raw, dict):
                raise FabricStateError("Fabric reservation jobs response was not an object")
            jobs = raw.get("value")
            if not isinstance(jobs, list):
                raise FabricStateError("Fabric reservation jobs response had no value list")
            active = [
                job
                for job in jobs
                if isinstance(job, dict) and job.get("status") in {"NotStarted", "InProgress"}
            ]
            if not active:
                return
            time.sleep(10)
    raise TimeoutError("Fabric reservation jobs did not quiesce within 15 minutes")


def _parse_exit_value(value: object) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        raise FabricStateError("Fabric state notebook returned no exit value")
    try:
        parsed: object = json.loads(value)
    except json.JSONDecodeError as exc:
        raise FabricStateError("Fabric state notebook returned malformed JSON") from exc
    if not isinstance(parsed, dict):
        raise FabricStateError("Fabric state notebook exit value is not a JSON object")
    return {str(key): item for key, item in parsed.items()}


def _job_exit_value(job: dict[str, Any]) -> object:
    if "exitValue" in job:
        return job["exitValue"]
    properties = job.get("properties")
    if isinstance(properties, dict):
        return properties.get("exitValue")
    return None


def _retry_after(response: httpx.Response) -> int:
    value = response.headers.get("Retry-After", "15")
    try:
        return max(1, min(int(value), 60))
    except ValueError:
        return 15


def _fabric_error(operation: str, response: httpx.Response) -> str:
    try:
        body: object = response.json()
    except json.JSONDecodeError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    code = body.get("errorCode", response.status_code)
    message = body.get("message", response.text or "No description")
    return f"Could not {operation} Fabric evaluation state: {code}: {message}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _error_text(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


@contextmanager
def _termination_as_exception() -> Iterator[None]:
    previous: dict[signal.Signals, Any] = {}

    def stop(signum: int, _: Any) -> None:
        raise SystemExit(128 + signum)

    for name in ("SIGTERM", "SIGHUP"):
        selected = getattr(signal, name, None)
        if selected is None:
            continue
        previous[selected] = signal.getsignal(selected)
        signal.signal(selected, stop)
    try:
        yield
    finally:
        for selected, handler in previous.items():
            signal.signal(selected, handler)
