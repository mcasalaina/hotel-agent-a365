from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from microsoft_agents_a365.notifications.agent_notification import NotificationTypes

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from email_prompt import build_email_prompt  # noqa: E402
from inbound_compat import NormalizedBodyRequest, normalize_known_entity_types  # noqa: E402

from agent import HotelServicingBridgeAgent  # noqa: E402


def test_email_prompt_preserves_exact_references_and_single_delivery_owner():
    prompt = build_email_prompt(
        SimpleNamespace(id="message-a", conversation_id="thread-a", html_body="Guest question")
    )
    assert "Email message id: message-a" in prompt
    assert "Email conversation id: thread-a" in prompt
    assert "actual sender" in prompt
    assert "Do not send, reply to, or forward any email yourself" in prompt
    assert "Guest question" in prompt


def test_entity_normalization_preserves_original_body_and_unknown_types():
    original = {
        "entities": [{"type": "productInfo", "name": "test"}, {"type": "customEntity"}],
        "text": "guest question",
    }
    normalized = normalize_known_entity_types(original)
    assert original["entities"][0]["type"] == "productInfo"
    assert normalized["entities"][0]["type"] == "ProductInfo"
    assert normalized["entities"][1] is original["entities"][1]
    assert normalized["text"] == original["text"]


def test_normalized_request_preserves_authentication_headers():
    class Request:
        headers = {"Authorization": "test-authentication"}
        claims_identity = object()

        async def json(self):
            return {"entities": [{"type": "productInfo"}]}

    request = Request()
    wrapped = NormalizedBodyRequest(request)
    assert wrapped.headers is request.headers
    assert wrapped.claims_identity is request.claims_identity
    assert asyncio.run(wrapped.json())["entities"][0]["type"] == "ProductInfo"


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setenv("AZURE_AI_FOUNDRY_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("FOUNDRY_AGENT_NAME", "hotel-servicing-agent")
    instance = HotelServicingBridgeAgent()
    calls = []

    class Responses:
        async def create(self, **kwargs):
            calls.append({**kwargs, "input": [dict(message) for message in kwargs["input"]]})
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="message",
                        role="assistant",
                        content=[SimpleNamespace(type="output_text", text="grounded answer")],
                    )
                ]
            )

    class Client:
        responses = Responses()

        async def close(self):
            pass

    async def client(token=None):
        assert token == "agent-user-token"
        return Client()

    async def exchange(*args):
        return "agent-user-token"

    monkeypatch.setattr(instance, "_client", client)
    monkeypatch.setattr(instance, "_exchange_user_token", exchange)
    return instance, calls


def context():
    return SimpleNamespace(
        activity=SimpleNamespace(from_property=SimpleNamespace(id="same-transport-sender"))
    )


def test_notification_threads_are_stateless_and_preserve_teams_history(bridge):
    instance, calls = bridge
    saved = [{"type": "message", "role": "user", "content": "teams history"}]
    instance.conversations["same-transport-sender"] = list(saved)
    for thread in ("thread-a", "thread-b"):
        notification = SimpleNamespace(
            notification_type=NotificationTypes.EMAIL_NOTIFICATION,
            email=SimpleNamespace(id=f"message-{thread}", conversation_id=thread, html_body=thread),
        )
        asyncio.run(
            instance.handle_agent_notification_activity(notification, None, "AGENTIC", context())
        )
    assert [len(call["input"]) for call in calls] == [1, 1]
    assert "thread-a" not in calls[1]["input"][0]["content"]
    assert instance.conversations["same-transport-sender"] == saved
    assert all("extra_headers" not in call for call in calls)


def test_failed_notification_does_not_clear_teams_history(bridge, monkeypatch):
    instance, _ = bridge
    saved = [{"type": "message", "role": "user", "content": "teams history"}]
    instance.conversations["same-transport-sender"] = list(saved)

    async def fail(*args, **kwargs):
        raise RuntimeError("Hosted invocation failed")

    monkeypatch.setattr(instance, "_call_foundry", fail)
    notification = SimpleNamespace(
        notification_type=NotificationTypes.EMAIL_NOTIFICATION,
        email=SimpleNamespace(id="message-a", html_body="guest question"),
    )
    result = asyncio.run(
        instance.handle_agent_notification_activity(notification, None, "AGENTIC", context())
    )
    assert "unavailable" in result
    assert instance.conversations["same-transport-sender"] == saved


def test_ordinary_teams_messages_preserve_history(bridge):
    instance, calls = bridge
    for message in ("first question", "follow-up question"):
        asyncio.run(instance.process_user_message(message, None, "AGENTIC", context()))
    assert len(calls[1]["input"]) == 3
    assert calls[1]["input"][0]["content"] == "first question"


def test_missing_authorization_handler_fails_closed(monkeypatch):
    monkeypatch.setenv("AZURE_AI_FOUNDRY_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("FOUNDRY_AGENT_NAME", "hotel-servicing-agent")
    instance = HotelServicingBridgeAgent()
    with pytest.raises(RuntimeError, match="authorization handler"):
        asyncio.run(instance._exchange_user_token(None, None, context()))
