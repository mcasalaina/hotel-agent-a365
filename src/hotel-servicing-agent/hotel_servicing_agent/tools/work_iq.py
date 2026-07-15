from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from dataclasses import dataclass
from typing import Any

import httpx
from agent_framework import Agent, FunctionTool, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.core.exceptions import ClientAuthenticationError

from hotel_servicing_agent.hosting import current_agent_user_id

WORK_IQ_SCOPE = "Tools.ListInvoke.All"
TOKEN_EXCHANGE_SCOPE = "api://AzureADTokenExchange/.default"
KEY_VAULT_SCOPE = "https://vault.azure.net/.default"
CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
WORK_IQ_READ_ONLY_TOOLS = {
    "work-iq-copilot": ("copilot_chat",),
    "work-iq-mail": (
        "GetMessage",
        "SearchMessages",
        "SearchMessagesQueryParameters",
        "GetAttachments",
        "DownloadAttachment",
    ),
    "work-iq-teams": (
        "ListTeams",
        "ListChats",
        "ListChannels",
        "GetTeam",
        "ListTeamMembers",
        "GetChat",
        "GetChannel",
        "ListChatMembers",
        "ListChannelMembers",
        "ListChannelFiles",
        "ListChatMessages",
        "ListChannelMessages",
        "GetChatMessage",
        "ListChannelMessageReplies",
        "GetRichMessageFormats",
        "GetUserPresence",
        "SearchTeamsMessages",
        "SearchTeamMessagesQueryParameters",
    ),
}
WorkIQQueryRunner = Callable[
    [str, str, Any, Sequence["WorkIQServer"], dict[str, str], str],
    Awaitable[str],
]
HttpClientFactory = Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]]


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


class WorkIQAuthenticationUnavailableError(RuntimeError):
    """Raised when Agent 365 cannot establish delegated Work IQ authentication."""


class AgenticUserTokenProvider:
    """Acquires delegated Work IQ tokens for the current Agent 365 user."""

    def __init__(
        self,
        tenant_id: str,
        blueprint_client_id: str,
        instance_client_id: str,
        blueprint_secret_vault_url: str,
        blueprint_secret_name: str,
        credential: Any,
        http_client_factory: HttpClientFactory | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._blueprint_client_id = blueprint_client_id
        self._instance_client_id = instance_client_id
        self._blueprint_secret_vault_url = blueprint_secret_vault_url.rstrip("/")
        self._blueprint_secret_name = blueprint_secret_name
        self._blueprint_secret: str | None = None
        self._credential = credential
        self._http_client_factory = http_client_factory or (lambda: httpx.AsyncClient(timeout=30))

    async def get_token(self, agent_user_id: str, scope: str) -> str:
        async with self._http_client_factory() as client:
            blueprint_secret = await self._get_blueprint_secret(client)
            blueprint_token = await self._exchange(
                client,
                "blueprint",
                {
                    "client_id": self._blueprint_client_id,
                    "scope": TOKEN_EXCHANGE_SCOPE,
                    "grant_type": "client_credentials",
                    "client_secret": blueprint_secret,
                    "fmi_path": self._instance_client_id,
                },
            )
            instance_token = await self._exchange(
                client,
                "instance",
                {
                    "client_id": self._instance_client_id,
                    "scope": TOKEN_EXCHANGE_SCOPE,
                    "grant_type": "client_credentials",
                    "client_assertion_type": CLIENT_ASSERTION_TYPE,
                    "client_assertion": blueprint_token,
                },
            )
            return await self._exchange(
                client,
                "delegated user",
                {
                    "client_id": self._instance_client_id,
                    "scope": scope,
                    "grant_type": "user_fic",
                    "client_assertion_type": CLIENT_ASSERTION_TYPE,
                    "client_assertion": blueprint_token,
                    "user_federated_identity_credential": instance_token,
                    "user_id": agent_user_id,
                },
            )

    async def _get_blueprint_secret(self, client: httpx.AsyncClient) -> str:
        if self._blueprint_secret:
            return self._blueprint_secret
        try:
            access_token = await asyncio.to_thread(
                self._credential.get_token,
                KEY_VAULT_SCOPE,
            )
        except ClientAuthenticationError as exc:
            raise WorkIQAuthenticationUnavailableError(
                "Hosted Agent identity could not authenticate to Key Vault"
            ) from exc
        url = f"{self._blueprint_secret_vault_url}/secrets/{self._blueprint_secret_name}"
        try:
            response = await client.get(
                url,
                params={"api-version": "7.5"},
                headers={"Authorization": f"Bearer {access_token.token}"},
            )
        except httpx.HTTPError as exc:
            raise WorkIQAuthenticationUnavailableError(
                "Agent 365 blueprint credential retrieval failed"
            ) from exc
        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise WorkIQAuthenticationUnavailableError("Key Vault returned invalid JSON") from exc
        secret = body.get("value")
        if not response.is_success or not secret:
            error = body.get("error", {})
            code = error.get("code", "unknown_error")
            message = error.get("message", "No description")
            raise WorkIQAuthenticationUnavailableError(
                f"Agent 365 blueprint credential retrieval failed: {code}: {message}"
            )
        self._blueprint_secret = str(secret)
        return self._blueprint_secret

    async def _exchange(
        self,
        client: httpx.AsyncClient,
        stage: str,
        data: dict[str, str],
    ) -> str:
        url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        try:
            response = await client.post(url, data=data)
        except httpx.HTTPError as exc:
            raise WorkIQAuthenticationUnavailableError(
                f"Agent 365 {stage} token exchange request failed"
            ) from exc
        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise WorkIQAuthenticationUnavailableError(
                f"Agent 365 {stage} token exchange returned invalid JSON"
            ) from exc
        token = body.get("access_token")
        if response.is_success and token:
            return str(token)
        error = body.get("error", "unknown_error")
        description = body.get("error_description", "No description")
        raise WorkIQAuthenticationUnavailableError(
            f"Agent 365 {stage} token exchange failed: {error}: {description}"
        )


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

    def as_access_check_tool(self) -> FunctionTool:
        return FunctionTool(
            name="check_work_context_access",
            description=(
                "Verify whether this request has authenticated user-scoped Work IQ access without "
                "reading Microsoft 365 content. Use this before making any claim that Work IQ is "
                "available."
            ),
            func=self.check_access,
        )

    async def check_access(self) -> str:
        try:
            user_id = current_agent_user_id()
        except RuntimeError:
            return json.dumps(
                {
                    "authenticated_user_context": False,
                    "available_servers": [],
                    "content_retrieved": False,
                    "reason": (
                        "No authenticated Agent 365 user context was supplied with this request."
                    ),
                },
                separators=(",", ":"),
            )
        available_servers: list[str] = []
        for server in self._servers:
            try:
                await self._token_provider.get_token(user_id, server.scope)
            except WorkIQAuthenticationUnavailableError:
                return json.dumps(
                    {
                        "authenticated_user_context": False,
                        "available_servers": [],
                        "content_retrieved": False,
                        "reason": "Delegated Agent 365 user authentication is unavailable.",
                    },
                    separators=(",", ":"),
                )
            available_servers.append(server.name)
        return json.dumps(
            {
                "authenticated_user_context": True,
                "available_servers": available_servers,
                "content_retrieved": False,
            },
            separators=(",", ":"),
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
