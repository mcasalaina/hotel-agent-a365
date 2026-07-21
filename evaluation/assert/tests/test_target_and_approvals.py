from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hotel_assert.correlation import CorrelationLedger, ScenarioCorrelation
from hotel_assert.foundry import FoundryTargetConfig, _complete_approvals, invoke_hosted_agent
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
    monkeypatch.setenv("ASSERT_FABRIC_SNAPSHOT_ID", "assert-snapshot-1")
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
    assert captured["token"] == "secret-token"
    assert "assert.snapshot_id=assert-snapshot-1" in captured["baggage"]
    assert captured["metadata"] == {"assert_snapshot_id": "assert-snapshot-1"}


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
        "traceparent": "00-abc-def-01",
        "baggage": "assert.run_id=run-1",
    }
    result = await _complete_approvals(
        client,
        model="model",
        history=[{"role": "user", "content": "test"}],
        response=first,
        headers=headers,
        metadata={"assert_snapshot_id": "snapshot-1"},
    )
    assert result is final
    assert calls[0]["extra_headers"] == headers
    assert calls[0]["metadata"] == {"assert_snapshot_id": "snapshot-1"}
    assert calls[0]["extra_body"] == {"structured_inputs": {"assert_snapshot_id": "snapshot-1"}}
    assert calls[0]["input"][0] == {
        "role": "developer",
        "content": "ASSERT_EVALUATION_SNAPSHOT_ID:snapshot-1",
    }
    assert calls[0]["input"][-1] == {
        "type": "mcp_approval_response",
        "approve": True,
        "approval_request_id": "approval-1",
    }


@pytest.mark.asyncio
async def test_foundry_invocation_authenticates_with_agent_user_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    response = SimpleNamespace(
        id="response-1",
        output=[
            SimpleNamespace(
                type="message",
                role="assistant",
                content=[SimpleNamespace(type="output_text", text="answer")],
            )
        ],
    )

    class FakeResponses:
        async def create(self, **kwargs: Any) -> Any:
            captured["request"] = kwargs
            return response

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs
            self.responses = FakeResponses()

        async def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr("hotel_assert.foundry.AsyncOpenAI", FakeClient)
    text, response_id = await invoke_hosted_agent(
        config=FoundryTargetConfig(
            endpoint="https://example.test/project",
            agent_name="hotel-agent",
            model="model",
            api_version="2025-05-15-preview",
        ),
        token="agent-user-token",
        history=[{"role": "user", "content": "hello"}],
        traceparent="00-abc-def-01",
        baggage="assert.run_id=run-1",
        metadata={"assert_snapshot_id": "snapshot-1"},
    )

    assert (text, response_id) == ("answer", "response-1")
    authorization = captured["client"]["default_headers"]["Authorization"]
    assert authorization.endswith("agent-user-token")
    assert "x-ms-user-identity" not in captured["client"]["default_headers"]
    request_headers = captured["request"]["extra_headers"]
    assert request_headers["Authorization"].endswith("agent-user-token")
    assert "x-ms-user-identity" not in request_headers
    assert request_headers["traceparent"] == "00-abc-def-01"
    assert request_headers["baggage"] == "assert.run_id=run-1"
    assert captured["request"]["metadata"] == {"assert_snapshot_id": "snapshot-1"}
    assert captured["request"]["extra_body"] == {
        "structured_inputs": {"assert_snapshot_id": "snapshot-1"}
    }
    assert captured["request"]["input"][0] == {
        "role": "developer",
        "content": "ASSERT_EVALUATION_SNAPSHOT_ID:snapshot-1",
    }
    assert captured["closed"] is True
