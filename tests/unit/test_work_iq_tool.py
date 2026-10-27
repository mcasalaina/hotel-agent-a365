from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from hotel_servicing_agent.language import LANGUAGE_RESPONSE_GUIDANCE
from hotel_servicing_agent.tools import work_iq
from hotel_servicing_agent.tools.work_iq import (
    WORK_IQ_AGENT_TOOLS,
    WORK_IQ_READ_ONLY_TOOLS,
    AgenticUserTokenProvider,
    WorkIQAuthenticationUnavailableError,
    WorkIQServer,
    WorkIQTool,
)


def test_agentic_user_provider_uses_three_step_token_exchange() -> None:
    requested_scopes: list[str] = []
    requests: list[dict[str, list[str]]] = []

    class FakeAccessToken:
        token = "key-vault-token"

    class FakeCredential:
        def get_token(self, scope: str) -> FakeAccessToken:
            requested_scopes.append(scope)
            return FakeAccessToken()

    def handle_request(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.path == "/secrets/blueprint-secret"
            assert request.headers["Authorization"] == "Bearer key-vault-token"
            return httpx.Response(200, json={"value": "blueprint-client-secret"})
        requests.append(parse_qs(request.content.decode()))
        return httpx.Response(
            200,
            json={"access_token": f"token-{len(requests)}"},
        )

    transport = httpx.MockTransport(handle_request)
    provider = AgenticUserTokenProvider(
        tenant_id="tenant-id",
        blueprint_client_id="blueprint-id",
        instance_client_id="instance-id",
        blueprint_secret_vault_url="https://vault.example.test",
        blueprint_secret_name="blueprint-secret",
        credential=FakeCredential(),
        http_client_factory=lambda: httpx.AsyncClient(transport=transport),
    )

    token = asyncio.run(provider.get_token("agent-user-id", "audience/scope"))

    assert token == "token-3"
    assert requested_scopes == [work_iq.KEY_VAULT_SCOPE]
    assert requests[0]["client_id"] == ["blueprint-id"]
    assert requests[0]["client_secret"] == ["blueprint-client-secret"]
    assert requests[0]["fmi_path"] == ["instance-id"]
    assert requests[1]["client_id"] == ["instance-id"]
    assert requests[1]["client_assertion"] == ["token-1"]
    assert requests[2]["grant_type"] == ["user_fic"]
    assert requests[2]["scope"] == ["audience/scope"]
    assert requests[2]["client_assertion"] == ["token-1"]
    assert requests[2]["user_federated_identity_credential"] == ["token-2"]
    assert requests[2]["user_id"] == ["agent-user-id"]


def test_work_iq_tool_uses_agent_user_and_per_server_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeTokenProvider:
        async def get_token(self, user_id: str, scope: str) -> str:
            captured.setdefault("token_calls", []).append((user_id, scope))
            return f"token-for-{scope}"

    async def fake_query_runner(
        project_endpoint: str,
        model_deployment: str,
        credential: Any,
        servers: tuple[WorkIQServer, ...],
        tokens: dict[str, str],
        question: str,
    ) -> str:
        captured.update(
            project_endpoint=project_endpoint,
            model_deployment=model_deployment,
            credential=credential,
            servers=servers,
            tokens=tokens,
            question=question,
        )
        return "Grounded work context"

    monkeypatch.setattr(work_iq, "current_agent_user_id", lambda: "agent-user-id")
    servers = (
        WorkIQServer("mail", "https://example.test/mail", "mail-audience", ("search",)),
        WorkIQServer("teams", "https://example.test/teams", "teams-audience", ("list",)),
    )
    tool = WorkIQTool(
        project_endpoint="https://example.test/project",
        model_deployment="model",
        credential=object(),
        token_provider=FakeTokenProvider(),  # type: ignore[arg-type]
        servers=servers,
        query_runner=fake_query_runner,
    )

    answer = asyncio.run(tool.query("  Find the recent guest email  "))

    assert answer.endswith("Tool evidence:\nGrounded work context")
    assert "use the user's established conversation language" in answer
    assert captured["question"] == "Find the recent guest email"
    assert captured["token_calls"] == [
        ("agent-user-id", "mail-audience/Tools.ListInvoke.All"),
        ("agent-user-id", "teams-audience/Tools.ListInvoke.All"),
    ]
    assert captured["tokens"]["mail"].startswith("token-for-mail-audience")


def test_work_iq_tool_rejects_empty_questions() -> None:
    tool = WorkIQTool(
        project_endpoint="https://example.test/project",
        model_deployment="model",
        credential=object(),
        token_provider=object(),  # type: ignore[arg-type]
        servers=(WorkIQServer("mail", "https://example.test/mail", "audience", ("search",)),),
    )

    with pytest.raises(ValueError, match="question must not be empty"):
        asyncio.run(tool.query(" "))


def test_work_iq_mail_action_tools_issue_explicit_send_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    questions: list[str] = []

    class FakeTokenProvider:
        async def get_token(self, user_id: str, scope: str) -> str:
            return "delegated-token"

    async def fake_query_runner(
        project_endpoint: str,
        model_deployment: str,
        credential: Any,
        servers: tuple[WorkIQServer, ...],
        tokens: dict[str, str],
        question: str,
    ) -> str:
        questions.append(question)
        return "Mail tool confirmed the send."

    monkeypatch.setattr(work_iq, "current_agent_user_id", lambda: "agent-user-id")
    tool = WorkIQTool(
        project_endpoint="https://example.test/project",
        model_deployment="model",
        credential=object(),
        token_provider=FakeTokenProvider(),  # type: ignore[arg-type]
        servers=(WorkIQServer("mail", "https://example.test/mail", "audience", ("send",)),),
        query_runner=fake_query_runner,
    )

    send_result = asyncio.run(
        tool.send_email(
            "maria@example.test",
            "Reservation update",
            "Your reservation is confirmed.",
            cc_emails="marco@example.test",
        )
    )
    reply_result = asyncio.run(
        tool.reply_to_email(
            "folder-message-id",
            "Your reservation number is RES-TEST.",
            cc_emails="marco@example.test",
        )
    )

    assert send_result.endswith("Tool evidence:\nMail tool confirmed the send.")
    assert reply_result.endswith("Tool evidence:\nMail tool confirmed the send.")
    assert "SendEmailWithAttachments" in questions[0]
    assert "To recipients: maria@example.test" in questions[0]
    assert "CC recipients: marco@example.test" in questions[0]
    assert "ReplyToMessage" in questions[1]
    assert "sendImmediately set to true" in questions[1]
    assert "folder-message-id" in questions[1]
    assert "Additional CC recipients: marco@example.test" in questions[1]
    assert tool.as_send_email_tool().name == "send_email"
    assert tool.as_reply_to_email_tool().name == "reply_to_email"


@pytest.mark.parametrize(
    ("user_request", "body"),
    [
        (
            "Réponds en français à Maria García concernant le voiturier du "
            "Lyrenza Scottsdale Sonoran Resort.",
            "Bonjour Maria, le voiturier du Lyrenza Scottsdale Sonoran Resort coûte "
            "25 dollars américains par nuit.",
        ),
        (
            "María et Chen séjournent au Lyrenza Scottsdale Sonoran Resort. "
            "Peux-tu leur répondre au sujet du voiturier ?",
            "Bonjour María et Chen, le voiturier du Lyrenza Scottsdale Sonoran Resort "
            "coûte 25 dollars américains par nuit.",
        ),
        (
            "María and Chen are visiting Lyrenza Scottsdale Sonoran Resort. "
            "Reply in English with the nightly valet parking fee.",
            "Hello María and Chen, valet parking at Lyrenza Scottsdale Sonoran Resort "
            "costs USD 25 per night.",
        ),
    ],
)
def test_mail_reply_preserves_language_with_foreign_names(
    monkeypatch: pytest.MonkeyPatch,
    user_request: str,
    body: str,
) -> None:
    questions: list[str] = []

    class FakeTokenProvider:
        async def get_token(self, user_id: str, scope: str) -> str:
            return "test-delegated-token"

    async def fake_query_runner(
        project_endpoint: str,
        model_deployment: str,
        credential: Any,
        servers: tuple[WorkIQServer, ...],
        tokens: dict[str, str],
        question: str,
    ) -> str:
        questions.append(question)
        return "Mail tool confirmed the reply."

    monkeypatch.setattr(work_iq, "current_agent_user_id", lambda: "agent-user-id")
    tool = WorkIQTool(
        project_endpoint="https://example.test/project",
        model_deployment="model",
        credential=object(),
        token_provider=FakeTokenProvider(),  # type: ignore[arg-type]
        servers=(WorkIQServer("mail", "https://example.test/mail", "audience", ("reply",)),),
        query_runner=fake_query_runner,
    )

    evidence = asyncio.run(tool.query(user_request))
    result = asyncio.run(tool.reply_to_email("folder-message-id", body))

    assert questions[0] == user_request
    actual_body = (
        questions[1]
        .split("Exact reply body:\n", 1)[1]
        .split("\nPreserve the additional CC recipient list exactly.", 1)[0]
    )
    assert actual_body == body
    assert (
        evidence
        == result
        == (f"{LANGUAGE_RESPONSE_GUIDANCE}\n\nTool evidence:\nMail tool confirmed the reply.")
    )
    assert "latest complete utterance is authoritative" in result
    assert "not from the visitors' names" in result


def test_work_iq_mail_actions_do_not_depend_on_unrelated_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_calls: list[str] = []
    queried_servers: list[str] = []

    class PartiallyAvailableTokenProvider:
        async def get_token(self, user_id: str, scope: str) -> str:
            token_calls.append(scope)
            if scope.startswith("teams-audience/"):
                raise WorkIQAuthenticationUnavailableError("Teams is unavailable")
            return "mail-token"

    async def fake_query_runner(
        project_endpoint: str,
        model_deployment: str,
        credential: Any,
        servers: tuple[WorkIQServer, ...],
        tokens: dict[str, str],
        question: str,
    ) -> str:
        queried_servers.extend(server.name for server in servers)
        return "Email sent."

    monkeypatch.setattr(work_iq, "current_agent_user_id", lambda: "agent-user-id")
    tool = WorkIQTool(
        project_endpoint="https://example.test/project",
        model_deployment="model",
        credential=object(),
        token_provider=PartiallyAvailableTokenProvider(),  # type: ignore[arg-type]
        servers=(
            WorkIQServer("work-iq-mail", "https://example.test/mail", "mail-audience", ("send",)),
            WorkIQServer(
                "work-iq-teams",
                "https://example.test/teams",
                "teams-audience",
                ("list",),
            ),
        ),
        query_runner=fake_query_runner,
    )

    result = asyncio.run(
        tool.send_email(
            "guest@example.test",
            "Reservation update",
            "Your reservation is confirmed.",
        )
    )

    assert result.endswith("Tool evidence:\nEmail sent.")
    assert queried_servers == ["work-iq-mail"]
    assert token_calls == ["mail-audience/Tools.ListInvoke.All"]


def test_work_iq_access_check_verifies_tokens_without_retrieving_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    class FakeTokenProvider:
        async def get_token(self, user_id: str, scope: str) -> str:
            calls.append((user_id, scope))
            return "delegated-token"

    monkeypatch.setattr(work_iq, "current_agent_user_id", lambda: "agent-user-id")
    tool = WorkIQTool(
        project_endpoint="https://example.test/project",
        model_deployment="model",
        credential=object(),
        token_provider=FakeTokenProvider(),  # type: ignore[arg-type]
        servers=(WorkIQServer("mail", "https://example.test/mail", "audience", ("search",)),),
    )

    result = json.loads(asyncio.run(tool.check_access()))

    assert result == {
        "authenticated_user_context": True,
        "available_servers": ["mail"],
        "content_retrieved": False,
    }
    assert calls == [("agent-user-id", "audience/Tools.ListInvoke.All")]
    assert tool.as_access_check_tool().name == "check_work_context_access"


def test_work_iq_access_check_reports_missing_user_context_without_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_user_context() -> str:
        raise RuntimeError("missing user context")

    monkeypatch.setattr(work_iq, "current_agent_user_id", no_user_context)
    tool = WorkIQTool(
        project_endpoint="https://example.test/project",
        model_deployment="model",
        credential=object(),
        token_provider=object(),  # type: ignore[arg-type]
        servers=(WorkIQServer("mail", "https://example.test/mail", "audience", ("search",)),),
    )

    result = json.loads(asyncio.run(tool.check_access()))

    assert result == {
        "authenticated_user_context": False,
        "available_servers": [],
        "content_retrieved": False,
        "reason": "No authenticated Agent 365 user context was supplied with this request.",
    }


def test_work_iq_access_check_reports_missing_delegated_token_without_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableTokenProvider:
        async def get_token(self, user_id: str, scope: str) -> str:
            raise WorkIQAuthenticationUnavailableError("no matching user FIC")

    monkeypatch.setattr(work_iq, "current_agent_user_id", lambda: "agent-user-id")
    tool = WorkIQTool(
        project_endpoint="https://example.test/project",
        model_deployment="model",
        credential=object(),
        token_provider=UnavailableTokenProvider(),  # type: ignore[arg-type]
        servers=(WorkIQServer("mail", "https://example.test/mail", "audience", ("search",)),),
    )

    result = json.loads(asyncio.run(tool.check_access()))

    assert result == {
        "authenticated_user_context": False,
        "available_servers": [],
        "content_retrieved": False,
        "reason": "Delegated Agent 365 user authentication is unavailable.",
    }


def test_work_iq_servers_fail_closed_with_read_only_allowlists() -> None:
    with pytest.raises(ValueError, match="requires a tool allowlist"):
        WorkIQServer("mail", "https://example.test/mail", "audience", ())

    mutating_fragments = ("create", "delete", "send", "post", "reply", "update", "add")
    for allowed_tools in WORK_IQ_READ_ONLY_TOOLS.values():
        assert allowed_tools
        assert not any(
            fragment.lower() in tool_name.lower()
            for tool_name in allowed_tools
            for fragment in mutating_fragments
        )


def test_agent_mailbox_allowlist_supports_read_and_send_without_delete() -> None:
    mail_tools = WORK_IQ_AGENT_TOOLS["work-iq-mail"]

    assert "GetMessage" in mail_tools
    assert "CreateDraftMessage" in mail_tools
    assert "ReplyAllToMessage" in mail_tools
    assert "ReplyToMessage" in mail_tools
    assert "SendDraftMessage" in mail_tools
    assert "SendEmailWithAttachments" in mail_tools
    assert "UpdateDraft" in mail_tools
    assert "SendMail" in mail_tools
    assert "mcp_MailTools_graph_mail_sendMail" in mail_tools
    assert not any("delete" in tool_name.lower() for tool_name in mail_tools)
