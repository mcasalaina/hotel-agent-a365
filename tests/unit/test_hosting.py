from __future__ import annotations

from types import SimpleNamespace

from hotel_servicing_agent.hosting import (
    _baggage_value,
    _extract_snapshot_marker,
    _metadata_value,
    _structured_input_value,
)


def test_baggage_value_reads_encoded_evaluation_snapshot() -> None:
    headers = {
        "Baggage": (
            "assert.run_id=run-1,"
            "assert.snapshot_id=assert-snapshot%2F1;property=value,"
            "session.id=session-1"
        )
    }

    assert _baggage_value(headers, "assert.snapshot_id") == "assert-snapshot/1"


def test_baggage_value_rejects_missing_or_empty_values() -> None:
    assert _baggage_value({}, "assert.snapshot_id") is None
    assert _baggage_value({"baggage": "assert.snapshot_id="}, "assert.snapshot_id") is None


def test_metadata_value_reads_evaluation_snapshot() -> None:
    request = SimpleNamespace(metadata={"assert_snapshot_id": "assert-snapshot-1"})

    assert _metadata_value(request, "assert_snapshot_id") == "assert-snapshot-1"


def test_metadata_value_rejects_missing_or_empty_values() -> None:
    assert _metadata_value(SimpleNamespace(metadata={}), "assert_snapshot_id") is None
    assert (
        _metadata_value(
            SimpleNamespace(metadata={"assert_snapshot_id": " "}),
            "assert_snapshot_id",
        )
        is None
    )


def test_structured_input_value_reads_evaluation_snapshot() -> None:
    request = SimpleNamespace(structured_inputs={"assert_snapshot_id": "assert-snapshot-1"})

    assert _structured_input_value(request, "assert_snapshot_id") == "assert-snapshot-1"


def test_structured_input_value_rejects_missing_or_empty_values() -> None:
    assert (
        _structured_input_value(SimpleNamespace(structured_inputs={}), "assert_snapshot_id") is None
    )
    assert (
        _structured_input_value(
            SimpleNamespace(structured_inputs={"assert_snapshot_id": " "}),
            "assert_snapshot_id",
        )
        is None
    )


def test_extract_snapshot_marker_reads_and_removes_evaluation_snapshot() -> None:
    request = SimpleNamespace(
        input=[
            SimpleNamespace(
                role="developer",
                content=[
                    SimpleNamespace(
                        type="input_text",
                        text="ASSERT_EVALUATION_SNAPSHOT_ID:assert-snapshot-1",
                    )
                ],
            ),
            {"role": "user", "content": "hello"},
        ]
    )

    assert _extract_snapshot_marker(request) == "assert-snapshot-1"
    assert request.input == [{"role": "user", "content": "hello"}]


def test_extract_snapshot_marker_rejects_invalid_values() -> None:
    assert _extract_snapshot_marker(SimpleNamespace(input=None)) is None
    request = SimpleNamespace(
        input=[
            {
                "role": "developer",
                "content": "ASSERT_EVALUATION_SNAPSHOT_ID:snapshot/1",
            }
        ]
    )
    assert _extract_snapshot_marker(request) is None
    assert len(request.input) == 1
