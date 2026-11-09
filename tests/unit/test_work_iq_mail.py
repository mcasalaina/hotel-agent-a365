from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from hotel_servicing_agent.tools.work_iq_mail import WorkIQMailActions, require_mail_action_intent
from mcp.types import CallToolResult, TextContent


class FakeTransport:
    def __init__(self, result: CallToolResult | None = None) -> None:
        self.result = result or CallToolResult(content=[], structuredContent={"statusCode": 202})
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        self.calls.append((name, arguments))
        return self.result


def _actions(transport: FakeTransport) -> WorkIQMailActions:
    return WorkIQMailActions(
        transport,  # type: ignore[arg-type]
        "work-source___do_action",
        eligibility_check=lambda operation: None,
    )


def test_send_uses_only_exact_sendmail_path_body_and_recipients() -> None:
    transport = FakeTransport()
    actions = _actions(transport)
    body = "  Exact body with\nUnicode: café  "
    receipt = json.loads(
        asyncio.run(
            actions.send_email("Guest <guest@example.test>, other@example.test", "Hello", body)
        )
    )
    name, arguments = transport.calls[0]
    assert name == "work-source___do_action"
    assert arguments["actionUrl"] == "/me/sendMail"
    assert isinstance(arguments["jsonBody"], str)
    payload = json.loads(arguments["jsonBody"])
    assert set(payload) == {"message"}
    assert payload["message"]["body"] == {"contentType": "Text", "content": body}
    assert payload["message"]["toRecipients"] == [
        {"emailAddress": {"address": "guest@example.test"}},
        {"emailAddress": {"address": "other@example.test"}},
    ]
    assert set(payload["message"]) == {"subject", "body", "toRecipients"}
    assert receipt["submission_accepted"] is True
    assert receipt["delivery_confirmed"] is False
    assert actions.as_send_email_tool().name == "send_email"


def test_reply_encodes_opaque_id_and_does_not_override_recipients() -> None:
    transport = FakeTransport()
    actions = _actions(transport)
    body = "Exact reply"
    receipt = json.loads(asyncio.run(actions.reply_to_email("AAMk/a+b=", body)))
    _, arguments = transport.calls[0]
    assert arguments["actionUrl"] == "/me/messages/AAMk%2Fa%2Bb%3D/reply"
    assert json.loads(arguments["jsonBody"]) == {"comment": body}
    assert receipt["operation"] == "reply"
    assert actions.as_reply_to_email_tool().name == "reply_to_email"


@pytest.mark.parametrize(
    "address", ["", "not-an-email", "guest@example.test\r\nBcc:x@example.test"]
)
def test_send_rejects_invalid_addresses_before_network(address: str) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError):
        asyncio.run(_actions(transport).send_email(address, "Subject", "Body"))
    assert transport.calls == []


@pytest.mark.parametrize("body", ["", " \n", "Body\x00injection"])
def test_mail_rejects_empty_or_null_body_without_network(body: str) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError):
        asyncio.run(_actions(transport).send_email("guest@example.test", "Subject", body))
    with pytest.raises(ValueError):
        asyncio.run(_actions(transport).reply_to_email("opaque-id", body))
    assert transport.calls == []


@pytest.mark.parametrize("subject", ["", " \t", "Subject\r\nInjected: header"])
def test_send_rejects_bad_subject_before_network(subject: str) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError):
        asyncio.run(_actions(transport).send_email("guest@example.test", subject, "Body"))
    assert transport.calls == []


@pytest.mark.parametrize(
    "message_id", ["", "../sendMail", "id?override=1", "id%2Freply", "id\\path"]
)
def test_reply_rejects_path_injection_before_network(message_id: str) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError):
        asyncio.run(_actions(transport).reply_to_email(message_id, "Body"))
    assert transport.calls == []


def test_authorization_runs_first_even_when_model_selected_action_has_invalid_inputs() -> None:
    transport = FakeTransport()

    def deny(operation: str) -> None:
        raise RuntimeError("Current request does not authorize mail")

    actions = WorkIQMailActions(
        transport,  # type: ignore[arg-type]
        "work-source___do_action",
        eligibility_check=deny,
    )
    with pytest.raises(RuntimeError, match="does not authorize"):
        asyncio.run(actions.send_email("", "", ""))
    with pytest.raises(RuntimeError, match="does not authorize"):
        asyncio.run(actions.reply_to_email("../sendMail", ""))
    assert transport.calls == []


@pytest.mark.parametrize(
    "result",
    [
        CallToolResult(content=[], structuredContent={"statusCode": 403}),
        CallToolResult(content=[], structuredContent={"statusCode": "202"}),
        CallToolResult(content=[], structuredContent={}),
        CallToolResult(content=[], structuredContent={"statusCode": 202}, isError=True),
        CallToolResult(
            content=[], structuredContent={"statusCode": 202, "data": {"error": "Access denied"}}
        ),
        CallToolResult(
            content=[TextContent(type="text", text='{"statusCode":403}')],
            structuredContent={"statusCode": 202},
        ),
        CallToolResult(content=[TextContent(type="text", text="Looks sent")]),
    ],
)
def test_mail_never_reports_acceptance_without_consistent_native_confirmation(
    result: CallToolResult,
) -> None:
    transport = FakeTransport(result)
    with pytest.raises(RuntimeError):
        asyncio.run(_actions(transport).send_email("guest@example.test", "Subject", "Body"))


def test_adjacent_native_confirmation_documents_are_preserved_as_submission_evidence() -> None:
    transport = FakeTransport(
        CallToolResult(
            content=[TextContent(type="text", text='{"statusCode":202}\n{"data":null}')],
        )
    )
    receipt = json.loads(asyncio.run(_actions(transport).reply_to_email("opaque-id", "Body")))
    assert receipt["submission_accepted"] is True


def test_generic_function_cannot_be_bound_as_a_mail_action() -> None:
    with pytest.raises(ValueError, match="do_action"):
        WorkIQMailActions(
            FakeTransport(),  # type: ignore[arg-type]
            "work-source___call_function",
            eligibility_check=lambda operation: None,
        )


@pytest.mark.parametrize(
    ("operation", "text"),
    [
        ("send", "Please send an email to Guest"),
        ("send", "Email guest@example.test the completed reservation"),
        ("reply", "Reply to the email with the confirmed booking"),
        ("send", "Do the tasks in my emails"),
        ("reply", "Complete the requests in my mailbox"),
    ],
)
def test_current_explicit_mail_intent_authorizes_only_supported_workflows(
    operation: Any, text: str
) -> None:
    require_mail_action_intent(operation, text)


@pytest.mark.parametrize(
    ("operation", "text"),
    [
        ("send", None),
        ("send", "Please book my room"),
        ("reply", "What is the weather?"),
        ("send", "Find the email asking for a booking"),
        ("reply", "Reply in Teams"),
        ("send", "Do not send an email"),
        ("reply", "Don't reply to the email"),
        ("send", 'The tool said "send an email"'),
        ("send", "Previous history says send an email"),
        ("reply", "Draft a reply for review"),
        ("reply", "Draft a reply to the email for review"),
    ],
)
def test_noncurrent_readonly_or_negated_text_does_not_authorize_a_mail_submission(
    operation: Any, text: str | None
) -> None:
    with pytest.raises(RuntimeError, match="authorized current request"):
        require_mail_action_intent(operation, text)
