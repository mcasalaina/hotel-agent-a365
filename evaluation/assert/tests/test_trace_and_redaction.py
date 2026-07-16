from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hotel_assert.redaction import redact
from hotel_assert.trace_import import import_rows, normalize_rows


def record() -> dict[str, object]:
    return {
        "run_id": "run-1",
        "case_id": "case-1",
        "session_id": "74e2d046-49f1-4f55-b98f-836878771222",
        "turn_index": 1,
        "trace_id": "a" * 32,
        "parent_span_id": "b" * 16,
        "response_id": "response-1",
        "started_at": "2026-07-15T10:00:00+00:00",
        "completed_at": "2026-07-15T10:00:01+00:00",
    }


def test_normalizer_assigns_session_and_redacts_content() -> None:
    rows = [
        {
            "EventTime": datetime(2026, 7, 15, 10, 0, tzinfo=UTC),
            "OpId": "a" * 32,
            "Parent": "b" * 16,
            "Span": "c" * 16,
            "EventName": "invoke_agent",
            "Props": {
                "gen_ai.input.messages": "private prompt",
                "authorization": "Bearer abc.def.ghi",
                "gen_ai.usage.input_tokens": "42",
                "user": "person@example.com",
            },
            "DurationMs": 10,
            "Success": True,
            "ResultCode": "200",
            "SourceTable": "AppRequests",
        }
    ]
    otlp, completeness = normalize_rows(rows, [record()])
    assert completeness["complete"] is True
    attributes = otlp["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
    attribute_map = {
        attribute["key"]: attribute["value"]["stringValue"]
        for attribute in attributes
        if "stringValue" in attribute["value"]
    }
    assert attribute_map["session.id"] == record()["session_id"]
    assert attribute_map["gen_ai.input.messages"] == "[REDACTED_CONTENT]"
    assert attribute_map["authorization"] == "[REDACTED_SECRET]"
    assert attribute_map["user"] == "[REDACTED_EMAIL]"
    token_attribute = next(
        attribute for attribute in attributes if attribute["key"] == "gen_ai.usage.input_tokens"
    )
    assert token_attribute["value"] == {"intValue": "42"}


def test_missing_trace_marks_case_incomplete(tmp_path: Path) -> None:
    result = import_rows(rows=[], records=[record()], output_directory=tmp_path)
    assert result.complete is False
    assert result.expected_turns == 1
    assert result.correlated_turns == 0
    assert result.otlp_path.is_file()


def test_redactor_removes_tokens_and_email_addresses() -> None:
    value = {
        "safe": "contact person@example.com",
        "detail": "Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiIxIn0.signature",
        "client_secret": "do-not-keep",
    }
    result = redact(value)
    assert "person@example.com" not in str(result)
    assert "eyJ" not in str(result)
    assert "do-not-keep" not in str(result)
