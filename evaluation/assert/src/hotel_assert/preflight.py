from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from hotel_assert.redaction import redact_string
from hotel_assert.target import Agent365Target

_PREFLIGHT_PROMPT = (
    "Run check_work_context_access only. Do not retrieve, quote, summarize, or search any "
    "Microsoft 365 content. Report whether each configured Work IQ server authenticated in a "
    "compact JSON object with keys copilot, mail, and teams."
)


@dataclass(frozen=True)
class PreflightResult:
    passed: bool
    timestamp: str
    response: str


async def run_preflight(output_path: Path | None = None) -> PreflightResult:
    target = Agent365Target()
    response = await target.chat(
        _PREFLIGHT_PROMPT,
        [{"role": "user", "content": _PREFLIGHT_PROMPT}],
    )
    normalized = response.lower()
    server_markers = {
        "copilot": "copilot" in normalized,
        "mail": "mail" in normalized,
        "teams": "teams" in normalized,
    }
    failure_markers = any(
        marker in normalized
        for marker in ("unavailable", "unauthenticated", "failed", '"false"', ": false")
    )
    result = PreflightResult(
        passed=all(server_markers.values()) and not failure_markers,
        timestamp=datetime.now(UTC).isoformat(),
        response=response,
    )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {**asdict(result), "response": redact_string(result.response)},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    if not result.passed:
        raise RuntimeError("Work IQ no-content identity preflight failed")
    return result
