from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from hotel_assert.redaction import redact

_HEX_RE = re.compile(r"[0-9a-f]+", re.IGNORECASE)


@dataclass(frozen=True)
class TraceImportResult:
    otlp_path: Path
    completeness_path: Path
    complete: bool
    expected_turns: int
    correlated_turns: int


def _kql_strings(values: Iterable[str]) -> str:
    return ", ".join(json.dumps(value) for value in sorted(set(values)) if value)


def build_kql(records: list[dict[str, Any]]) -> tuple[str, datetime, datetime]:
    if not records:
        raise ValueError("The correlation ledger is empty")
    start = min(datetime.fromisoformat(record["started_at"]) for record in records) - timedelta(
        minutes=2
    )
    end = max(datetime.fromisoformat(record["completed_at"]) for record in records) + timedelta(
        minutes=5
    )
    trace_ids = _kql_strings(str(record["trace_id"]) for record in records)
    response_ids = _kql_strings(str(record["response_id"]) for record in records)
    query = f"""
union withsource=SourceTable isfuzzy=true
      AppEvents, AppDependencies, AppRequests, AppTraces
| extend EventTime=coalesce(
             column_ifexists("TimeGenerated", datetime(null)),
             column_ifexists("timestamp", datetime(null))
         ),
         OpId=tostring(coalesce(
             column_ifexists("OperationId", ""),
             column_ifexists("operation_Id", "")
         )),
         Parent=tostring(coalesce(
             column_ifexists("ParentId", ""),
             column_ifexists("operation_ParentId", "")
         )),
         Span=tostring(coalesce(
             column_ifexists("Id", ""),
             column_ifexists("id", "")
         )),
         EventName=tostring(coalesce(
             column_ifexists("Name", ""),
             column_ifexists("name", "")
         )),
         Props=coalesce(
             column_ifexists("Properties", dynamic(null)),
             column_ifexists("customDimensions", dynamic(null)),
             dynamic({{}})
         ),
         DurationValue=tostring(coalesce(
             tostring(column_ifexists("DurationMs", real(null))),
             tostring(column_ifexists("duration", timespan(null)))
         )),
         SuccessValue=coalesce(
             column_ifexists("Success", bool(null)),
             column_ifexists("success", bool(null))
         ),
         ResultCodeValue=tostring(coalesce(
             column_ifexists("ResultCode", ""),
             column_ifexists("resultCode", "")
         )),
         DependencyTypeValue=tostring(coalesce(
             column_ifexists("DependencyType", ""),
             column_ifexists("type", "")
         )),
         DataValue=tostring(coalesce(
             column_ifexists("Data", ""),
             column_ifexists("data", "")
         ))
| where EventTime between (datetime({start.isoformat()}) .. datetime({end.isoformat()}))
| where OpId in ({trace_ids})
    or tostring(Props["gen_ai.response.id"]) in ({response_ids})
    or tostring(Props["response.id"]) in ({response_ids})
| project EventTime, OpId, Parent, Span, EventName, Props,
          DurationMs=DurationValue,
          Success=SuccessValue,
          ResultCode=ResultCodeValue,
          DependencyType=DependencyTypeValue,
          Data=DataValue,
          SourceTable
| order by EventTime asc
""".strip()
    return query, start.astimezone(UTC), end.astimezone(UTC)


def _hex_id(value: Any, length: int, *, fallback: str) -> str:
    candidate = "".join(_HEX_RE.findall(str(value))).lower()
    if len(candidate) >= length:
        return candidate[-length:]
    return hashlib.sha256(fallback.encode()).hexdigest()[:length]


def _timestamp_ns(value: Any) -> int:
    if isinstance(value, datetime):
        timestamp = value
    else:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return int(timestamp.timestamp() * 1_000_000_000)


def _duration_ns(value: Any) -> int:
    if value is None:
        return 1
    if isinstance(value, timedelta):
        return max(1, int(value.total_seconds() * 1_000_000_000))
    if isinstance(value, (int, float)):
        return max(1, int(float(value) * 1_000_000))
    text = str(value)
    try:
        parts = text.split(":")
        seconds = (
            float(parts[-1])
            + (int(parts[-2]) * 60 if len(parts) > 1 else 0)
            + (int(parts[-3]) * 3600 if len(parts) > 2 else 0)
        )
        return max(1, int(seconds * 1_000_000_000))
    except (ValueError, IndexError):
        return 1


def _properties(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("Props", {})
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def _otlp_value(key: str, value: Any) -> dict[str, Any]:
    if (
        key.startswith("gen_ai.usage.")
        and key.endswith("tokens")
        and isinstance(value, str)
        and value.isdigit()
    ):
        value = int(value)
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [_otlp_value(key, item) for item in value]}}
    return {"stringValue": "" if value is None else str(value)}


def _matching_record(
    row: Mapping[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    operation_id = _hex_id(row.get("OpId"), 32, fallback="no-operation")
    props = _properties(row)
    response_values = {
        str(props.get("gen_ai.response.id", "")),
        str(props.get("response.id", "")),
    }
    for record in records:
        if operation_id == _hex_id(record["trace_id"], 32, fallback=str(record["trace_id"])):
            return record
        if str(record["response_id"]) in response_values:
            return record
    return None


def normalize_rows(
    rows: Iterable[Mapping[str, Any]],
    records: list[dict[str, Any]],
    *,
    include_content: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    correlated: set[tuple[str, int]] = set()
    spans: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        record = _matching_record(row, records)
        if record is None:
            continue
        correlated.add((str(record["session_id"]), int(record["turn_index"])))
        props = _properties(row)
        props.update(
            {
                "session.id": record["session_id"],
                "assert.run_id": record["run_id"],
                "assert.case_id": record["case_id"],
                "assert.turn_index": record["turn_index"],
                "assert.response_id": record["response_id"],
                "telemetry.source_table": row.get("SourceTable", ""),
            }
        )
        if row.get("DependencyType"):
            props["dependency.type"] = row["DependencyType"]
        if row.get("Data"):
            props["dependency.data"] = row["Data"]
        start_ns = _timestamp_ns(row["EventTime"])
        duration_ns = _duration_ns(row.get("DurationMs"))
        success = row.get("Success")
        failed = success is False or (
            str(row.get("ResultCode", "")).isdigit() and int(str(row["ResultCode"])) >= 400
        )
        trace_id = _hex_id(row.get("OpId"), 32, fallback=str(record["trace_id"]))
        span_id = _hex_id(
            row.get("Span"),
            16,
            fallback=f"{trace_id}:{index}:{row.get('EventName', '')}",
        )
        parent_id = _hex_id(
            row.get("Parent"),
            16,
            fallback=str(record["parent_span_id"]),
        )
        spans.append(
            {
                "traceId": trace_id,
                "spanId": span_id,
                "parentSpanId": parent_id,
                "name": str(row.get("EventName") or "application-insights-span"),
                "kind": 3 if row.get("DependencyType") else 1,
                "startTimeUnixNano": str(start_ns),
                "endTimeUnixNano": str(start_ns + duration_ns),
                "attributes": [
                    {"key": key, "value": _otlp_value(key, value)}
                    for key, value in sorted(redact(props, include_content=include_content).items())
                ],
                "status": {"code": "STATUS_CODE_ERROR" if failed else "STATUS_CODE_OK"},
            }
        )

    expected = {(str(record["session_id"]), int(record["turn_index"])) for record in records}
    missing = sorted(expected - correlated)
    completeness = {
        "complete": not missing,
        "expected_turns": len(expected),
        "correlated_turns": len(correlated),
        "missing": [
            {"session_id": session_id, "turn_index": turn_index}
            for session_id, turn_index in missing
        ],
    }
    otlp = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": "hotel-agent-assert-import"},
                        }
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "hotel_assert.app_insights_importer"},
                        "spans": spans,
                    }
                ],
            }
        ]
    }
    return otlp, completeness


def import_rows(
    *,
    rows: Iterable[Mapping[str, Any]],
    records: list[dict[str, Any]],
    output_directory: Path,
    include_content: bool = False,
) -> TraceImportResult:
    output_directory.mkdir(parents=True, exist_ok=True)
    otlp, completeness = normalize_rows(rows, records, include_content=include_content)
    otlp_path = output_directory / "traces.otlp.json"
    completeness_path = output_directory / "trace-completeness.json"
    otlp_path.write_text(json.dumps(otlp, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    completeness_path.write_text(
        json.dumps(completeness, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return TraceImportResult(
        otlp_path=otlp_path,
        completeness_path=completeness_path,
        complete=bool(completeness["complete"]),
        expected_turns=int(completeness["expected_turns"]),
        correlated_turns=int(completeness["correlated_turns"]),
    )
