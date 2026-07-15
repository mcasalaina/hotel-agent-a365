from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from hotel_servicing_agent.tools import work_iq
from hotel_servicing_agent.tools.work_iq import (
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

    assert answer == "Grounded work context"
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
    with pytest.raises(ValueError, match="requires a read-only tool allowlist"):
        WorkIQServer("mail", "https://example.test/mail", "audience", ())

    mutating_fragments = ("create", "delete", "send", "post", "reply", "update", "add")
    for allowed_tools in WORK_IQ_READ_ONLY_TOOLS.values():
        assert allowed_tools
        assert not any(
            fragment.lower() in tool_name.lower()
            for tool_name in allowed_tools
            for fragment in mutating_fragments
        )
