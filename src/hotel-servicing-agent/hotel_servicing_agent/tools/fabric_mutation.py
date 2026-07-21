from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

import httpx
from agent_framework import FunctionTool

from hotel_servicing_agent.hosting import current_evaluation_snapshot_id

FABRIC_API_SCOPE = "https://api.fabric.microsoft.com/.default"
JOB_TYPE = "RunNotebook"
TERMINAL_JOB_STATUSES = {"Completed", "Failed", "Cancelled", "Deduped"}
NEGATIVE_VERIFICATION_PHRASES = (
    "could not be found",
    "does not exist",
    "no data was found",
    "no reservation",
    "not found",
)
ReservationJobRunner = Callable[
    [str, str, Any, list[dict[str, object]]],
    Awaitable[dict[str, Any]],
]
ReservationVerifier = Callable[[str], Awaitable[str]]


class FabricReservationMutationTool:
    """Executes reservation changes through the governed Fabric notebook."""

    def __init__(
        self,
        workspace_id: str,
        guest_services_lakehouse_id: str,
        reservation_notebook_id: str,
        credential: Any,
        verifier: ReservationVerifier,
        job_runner: ReservationJobRunner | None = None,
    ) -> None:
        self._workspace_id = workspace_id
        self._guest_services_lakehouse_id = guest_services_lakehouse_id
        self._reservation_notebook_id = reservation_notebook_id
        self._credential = credential
        self._verifier = verifier
        self._job_runner = job_runner or _run_reservation_notebook

    def as_function_tool(self) -> FunctionTool:
        return FunctionTool(
            name="manage_reservation",
            description=(
                "Create, change, or cancel a reservation after resolving the guest, hotel, room "
                "type, availability, price, currency, and policy with "
                "query_hotel_operations_data. An explicit request in the current conversation or "
                "in my mailbox authorizes the requested action. Use a stable request_reference, "
                "such as the source email Internet Message ID, so retries do not duplicate a "
                "reservation."
            ),
            func=self.mutate,
        )

    async def mutate(
        self,
        action: str,
        request_reference: str,
        guest_id: str,
        property_id: str,
        room_type_id: str,
        check_in: str,
        check_out: str,
        room_count: int,
        rate_total: float,
        currency: str,
        channel: str,
        cancellation_policy: str,
        reservation_id: str = "",
        status: str = "future",
        expected_record_version: int | None = None,
    ) -> str:
        normalized_action = action.strip().lower()
        if normalized_action not in {"create", "change", "cancel"}:
            raise ValueError("action must be create, change, or cancel")
        if not request_reference.strip():
            raise ValueError("request_reference must not be empty")
        if room_count < 1:
            raise ValueError("room_count must be at least 1")
        if rate_total < 0:
            raise ValueError("rate_total must not be negative")
        check_in_date = date.fromisoformat(check_in)
        check_out_date = date.fromisoformat(check_out)
        if check_out_date <= check_in_date:
            raise ValueError("check_out must be after check_in")

        stable_reference = request_reference.strip()
        resolved_reservation_id = reservation_id.strip() or _reservation_id(stable_reference)
        confirmation_id = str(uuid5(NAMESPACE_URL, f"confirmation:{stable_reference}"))
        idempotency_key = str(
            uuid5(
                NAMESPACE_URL,
                f"reservation:{normalized_action}:{stable_reference}:{resolved_reservation_id}",
            )
        )
        verification_question = (
            f"Find reservation {resolved_reservation_id} using its complete record history and "
            "return its current persisted reservation details, including its status and the exact "
            "last confirmation ID."
        )
        expected_persisted_status = (
            "cancelled" if normalized_action == "cancel" else status.strip().casefold()
        )
        request_timestamp = (
            datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        payload = {
            "reservation_id": resolved_reservation_id,
            "guest_id": guest_id.strip(),
            "property_id": property_id.strip(),
            "room_type_id": room_type_id.strip(),
            "check_in": check_in_date.isoformat(),
            "check_out": check_out_date.isoformat(),
            "status": status.strip(),
            "cancellation_policy": cancellation_policy.strip(),
            "room_count": room_count,
            "rate_total": f"{rate_total:.2f}",
            "currency": currency.strip(),
            "channel": channel.strip(),
        }
        if any(not str(value).strip() for value in payload.values()):
            raise ValueError("reservation mutation fields must not be empty")
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        parameters: list[dict[str, object]] = [
            {"name": "action", "value": normalized_action, "type": "Text"},
            {"name": "confirmation_id", "value": confirmation_id, "type": "Text"},
            {"name": "idempotency_key", "value": idempotency_key, "type": "Text"},
            {
                "name": "request_timestamp_utc",
                "value": request_timestamp,
                "type": "Text",
            },
            {"name": "request_payload_json", "value": payload_json, "type": "Text"},
            {"name": "workspace_id", "value": self._workspace_id, "type": "Text"},
            {
                "name": "hotel_guest_services_lakehouse_id",
                "value": self._guest_services_lakehouse_id,
                "type": "Text",
            },
        ]
        evaluation_snapshot_id = current_evaluation_snapshot_id()
        if evaluation_snapshot_id:
            parameters.append(
                {
                    "name": "evaluation_snapshot_id",
                    "value": evaluation_snapshot_id,
                    "type": "Text",
                }
            )
        if expected_record_version is not None:
            parameters.insert(
                3,
                {
                    "name": "expected_record_version",
                    "value": expected_record_version,
                    "type": "Integer",
                },
            )

        try:
            job = await self._job_runner(
                self._workspace_id,
                self._reservation_notebook_id,
                self._credential,
                parameters,
            )
        except RuntimeError:
            recovered_verification = await self._verify_persisted_mutation(
                verification_question,
                resolved_reservation_id,
                confirmation_id,
                expected_persisted_status,
            )
            if recovered_verification:
                return _mutation_result(
                    "idempotent_replay" if normalized_action == "create" else "committed",
                    resolved_reservation_id,
                    confirmation_id,
                    recovered_verification,
                )
            raise
        if job.get("status") != "Completed":
            recovered_verification = await self._verify_persisted_mutation(
                verification_question,
                resolved_reservation_id,
                confirmation_id,
                expected_persisted_status,
            )
            if recovered_verification:
                return _mutation_result(
                    "idempotent_replay" if normalized_action == "create" else "committed",
                    resolved_reservation_id,
                    confirmation_id,
                    recovered_verification,
                )
            raise RuntimeError(f"Fabric reservation job did not complete: {job.get('status')}")

        notebook_result = _parse_exit_value(job.get("exitValue"))
        persisted_record = _verified_notebook_record(
            notebook_result,
            resolved_reservation_id,
            confirmation_id,
            expected_persisted_status,
        )
        if persisted_record is None:
            raise RuntimeError(
                "Fabric write completed but the persisted reservation could not be verified"
            )
        return _mutation_result(
            str(notebook_result.get("status", "committed")),
            resolved_reservation_id,
            confirmation_id,
            persisted_record,
        )

    async def _verify_persisted_mutation(
        self,
        verification_question: str,
        reservation_id: str,
        confirmation_id: str,
        expected_status: str,
    ) -> str:
        verification = await self._verifier(verification_question)
        if _verification_confirms_reservation(
            verification,
            reservation_id,
            confirmation_id,
            expected_status,
        ):
            return verification
        return ""


def _reservation_id(request_reference: str) -> str:
    value = uuid5(NAMESPACE_URL, f"reservation:{request_reference}").hex[:12].upper()
    return f"RES-{value}"


def _parse_exit_value(value: object) -> dict[str, object]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _verification_confirms_reservation(
    verification: str,
    reservation_id: str,
    confirmation_id: str,
    expected_status: str,
) -> bool:
    normalized = " ".join(verification.casefold().split())
    if not normalized or reservation_id.casefold() not in normalized:
        return False
    if any(phrase in normalized for phrase in NEGATIVE_VERIFICATION_PHRASES):
        return False
    confirmation_pattern = (
        r"\blast\s+confirmation\s+(?:id|identifier)\s*[:#-]?\s*"
        + re.escape(confirmation_id.casefold())
        + r"\b"
    )
    return bool(
        re.search(confirmation_pattern, normalized)
        and re.search(rf"\b{re.escape(expected_status.casefold())}\b", normalized)
    )


def _verified_notebook_record(
    notebook_result: dict[str, object],
    reservation_id: str,
    confirmation_id: str,
    expected_status: str,
) -> dict[str, object] | None:
    persisted_record = notebook_result.get("persisted_record")
    if not isinstance(persisted_record, dict):
        return None
    normalized_record = {str(key): value for key, value in persisted_record.items()}
    if normalized_record.get("reservation_id") != reservation_id:
        return None
    if normalized_record.get("last_confirmation_id") != confirmation_id:
        return None
    status = normalized_record.get("status")
    if not isinstance(status, str) or status.casefold() != expected_status.casefold():
        return None
    return normalized_record


def _mutation_result(
    status: str,
    reservation_id: str,
    confirmation_id: str,
    verification: object,
) -> str:
    return json.dumps(
        {
            "status": status,
            "reservation_id": reservation_id,
            "confirmation_id": confirmation_id,
            "persisted_record": verification,
        },
        separators=(",", ":"),
    )


async def _run_reservation_notebook(
    workspace_id: str,
    notebook_id: str,
    credential: Any,
    parameters: list[dict[str, object]],
) -> dict[str, Any]:
    access_token = await asyncio.to_thread(credential.get_token, FABRIC_API_SCOPE)
    headers = {"Authorization": f"Bearer {access_token.token}"}
    submit_url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/notebooks/{notebook_id}"
        "/jobs/execute/instances?beta=false"
    )
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        response = await client.post(submit_url, json={"parameters": parameters})
        if response.status_code != httpx.codes.ACCEPTED:
            raise RuntimeError(_fabric_error("start reservation job", response))
        location = response.headers.get("Location")
        if not location:
            raise RuntimeError("Fabric reservation job response did not include a Location header")
        job_id = urlparse(location).path.rstrip("/").rsplit("/", 1)[-1]
        if not job_id:
            raise RuntimeError("Fabric reservation job response did not include a job instance ID")
        status_url = (
            f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}"
            f"/notebooks/{notebook_id}/jobs/execute/instances/{job_id}"
        )

        deadline = time.monotonic() + 900
        retry_after = _retry_after(response)
        while time.monotonic() < deadline:
            await asyncio.sleep(retry_after)
            status_response = await client.get(status_url, params={"beta": "true"})
            if status_response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                retry_after = _retry_after(status_response)
                continue
            if not status_response.is_success:
                raise RuntimeError(_fabric_error("read reservation job status", status_response))
            raw_job: object = status_response.json()
            if not isinstance(raw_job, dict):
                raise RuntimeError("Fabric reservation job returned an invalid status response")
            job = {str(key): value for key, value in raw_job.items()}
            status = job.get("status")
            if status not in TERMINAL_JOB_STATUSES:
                retry_after = _retry_after(status_response)
                continue
            if status != "Completed":
                reason = job.get("failureReason") or "No failure details were returned"
                raise RuntimeError(f"Fabric reservation job {status}: {reason}")
            properties = job.get("properties")
            if "exitValue" not in job and isinstance(properties, dict):
                job["exitValue"] = properties.get("exitValue")
            return job
    raise TimeoutError("Fabric reservation job did not finish within 15 minutes")


def _retry_after(response: httpx.Response) -> int:
    value = response.headers.get("Retry-After", "15")
    try:
        return max(1, min(int(value), 60))
    except ValueError:
        return 15


def _fabric_error(operation: str, response: httpx.Response) -> str:
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {}
    code = body.get("errorCode", response.status_code)
    message = body.get("message", response.text or "No description")
    return f"Could not {operation}: {code}: {message}"
