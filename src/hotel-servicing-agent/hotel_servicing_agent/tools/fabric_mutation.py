from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from agent_framework import FunctionTool

FABRIC_API_SCOPE = "https://api.fabric.microsoft.com/.default"
JOB_TYPE = "RunNotebook"
TERMINAL_JOB_STATUSES = {"Completed", "Failed", "Cancelled", "Deduped"}
VERIFICATION_ATTEMPTS = 6
VERIFICATION_RETRY_SECONDS = 20
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
            "return its current persisted reservation details, including the exact last "
            f"confirmation ID. The expected confirmation ID is {confirmation_id}."
        )
        if normalized_action == "create":
            existing_verification = await self._verifier(verification_question)
            if _verification_confirms_reservation(
                existing_verification,
                resolved_reservation_id,
                confirmation_id,
            ):
                return _mutation_result(
                    "idempotent_replay",
                    resolved_reservation_id,
                    confirmation_id,
                    existing_verification,
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
            )
            if recovered_verification:
                return _mutation_result(
                    "idempotent_replay" if normalized_action == "create" else "committed",
                    resolved_reservation_id,
                    confirmation_id,
                    recovered_verification,
                )
            raise RuntimeError(f"Fabric reservation job did not complete: {job.get('status')}")

        verification = await self._verify_persisted_mutation(
            verification_question,
            resolved_reservation_id,
            confirmation_id,
        )
        if not verification:
            raise RuntimeError(
                "Fabric write completed but the persisted reservation could not be verified"
            )
        notebook_result = _parse_exit_value(job.get("exitValue"))
        return _mutation_result(
            str(notebook_result.get("status", "committed")),
            resolved_reservation_id,
            confirmation_id,
            verification,
        )

    async def _verify_persisted_mutation(
        self,
        verification_question: str,
        reservation_id: str,
        confirmation_id: str,
    ) -> str:
        for attempt in range(VERIFICATION_ATTEMPTS):
            verification = await self._verifier(verification_question)
            if _verification_confirms_reservation(
                verification,
                reservation_id,
                confirmation_id,
            ):
                return verification
            if attempt + 1 < VERIFICATION_ATTEMPTS:
                await asyncio.sleep(VERIFICATION_RETRY_SECONDS)
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
) -> bool:
    normalized = verification.strip().casefold()
    if (
        not normalized
        or reservation_id.casefold() not in normalized
        or confirmation_id.casefold() not in normalized
    ):
        return False
    return not any(phrase in normalized for phrase in NEGATIVE_VERIFICATION_PHRASES)


def _mutation_result(
    status: str,
    reservation_id: str,
    confirmation_id: str,
    verification: str,
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
    parameter_types = {"Text": "string", "Integer": "int"}
    notebook_parameters: dict[str, dict[str, object]] = {}
    for parameter in parameters:
        parameter_type = str(parameter["type"])
        if parameter_type not in parameter_types:
            raise ValueError(f"Unsupported Fabric notebook parameter type: {parameter_type}")
        notebook_parameters[str(parameter["name"])] = {
            "value": parameter["value"],
            "type": parameter_types[parameter_type],
        }
    access_token = await asyncio.to_thread(credential.get_token, FABRIC_API_SCOPE)
    headers = {"Authorization": f"Bearer {access_token.token}"}
    submit_url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{notebook_id}"
        f"/jobs/{JOB_TYPE}/instances"
    )
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        response = await client.post(
            submit_url,
            json={"executionData": {"parameters": notebook_parameters}},
        )
        if response.status_code != httpx.codes.ACCEPTED:
            raise RuntimeError(_fabric_error("start reservation job", response))
        location = response.headers.get("Location")
        if not location:
            raise RuntimeError("Fabric reservation job response did not include a Location header")
        try:
            job_id = UUID(httpx.URL(location).path.rstrip("/").rsplit("/", 1)[-1])
        except ValueError as error:
            raise RuntimeError("Fabric reservation job returned an invalid job Location") from error
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
            if job.get("exitValue") is None and isinstance(properties, dict):
                job["exitValue"] = properties.get("exitValue")
            return job
    raise TimeoutError("Fabric reservation job did not finish within 15 minutes")


def _retry_after(response: httpx.Response) -> int:
    value = response.headers.get("Retry-After", "15")
    try:
        return max(1, int(value))
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
