from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hotel_assert.correlation import CorrelationLedger, ScenarioCorrelation
from hotel_assert.foundry import _complete_approvals
from hotel_assert.identity import ValidatedIdentity
from hotel_assert.target import Agent365Target


class FakeSidecar:
    async def acquire(self) -> ValidatedIdentity:
        return ValidatedIdentity(
            token="secret-token",
            claim_digest="digest",
            tenant_id="tenant",
            audience="audience",
            agent_user_id="agent-user",
            agent_identity_id="agent",
            parent_blueprint_id="parent",
            issued_at=1,
            expires_at=2,
        )


@pytest.mark.asyncio
async def test_target_does_not_duplicate_current_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_invoke(**kwargs: Any) -> tuple[str, str]:
        captured.update(kwargs)
        return "answer", "response-1"

    monkeypatch.setattr("hotel_assert.target.invoke_hosted_agent", fake_invoke)
    target = Agent365Target.__new__(Agent365Target)
    target.sidecar = FakeSidecar()
    target.foundry = SimpleNamespace()
    target.correlation = ScenarioCorrelation(
        "run-1",
        CorrelationLedger(tmp_path / "ledger.jsonl"),
    )
    history = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "current"},
    ]
    assert await target.chat("current", history) == "answer"
    assert captured["history"] == history
    assert captured["history"].count({"role": "user", "content": "current"}) == 1
    assert captured["agent_user_id"] == "agent-user"


@pytest.mark.asyncio
async def test_target_requires_message_to_match_history(tmp_path: Path) -> None:
    target = Agent365Target.__new__(Agent365Target)
    target.sidecar = FakeSidecar()
    target.foundry = SimpleNamespace()
    target.correlation = ScenarioCorrelation(
        "run-1",
        CorrelationLedger(tmp_path / "ledger.jsonl"),
    )
    with pytest.raises(ValueError, match="final user turn"):
        await target.chat("different", [{"role": "user", "content": "current"}])


@pytest.mark.asyncio
async def test_approval_continuation_preserves_identity_and_trace_headers() -> None:
    request = SimpleNamespace(type="mcp_approval_request", id="approval-1")
    first = SimpleNamespace(output=[request])
    final = SimpleNamespace(output=[SimpleNamespace(type="message")])
    calls: list[dict[str, Any]] = []

    async def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return final

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    headers = {
        "x-ms-user-identity": "agent-user",
        "traceparent": "00-abc-def-01",
        "baggage": "assert.run_id=run-1",
    }
    result = await _complete_approvals(
        client,
        model="model",
        history=[{"role": "user", "content": "test"}],
        response=first,
        headers=headers,
    )
    assert result is final
    assert calls[0]["extra_headers"] == headers
    assert calls[0]["input"][-1] == {
        "type": "mcp_approval_response",
        "approve": True,
        "approval_request_id": "approval-1",
    }
