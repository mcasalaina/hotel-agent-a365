from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import httpx
from agent_framework import Agent, FunctionTool, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from microsoft_agents.authentication.msal import MsalAuth
from microsoft_agents.hosting.core import AgentAuthConfiguration, AuthTypes

from hotel_servicing_agent.hosting import current_agent_user_id

WORK_IQ_SCOPE = "Tools.ListInvoke.All"
WORK_IQ_READ_ONLY_TOOLS = {
    "work-iq-copilot": ("ask", "list_agents"),
    "work-iq-mail": (
        "mcp_MailTools_graph_mail_getMessage",
        "mcp_MailTools_graph_mail_listSent",
        "mcp_MailTools_graph_mail_searchMessages",
    ),
    "work-iq-teams": (
        "mcp_graph_chat_getChat",
        "mcp_graph_chat_getChatMessage",
        "mcp_graph_chat_listChatMembers",
        "mcp_graph_chat_listChatMessages",
        "mcp_graph_chat_listChats",
        "mcp_graph_teams_getChannel",
        "mcp_graph_teams_getTeam",
        "mcp_graph_teams_listChannelMembers",
        "mcp_graph_teams_listChannelMessages",
        "mcp_graph_teams_listChannels",
        "mcp_graph_teams_listTeams",
    ),
}
WorkIQQueryRunner = Callable[
    [str, str, Any, Sequence["WorkIQServer"], dict[str, str], str],
    Awaitable[str],
]


@dataclass(frozen=True, slots=True)
class WorkIQServer:
    name: str
    url: str
    audience: str
    allowed_tools: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.allowed_tools:
            raise ValueError(f"Work IQ server {self.name} requires a read-only tool allowlist")

    @property
    def scope(self) -> str:
        return f"{self.audience}/{WORK_IQ_SCOPE}"


class AgenticUserTokenProvider:
    """Acquires delegated Work IQ tokens for the current Agent 365 user."""

    def __init__(
        self,
        tenant_id: str,
        blueprint_client_id: str,
        instance_client_id: str,
    ) -> None:
        self._tenant_id = tenant_id
        self._instance_client_id = instance_client_id
        self._auth = MsalAuth(
            AgentAuthConfiguration(
                auth_type=AuthTypes.identity_proxy_manager,
                client_id=blueprint_client_id,
                tenant_id=tenant_id,
            )
        )

    async def get_token(self, agent_user_id: str, scope: str) -> str:
        token = await self._auth.get_agentic_user_token(
            tenant_id=self._tenant_id,
            agent_app_instance_id=self._instance_client_id,
            agentic_user_id=agent_user_id,
            scopes=[scope],
        )
        if not token:
            raise RuntimeError(f"Agent 365 did not issue a delegated token for {scope}")
        return str(token)


class WorkIQTool:
    """Delegates Microsoft 365 questions to governed Work IQ MCP servers."""

    def __init__(
        self,
        project_endpoint: str,
        model_deployment: str,
        credential: Any,
        token_provider: AgenticUserTokenProvider,
        servers: Sequence[WorkIQServer],
        query_runner: WorkIQQueryRunner | None = None,
    ) -> None:
        if not servers:
            raise ValueError("At least one Work IQ server is required")
        self._project_endpoint = project_endpoint
        self._model_deployment = model_deployment
        self._credential = credential
        self._token_provider = token_provider
        self._servers = tuple(servers)
        self._query_runner = query_runner or _query_work_iq

    def as_function_tool(self) -> FunctionTool:
        return FunctionTool(
            name="query_work_context",
            description=(
                "Query the authenticated user's Microsoft 365 context through Work IQ, including "
                "mail, Teams, files, meetings, and organizational knowledge. This Phase 2 tool is "
                "read-only and may draft text but must not send or modify Microsoft 365 content."
            ),
            func=self.query,
        )

    async def query(self, question: str) -> str:
        if not question.strip():
            raise ValueError("question must not be empty")
        user_id = current_agent_user_id()
        tokens = {
            server.name: await self._token_provider.get_token(user_id, server.scope)
            for server in self._servers
        }
        return await self._query_runner(
            self._project_endpoint,
            self._model_deployment,
            self._credential,
            self._servers,
            tokens,
            question.strip(),
        )


async def _query_work_iq(
    project_endpoint: str,
    model_deployment: str,
    credential: Any,
    servers: Sequence[WorkIQServer],
    tokens: dict[str, str],
    question: str,
) -> str:
    tools: list[MCPStreamableHTTPTool] = []
    async with AsyncExitStack() as stack:
        for server in servers:
            client = await stack.enter_async_context(
                httpx.AsyncClient(
                    headers={"Authorization": f"Bearer {tokens[server.name]}"},
                    timeout=120,
                )
            )
            tools.append(
                MCPStreamableHTTPTool(
                    name=server.name,
                    url=server.url,
                    http_client=client,
                    description=f"Governed Microsoft 365 tools from {server.name}",
                    allowed_tools=server.allowed_tools,
                )
            )

        specialist = Agent(
            client=FoundryChatClient(
                project_endpoint=project_endpoint,
                model=model_deployment,
                credential=credential,
            ),
            name="work-context-specialist",
            instructions=(
                "Answer only from the authenticated user's Microsoft 365 context. Use the most "
                "appropriate Work IQ server and report when access or evidence is unavailable. "
                "You may draft text, but never send, post, delete, or modify Microsoft 365 content."
            ),
            default_options={"store": False},
            tools=tools,
        )
        try:
            await specialist.__aenter__()
        except BaseException:
            await specialist.__aexit__(None, None, None)
            raise
        stack.push_async_exit(specialist.__aexit__)
        response = await specialist.run(question)
        answer = response.text.strip()
        if not answer:
            raise RuntimeError("Work IQ returned no answer")
        return answer
