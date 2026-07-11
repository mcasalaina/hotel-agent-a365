from __future__ import annotations

import asyncio
from typing import Any

import pytest
from hotel_servicing_agent.tools import work_iq
from hotel_servicing_agent.tools.work_iq import (
    WORK_IQ_READ_ONLY_TOOLS,
    WorkIQServer,
    WorkIQTool,
)


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
