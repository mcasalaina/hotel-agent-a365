from __future__ import annotations

import hashlib
import json
import secrets
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


def _now() -> str:
    return datetime.now(UTC).isoformat()


def case_id_for_history(history: list[dict[str, str]]) -> str:
    first_user = next(
        (item.get("content", "") for item in history if item.get("role") == "user"),
        "",
    )
    return f"case-{hashlib.sha256(first_user.encode()).hexdigest()[:16]}"


def is_first_turn(history: list[dict[str, str]]) -> bool:
    return sum(item.get("role") == "user" for item in history) == 1


def make_traceparent() -> tuple[str, str, str]:
    trace_id = secrets.token_hex(16)
    span_id = secrets.token_hex(8)
    return f"00-{trace_id}-{span_id}-01", trace_id, span_id


@dataclass(frozen=True)
class CorrelationRecord:
    run_id: str
    case_id: str
    session_id: str
    turn_index: int
    trace_id: str
    parent_span_id: str
    response_id: str
    started_at: str
    completed_at: str
    identity: dict[str, str | int | None]


class CorrelationLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: CorrelationRecord) -> None:
        serialized = json.dumps(asdict(record), sort_keys=True, separators=(",", ":"))
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Malformed correlation ledger line {line_number}: {self.path}"
                ) from exc
            UUID(record["session_id"])
            records.append(record)
        return records


class ScenarioCorrelation:
    def __init__(self, run_id: str, ledger: CorrelationLedger) -> None:
        self.run_id = run_id
        self.ledger = ledger
        self.case_id = ""
        self.session_id = ""
        self.turn_index = 0

    def begin_turn(self, history: list[dict[str, str]]) -> dict[str, str | int]:
        if is_first_turn(history) or not self.session_id:
            self.case_id = case_id_for_history(history)
            self.session_id = str(uuid4())
            self.turn_index = 0
        self.turn_index += 1
        traceparent, trace_id, parent_span_id = make_traceparent()
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "session_id": self.session_id,
            "turn_index": self.turn_index,
            "traceparent": traceparent,
            "trace_id": trace_id,
            "parent_span_id": parent_span_id,
            "started_at": _now(),
        }


def completed_at() -> str:
    return _now()
