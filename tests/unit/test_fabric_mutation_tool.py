from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pytest
from hotel_servicing_agent.tools import fabric_mutation
from hotel_servicing_agent.tools.fabric_mutation import FabricReservationMutationTool


def _confirmation_id(request_reference: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"confirmation:{request_reference}"))


def _completed_job(
    parameters: list[dict[str, object]],
    reservation_id: str,
    status: str,
    *,
    result_status: str = "committed",
) -> dict[str, Any]:
    values = {str(item["name"]): item["value"] for item in parameters}
    return {
        "status": "Completed",
        "exitValue": json.dumps(
            {
                "status": result_status,
                "reservation_id": reservation_id,
                "confirmation_id": values["confirmation_id"],
                "persisted_record": {
                    "reservation_id": reservation_id,
                    "status": status,
                    "last_confirmation_id": values["confirmation_id"],
                    "record_version": 2,
                },
            }
        ),
    }


def test_reservation_mutation_runs_notebook_and_rereads_persisted_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        captured.update(
            workspace_id=workspace_id,
            notebook_id=notebook_id,
            credential=credential,
            parameters=parameters,
        )
        return _completed_job(parameters, "RES-TEST", "future")

    async def fake_verifier(question: str) -> str:
        raise AssertionError("completed notebook result should be authoritative")

    credential = object()
    monkeypatch.setattr(
        fabric_mutation,
        "current_evaluation_snapshot_id",
        lambda: "assert-snapshot-1",
    )
    tool = FabricReservationMutationTool(
        workspace_id="00000000-0000-0000-0000-000000000001",
        guest_services_lakehouse_id="00000000-0000-0000-0000-000000000002",
        reservation_notebook_id="00000000-0000-0000-0000-000000000003",
        credential=credential,
        verifier=fake_verifier,
        job_runner=fake_job_runner,
    )

    result = json.loads(
        asyncio.run(
            tool.mutate(
                action="create",
                request_reference="mail-message-123",
                reservation_id="RES-TEST",
                guest_id="GST-000001",
                property_id="HTL-016",
                room_type_id="HTL-016-RT-04",
                check_in="2026-07-22",
                check_out="2026-07-24",
                room_count=1,
                rate_total=800.0,
                currency="USD",
                channel="direct",
                cancellation_policy="flexible",
            )
        )
    )

    parameters = {item["name"]: item for item in captured["parameters"]}
    payload = json.loads(str(parameters["request_payload_json"]["value"]))
    assert captured["workspace_id"].endswith("1")
    assert captured["notebook_id"].endswith("3")
    assert captured["credential"] is credential
    assert parameters["action"]["value"] == "create"
    assert parameters["confirmation_id"]["type"] == "Text"
    assert parameters["idempotency_key"]["type"] == "Text"
    assert parameters["evaluation_snapshot_id"]["value"] == "assert-snapshot-1"
    assert payload["reservation_id"] == "RES-TEST"
    assert payload["property_id"] == "HTL-016"
    assert result["status"] == "committed"
    assert result["reservation_id"] == "RES-TEST"
    assert result["persisted_record"]["status"] == "future"
    assert result["persisted_record"]["record_version"] == 2
    assert tool.as_function_tool().name == "manage_reservation"


def test_reservation_mutation_uses_stable_ids_for_retries() -> None:
    calls: list[list[dict[str, object]]] = []

    async def fake_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        calls.append(parameters)
        reservation_id = str(
            json.loads(
                str(
                    next(
                        item["value"]
                        for item in parameters
                        if item["name"] == "request_payload_json"
                    )
                )
            )["reservation_id"]
        )
        return _completed_job(
            parameters,
            reservation_id,
            "future",
            result_status="committed" if len(calls) == 1 else "idempotent_replay",
        )

    async def fake_verifier(question: str) -> str:
        raise AssertionError("completed notebook result should be authoritative")

    tool = FabricReservationMutationTool(
        workspace_id="00000000-0000-0000-0000-000000000001",
        guest_services_lakehouse_id="00000000-0000-0000-0000-000000000002",
        reservation_notebook_id="00000000-0000-0000-0000-000000000003",
        credential=object(),
        verifier=fake_verifier,
        job_runner=fake_job_runner,
    )
    arguments = {
        "action": "create",
        "request_reference": "same-email",
        "guest_id": "GST-1",
        "property_id": "HTL-016",
        "room_type_id": "HTL-016-RT-04",
        "check_in": "2026-07-22",
        "check_out": "2026-07-24",
        "room_count": 1,
        "rate_total": 800.0,
        "currency": "USD",
        "channel": "direct",
        "cancellation_policy": "flexible",
    }

    first = json.loads(asyncio.run(tool.mutate(**arguments)))
    second = json.loads(asyncio.run(tool.mutate(**arguments)))
    first_parameters = {item["name"]: item["value"] for item in calls[0]}

    assert first["reservation_id"] == second["reservation_id"]
    assert first["confirmation_id"] == second["confirmation_id"]
    assert first_parameters["confirmation_id"] == first["confirmation_id"]
    assert first_parameters["idempotency_key"]
    assert second["status"] == "idempotent_replay"
    assert len(calls) == 2


def test_reservation_mutation_rejects_unverified_notebook_result() -> None:
    async def fake_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        return {
            "status": "Completed",
            "exitValue": json.dumps(
                {
                    "status": "committed",
                    "reservation_id": "RES-TEST",
                    "persisted_record": {
                        "reservation_id": "RES-TEST",
                        "status": "future",
                        "last_confirmation_id": "wrong-confirmation",
                    },
                }
            ),
        }

    async def fake_verifier(question: str) -> str:
        raise AssertionError("completed notebook result should be authoritative")

    tool = FabricReservationMutationTool(
        workspace_id="workspace",
        guest_services_lakehouse_id="lakehouse",
        reservation_notebook_id="notebook",
        credential=object(),
        verifier=fake_verifier,
        job_runner=fake_job_runner,
    )

    with pytest.raises(RuntimeError, match="could not be verified"):
        asyncio.run(
            tool.mutate(
                action="create",
                request_reference="request",
                reservation_id="RES-TEST",
                guest_id="guest",
                property_id="property",
                room_type_id="room-type",
                check_in="2026-07-22",
                check_out="2026-07-24",
                room_count=1,
                rate_total=100,
                currency="USD",
                channel="direct",
                cancellation_policy="flexible",
            )
        )


def test_create_does_not_replay_an_unrelated_existing_reservation() -> None:
    job_calls = 0

    async def fake_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        nonlocal job_calls
        job_calls += 1
        return _completed_job(parameters, "RES-EXISTING", "future")

    async def fake_verifier(question: str) -> str:
        raise AssertionError("completed notebook result should be authoritative")

    tool = FabricReservationMutationTool(
        workspace_id="workspace",
        guest_services_lakehouse_id="lakehouse",
        reservation_notebook_id="notebook",
        credential=object(),
        verifier=fake_verifier,
        job_runner=fake_job_runner,
    )

    result = json.loads(
        asyncio.run(
            tool.mutate(
                action="create",
                request_reference="new-email-message-id",
                reservation_id="RES-EXISTING",
                guest_id="guest",
                property_id="property",
                room_type_id="room-type",
                check_in="2026-07-22",
                check_out="2026-07-24",
                room_count=1,
                rate_total=100,
                currency="USD",
                channel="email",
                cancellation_policy="flexible",
            )
        )
    )

    assert result["status"] == "committed"
    assert job_calls == 1


def test_change_rejects_an_unchanged_persisted_record() -> None:
    async def fake_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        result = _completed_job(parameters, "RES-OLD", "future")
        notebook_result = json.loads(str(result["exitValue"]))
        notebook_result["persisted_record"]["last_confirmation_id"] = "prior-confirmation"
        result["exitValue"] = json.dumps(notebook_result)
        return result

    async def fake_verifier(question: str) -> str:
        raise AssertionError("completed notebook result should be authoritative")

    tool = FabricReservationMutationTool(
        workspace_id="workspace",
        guest_services_lakehouse_id="lakehouse",
        reservation_notebook_id="notebook",
        credential=object(),
        verifier=fake_verifier,
        job_runner=fake_job_runner,
    )

    with pytest.raises(RuntimeError, match="could not be verified"):
        asyncio.run(
            tool.mutate(
                action="change",
                request_reference="change-request",
                reservation_id="RES-OLD",
                guest_id="guest",
                property_id="new-property",
                room_type_id="new-room-type",
                check_in="2026-08-01",
                check_out="2026-08-03",
                room_count=1,
                rate_total=200,
                currency="USD",
                channel="direct",
                cancellation_policy="flexible",
            )
        )


def test_cancel_rejects_an_echoed_expected_confirmation() -> None:
    async def fake_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        raise RuntimeError("Fabric status polling failed")

    async def fake_verifier(question: str) -> str:
        confirmation_id = _confirmation_id("cancel-request")
        return (
            "Reservation RES-CANCEL has status future. "
            "Last confirmation ID: No confirmation ID is currently persisted. "
            f"Expected confirmation ID: {confirmation_id}."
        )

    tool = FabricReservationMutationTool(
        workspace_id="workspace",
        guest_services_lakehouse_id="lakehouse",
        reservation_notebook_id="notebook",
        credential=object(),
        verifier=fake_verifier,
        job_runner=fake_job_runner,
    )

    with pytest.raises(RuntimeError, match="polling failed"):
        asyncio.run(
            tool.mutate(
                action="cancel",
                request_reference="cancel-request",
                reservation_id="RES-CANCEL",
                guest_id="guest",
                property_id="property",
                room_type_id="room-type",
                check_in="2026-08-01",
                check_out="2026-08-03",
                room_count=1,
                rate_total=200,
                currency="USD",
                channel="direct",
                cancellation_policy="flexible",
            )
        )


def test_change_recovers_when_polling_fails_after_the_write() -> None:
    async def failing_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        raise RuntimeError("Fabric status polling failed")

    async def fake_verifier(question: str) -> str:
        confirmation_id = _confirmation_id("change-request")
        return (
            "Reservation RES-CHANGE has the requested new dates and future status. "
            f"Last confirmation ID: {confirmation_id}."
        )

    tool = FabricReservationMutationTool(
        workspace_id="workspace",
        guest_services_lakehouse_id="lakehouse",
        reservation_notebook_id="notebook",
        credential=object(),
        verifier=fake_verifier,
        job_runner=failing_job_runner,
    )

    result = json.loads(
        asyncio.run(
            tool.mutate(
                action="change",
                request_reference="change-request",
                reservation_id="RES-CHANGE",
                guest_id="guest",
                property_id="property",
                room_type_id="room-type",
                check_in="2026-08-01",
                check_out="2026-08-03",
                room_count=1,
                rate_total=200,
                currency="USD",
                channel="direct",
                cancellation_policy="flexible",
            )
        )
    )

    assert result["status"] == "committed"
    assert result["reservation_id"] == "RES-CHANGE"


@pytest.mark.parametrize("action", ["", "upgrade", "delete"])
def test_reservation_mutation_rejects_unsupported_actions(action: str) -> None:
    async def unused_verifier(question: str) -> str:
        raise AssertionError("verifier should not run")

    tool = FabricReservationMutationTool(
        workspace_id="workspace",
        guest_services_lakehouse_id="lakehouse",
        reservation_notebook_id="notebook",
        credential=object(),
        verifier=unused_verifier,
    )

    with pytest.raises(ValueError, match="action must be"):
        asyncio.run(
            tool.mutate(
                action=action,
                request_reference="request",
                guest_id="guest",
                property_id="property",
                room_type_id="room-type",
                check_in="2026-07-22",
                check_out="2026-07-24",
                room_count=1,
                rate_total=100,
                currency="USD",
                channel="direct",
                cancellation_policy="flexible",
            )
        )
