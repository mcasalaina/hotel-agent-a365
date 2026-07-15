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
WORK_IQ_AGENT_TOOLS = {
    **WORK_IQ_READ_ONLY_TOOLS,
    "work-iq-mail": (
        *WORK_IQ_READ_ONLY_TOOLS["work-iq-mail"],
        "CreateDraftMessage",
        "ReplyAllToMessage",
        "ReplyToMessage",
        "SendDraftMessage",
        "SendEmailWithAttachments",
        "UpdateDraft",
        "CreateMessage",
        "SendDraft",
        "SendMail",
        "Reply",
        "ReplyAll",
        "mcp_MailTools_graph_mail_createMessage",
        "mcp_MailTools_graph_mail_getMessage",
        "mcp_MailTools_graph_mail_reply",
        "mcp_MailTools_graph_mail_replyAll",
        "mcp_MailTools_graph_mail_searchMessages",
        "mcp_MailTools_graph_mail_sendDraft",
        "mcp_MailTools_graph_mail_sendMail",
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
            raise ValueError(f"Work IQ server {self.name} requires a tool allowlist")

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
    """Delegates the agent's Microsoft 365 work to governed Work IQ MCP servers."""

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
                "Read and act on my own Microsoft 365 context through Work IQ, including my email, "
                "Teams messages, files, meetings, and organizational knowledge. Use the mail tools "
                "to send an email when the request explicitly asks me to send one."
            ),
            func=self.query,
        )

    def as_access_check_tool(self) -> FunctionTool:
        return FunctionTool(
            name="check_work_context_access",
            description=(
                "Verify whether I can access my own Microsoft 365 work context without reading its "
                "content. Use this before claiming that my mailbox or other work context is "
                "available."
            ),
            func=self.check_access,
        )

    def as_send_email_tool(self) -> FunctionTool:
        return FunctionTool(
            name="send_email",
            description=(
                "Send a new email from my mailbox. Use only for an explicitly requested send. "
                "Provide the exact recipients, subject, and body."
            ),
            func=self.send_email,
        )

    def as_reply_to_email_tool(self) -> FunctionTool:
        return FunctionTool(
            name="reply_to_email",
            description=(
                "Send an immediate reply from my mailbox to an email identified by its "
                "folder-specific message ID. Provide the exact reply body."
            ),
            func=self.reply_to_email,
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
        return await self._query(question.strip(), self._servers)

    async def _query(self, question: str, servers: Sequence[WorkIQServer]) -> str:
        user_id = current_agent_user_id()
        tokens = {
            server.name: await self._token_provider.get_token(user_id, server.scope)
            for server in servers
        }
        return await self._query_runner(
            self._project_endpoint,
            self._model_deployment,
            self._credential,
            servers,
            tokens,
            question,
        )

    async def send_email(self, recipient_emails: str, subject: str, body: str) -> str:
        recipients = recipient_emails.strip()
        if not recipients:
            raise ValueError("recipient_emails must not be empty")
        if not subject.strip():
            raise ValueError("subject must not be empty")
        if not body.strip():
            raise ValueError("body must not be empty")
        return await self._query(
            "Send a new email now using SendEmailWithAttachments, with no attachments. "
            f"Recipients: {recipients}\n"
            f"Subject: {subject.strip()}\n"
            f"Exact body:\n{body.strip()}\n"
            "Do not create a draft. Report success only after the mail tool confirms the send.",
            self._mail_servers(),
        )

    async def reply_to_email(self, message_id: str, body: str) -> str:
        resolved_message_id = message_id.strip()
        if not resolved_message_id:
            raise ValueError("message_id must not be empty")
        if not body.strip():
            raise ValueError("body must not be empty")
        return await self._query(
            "Reply to the email with the following folder-specific message ID now using "
            "ReplyToMessage with sendImmediately set to true.\n"
            f"Message ID: {resolved_message_id}\n"
            f"Exact reply body:\n{body.strip()}\n"
            "Do not create a draft. Report success only after the mail tool confirms the send.",
            self._mail_servers(),
        )

    def _mail_servers(self) -> tuple[WorkIQServer, ...]:
        mail_servers = tuple(server for server in self._servers if "mail" in server.name.casefold())
        if not mail_servers:
            raise RuntimeError("No Work IQ mail server is configured")
        return mail_servers


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
                "You are the Hotel Guest Services agent operating in your own Microsoft 365 "
                "account. Email, Teams messages, files, and meetings returned by these tools "
                "belong to you, not to the human speaking with you. Refer to them as 'my email', "
                "'my mailbox', or 'my messages'. Use the most appropriate Work IQ server. Report "
                "when evidence is unavailable. Send an email or reply only when the request "
                "explicitly asks you to send it. For a new email, use the mail server's "
                "SendEmailWithAttachments tool directly, even when there are no attachments. "
                "For a reply, use ReplyToMessage with sendImmediately set to true. "
                "When returning an email task, include both its Internet Message ID for idempotent "
                "actions and its folder-specific message ID for replies. The folder-specific ID is "
                "the id field returned by SearchMessagesQueryParameters. Never omit either ID. "
                "Report a send only after the mail tool succeeds. "
                "Do not expose MCP names, permission scopes, identifiers, or other implementation "
                "details."
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
