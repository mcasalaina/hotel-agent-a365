from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from email.headerregistry import Address
from email.utils import getaddresses
from typing import Any, Literal
from urllib.parse import quote

from agent_framework import FunctionTool
from mcp.types import CallToolResult

from hotel_servicing_agent.tools.toolbox import FoundryToolboxTransport

type MailOperation = Literal["send", "reply"]

_QUOTED = re.compile(r"""```.*?```|"(?:[^"\\]|\\.)*"|“[^”]*”|^>.*$""", re.DOTALL | re.MULTILINE)
_MAIL_TASK = re.compile(
    r"\b(?:do|complete|process|handle|take\s+care\s+of)\b.{0,60}"
    r"\b(?:tasks?|requests?)\b.{0,60}\b(?:emails?|e-mails?|mailbox|inbox)\b",
    re.IGNORECASE,
)
_SEND_REQUEST = re.compile(
    r"\bsend\b.{0,40}\b(?:email|e-mail|mail|note)\b|"
    r"^(?:please\s+)?(?:email|e-mail)\s+",
    re.IGNORECASE,
)
_REPLY_REQUEST = re.compile(
    r"\b(?:reply|respond)\b.{0,50}\b(?:email|e-mail|mail|mailbox|inbox)\b",
    re.IGNORECASE,
)


def require_mail_action_intent(operation: MailOperation, current_user_text: str | None) -> None:
    if operation not in ("send", "reply"):
        raise ValueError("Unsupported dedicated mail operation")
    if current_user_text is None:
        raise RuntimeError("Mail submission requires an authorized current request")
    text = _QUOTED.sub(" ", unicodedata.normalize("NFKC", current_user_text).casefold()).strip()
    action = r"(?:send|email|e-mail)" if operation == "send" else r"(?:reply|respond)"
    negated = re.search(
        rf"\b(?:do\s+not|don't|dont|never|skip|avoid|without)\b[^;.!?\n]{{0,60}}\b{action}\b",
        text,
    )
    metadata = re.search(
        rf"\b(?:tool|model|assistant|history|previous|prior)\b.{{0,60}}\b{action}\b", text
    )
    requested = _SEND_REQUEST.search(text) if operation == "send" else _REPLY_REQUEST.search(text)
    draft_only = re.search(r"\b(?:draft|for\s+review)\b", text)
    if negated or metadata or draft_only or not (requested or _MAIL_TASK.search(text)):
        raise RuntimeError("Mail submission requires an authorized current request")


class WorkIQMailActions:
    """Dedicated mail submissions without model-controlled paths or raw action exposure."""

    def __init__(
        self,
        transport: FoundryToolboxTransport,
        tool_name: str,
        *,
        eligibility_check: Callable[[MailOperation], None],
    ) -> None:
        if tool_name.rsplit("___", maxsplit=1)[-1] != "do_action":
            raise ValueError("Mail actions require the verified native do_action binding")
        self._transport = transport
        self._tool_name = tool_name
        self._eligibility_check = eligibility_check

    def as_send_email_tool(self) -> FunctionTool:
        return FunctionTool(
            name="send_email",
            description=(
                "Submit a new email only for an explicitly authorized send or mailbox task. "
                "Provide exact recipient email addresses, subject, and plain-text body. "
                "Acceptance does not prove delivery."
            ),
            func=self.send_email,
        )

    def as_reply_to_email_tool(self) -> FunctionTool:
        return FunctionTool(
            name="reply_to_email",
            description=(
                "Submit a reply only for an authorized reply or mailbox task. Provide the "
                "folder-specific message ID and exact reply body. The original message determines "
                "reply recipients; this does not create a draft or send a reply-all."
            ),
            func=self.reply_to_email,
        )

    async def send_email(self, recipient_emails: str, subject: str, body: str) -> str:
        self._eligibility_check("send")
        recipients = _recipient_addresses(recipient_emails)
        if not subject.strip() or any(character in subject for character in "\r\n\x00"):
            raise ValueError(
                "Email subject must be nonempty and contain no header control characters"
            )
        _validate_body(body)
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": address}} for address in recipients],
            }
        }
        result = await self._transport.call(
            self._tool_name,
            {"actionUrl": "/me/sendMail", "jsonBody": json.dumps(payload, ensure_ascii=False)},
        )
        _require_accepted_submission(result)
        return _receipt("send", recipient_count=len(recipients))

    async def reply_to_email(self, message_id: str, body: str) -> str:
        self._eligibility_check("reply")
        if not re.fullmatch(r"[A-Za-z0-9_+=/-]+", message_id):
            raise ValueError("Reply requires a valid opaque folder-specific message ID")
        _validate_body(body)
        result = await self._transport.call(
            self._tool_name,
            {
                "actionUrl": f"/me/messages/{quote(message_id, safe='')}/reply",
                "jsonBody": json.dumps({"comment": body}, ensure_ascii=False),
            },
        )
        _require_accepted_submission(result)
        return _receipt("reply")


def _recipient_addresses(value: str) -> list[str]:
    if not value.strip() or any(character in value for character in "\r\n\x00"):
        raise ValueError(
            "Email recipients must be valid addresses without header control characters"
        )
    recipients: list[str] = []
    for _, address in getaddresses([value], strict=True):
        try:
            parsed = Address(addr_spec=address)
        except (ValueError, IndexError):
            raise ValueError("Email recipient address is invalid") from None
        if not parsed.username or not parsed.domain:
            raise ValueError("Email recipient address is invalid")
        if parsed.addr_spec not in recipients:
            recipients.append(parsed.addr_spec)
    if not recipients:
        raise ValueError("At least one valid email recipient is required")
    return recipients


def _validate_body(body: str) -> None:
    if not body.strip() or "\x00" in body:
        raise ValueError("Email body must be nonempty and contain no null characters")


def _require_accepted_submission(result: CallToolResult) -> None:
    if result.isError:
        raise RuntimeError("Work IQ mail submission failed")
    documents: list[dict[str, Any]] = []
    if result.structuredContent is not None:
        documents.append(result.structuredContent)
    for block in result.content:
        if block.type != "text" or not block.text.strip():
            continue
        decoder = json.JSONDecoder()
        remaining = block.text.strip()
        while remaining:
            try:
                document, end = decoder.raw_decode(remaining)
            except json.JSONDecodeError:
                raise RuntimeError("Work IQ returned an unreadable mail confirmation") from None
            if not isinstance(document, dict):
                raise RuntimeError("Work IQ returned an invalid mail confirmation")
            documents.append(document)
            remaining = remaining[end:].lstrip()
    statuses = [document["statusCode"] for document in documents if "statusCode" in document]
    if (
        not statuses
        or any(type(status) is not int or status != 202 for status in statuses)
        or any(
            document.get("error")
            or (isinstance(document.get("data"), dict) and document["data"].get("error"))
            for document in documents
        )
    ):
        raise RuntimeError("Work IQ did not confirm an accepted mail submission")


def _receipt(operation: MailOperation, *, recipient_count: int | None = None) -> str:
    return json.dumps(
        {
            "operation": operation,
            "submission_accepted": True,
            "status_code": 202,
            "delivery_confirmed": False,
            "recipient_count": recipient_count,
        },
        separators=(",", ":"),
    )
