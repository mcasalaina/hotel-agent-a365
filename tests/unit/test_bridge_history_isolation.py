"""Regression tests: notification turns never share or touch hosted conversation history."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

pytest.importorskip("microsoft_agents_a365")

import agent as bridge  # noqa: E402


class FakeResponses:
    def __init__(self):
        self.inputs = []

    async def create(self, model, input):
        self.inputs.append([dict(m) for m in input])
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    role="assistant",
                    content=[SimpleNamespace(type="output_text", text="ok")],
                )
            ],
            output_text="ok",
        )


class FakeClient:
    def __init__(self, responses):
        self.responses = responses

    async def close(self):
        pass


def make_agent(monkeypatch):
    monkeypatch.setenv("AZURE_AI_FOUNDRY_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("FOUNDRY_AGENT_NAME", "hotel-servicing-agent")
    instance = bridge.HotelServicingBridgeAgent()
    responses = FakeResponses()

    async def fake_client(token=None):
        return FakeClient(responses)

    monkeypatch.setattr(instance, "_client", fake_client)
    monkeypatch.setattr(instance, "_assistant_text", lambda response: "ok")

    async def fake_approvals(client, history, response):
        return response

    monkeypatch.setattr(instance, "_complete_approvals", fake_approvals)
    return instance, responses


def context(sender="agent-transport-id"):
    return SimpleNamespace(
        activity=SimpleNamespace(from_property=SimpleNamespace(id=sender))
    )


def notification(conversation_id, body):
    email = SimpleNamespace(
        id=f"MSG-{conversation_id}", conversation_id=conversation_id, html_body=body
    )
    return SimpleNamespace(
        notification_type=bridge.NotificationTypes.EMAIL_NOTIFICATION, email=email
    )


def run(coro):
    return asyncio.run(coro)


def test_same_sender_different_email_threads_share_no_history(monkeypatch):
    agent, responses = make_agent(monkeypatch)
    for conv, body in (("CONV-A", "first thread"), ("CONV-B", "second thread")):
        run(agent.handle_agent_notification_activity(notification(conv, body), None, None, context()))
    assert [len(i) for i in responses.inputs] == [1, 1]
    assert "first thread" not in responses.inputs[1][0]["content"]
    assert agent.conversations == {}


def test_notification_does_not_read_write_or_clear_teams_history(monkeypatch):
    agent, responses = make_agent(monkeypatch)
    saved = [{"type": "message", "role": "user", "content": "teams hello"}]
    agent.conversations["agent-transport-id"] = list(saved)
    run(agent.handle_agent_notification_activity(notification("CONV-A", "mail"), None, None, context()))
    assert len(responses.inputs[0]) == 1
    assert agent.conversations["agent-transport-id"] == saved

    async def boom(*args, **kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(agent, "_call_foundry", boom)
    run(agent.handle_agent_notification_activity(notification("CONV-B", "mail"), None, None, context()))
    assert agent.conversations["agent-transport-id"] == saved


def test_teams_path_still_retains_history(monkeypatch):
    agent, responses = make_agent(monkeypatch)
    run(agent.process_user_message("hello", None, None, context("teams-user")))
    run(agent.process_user_message("again", None, None, context("teams-user")))
    assert len(responses.inputs[1]) == 3
    assert responses.inputs[1][0]["content"] == "hello"
