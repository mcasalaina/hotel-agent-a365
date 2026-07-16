from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from hotel_servicing_agent.tools.fabric_mutation import FabricReservationMutationTool


def _confirmation_id_from_question(question: str) -> str:
    return question.rsplit(" ", 1)[-1].rstrip(".")


def test_reservation_mutation_runs_notebook_and_rereads_persisted_record() -> None:
    captured: dict[str, Any] = {}
    verification_calls = 0

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
        return {
            "status": "Completed",
            "exitValue": json.dumps({"status": "committed", "reservation_id": "RES-TEST"}),
        }

    async def fake_verifier(question: str) -> str:
        nonlocal verification_calls
        verification_calls += 1
        captured["verification_question"] = question
        if verification_calls == 1:
            return "No data was found for reservation RES-TEST."
        confirmation_id = _confirmation_id_from_question(question)
        return (
            "Reservation RES-TEST is for Maria Garcia at Lyrenza Buenos Aires. "
            f"Last confirmation ID: {confirmation_id}."
        )

    credential = object()
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
    assert payload["reservation_id"] == "RES-TEST"
    assert payload["property_id"] == "HTL-016"
    assert "Find reservation RES-TEST" in captured["verification_question"]
    assert result["status"] == "committed"
    assert result["reservation_id"] == "RES-TEST"
    assert "Lyrenza Buenos Aires" in result["persisted_record"]
    assert tool.as_function_tool().name == "manage_reservation"


def test_reservation_mutation_uses_stable_ids_for_retries() -> None:
    calls: list[list[dict[str, object]]] = []
    persisted_reservation_id = ""

    async def fake_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        calls.append(parameters)
        return {"status": "Completed"}

    async def fake_verifier(question: str) -> str:
        nonlocal persisted_reservation_id
        reservation_id = question.split()[2]
        if not persisted_reservation_id:
            persisted_reservation_id = reservation_id
            return f"No data was found for reservation {reservation_id}."
        confirmation_id = _confirmation_id_from_question(question)
        return f"Persisted reservation {reservation_id}. Last confirmation ID: {confirmation_id}."

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
    assert len(calls) == 1


def test_reservation_mutation_retries_until_record_is_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verification_calls = 0

    async def fake_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        return {"status": "Completed"}

    async def fake_verifier(question: str) -> str:
        nonlocal verification_calls
        verification_calls += 1
        if verification_calls < 3:
            return "No data was found for reservation RES-TEST."
        confirmation_id = _confirmation_id_from_question(question)
        return (
            "Reservation RES-TEST is future and persisted. "
            f"Last confirmation ID: {confirmation_id}."
        )

    async def no_wait(seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_wait)
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
    )

    assert "Reservation RES-TEST is future and persisted." in result["persisted_record"]


def test_create_does_not_replay_an_unrelated_existing_reservation() -> None:
    job_calls = 0
    verification_calls = 0

    async def fake_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        nonlocal job_calls
        job_calls += 1
        return {"status": "Completed"}

    async def fake_verifier(question: str) -> str:
        nonlocal verification_calls
        verification_calls += 1
        if verification_calls == 1:
            return (
                "Reservation RES-EXISTING belongs to another request. "
                "Last confirmation ID: unrelated-confirmation."
            )
        confirmation_id = _confirmation_id_from_question(question)
        return (
            f"Reservation RES-EXISTING is now persisted. Last confirmation ID: {confirmation_id}."
        )

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


def test_change_rejects_an_unchanged_persisted_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        return {"status": "Completed"}

    async def fake_verifier(question: str) -> str:
        return (
            "Reservation RES-OLD still has its original values. "
            "Last confirmation ID: prior-confirmation."
        )

    async def no_wait(seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_wait)
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


def test_change_recovers_when_polling_fails_after_the_write() -> None:
    async def failing_job_runner(
        workspace_id: str,
        notebook_id: str,
        credential: Any,
        parameters: list[dict[str, object]],
    ) -> dict[str, Any]:
        raise RuntimeError("Fabric status polling failed")

    async def fake_verifier(question: str) -> str:
        confirmation_id = _confirmation_id_from_question(question)
        return (
            "Reservation RES-CHANGE has the requested new dates. "
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
