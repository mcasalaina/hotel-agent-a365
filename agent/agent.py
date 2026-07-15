import logging
import os
from typing import Optional

from azure.identity.aio import DefaultAzureCredential
from microsoft_agents.hosting.core import Authorization, TurnContext
from microsoft_agents_a365.notifications.agent_notification import NotificationTypes
from openai import AsyncOpenAI

from agent_interface import AgentInterface

logger = logging.getLogger(__name__)

_API_VERSION = "2025-11-15-preview"
_DEFAULT_SCOPE = "https://ai.azure.com/.default"


class HotelServicingBridgeAgent(AgentInterface):
    """Agent 365 ingress that delegates all intelligence to the Foundry Hosted Agent."""

    def __init__(self) -> None:
        self.endpoint = os.environ["AZURE_AI_FOUNDRY_ENDPOINT"].rstrip("/")
        self.agent_name = os.environ["FOUNDRY_AGENT_NAME"]
        self.model = os.getenv("FOUNDRY_MODEL_NAME", "gpt-5.4-mini")
        self.user_scopes = [
            scope.strip()
            for scope in os.getenv("FOUNDRY_USER_TOKEN_SCOPES", _DEFAULT_SCOPE).split(",")
            if scope.strip()
        ]
        self.credential = DefaultAzureCredential()
        self.conversations: dict[str, list[dict[str, str]]] = {}

    async def _client(self, bearer_token: Optional[str] = None) -> AsyncOpenAI:
        token = bearer_token
        if token is None:
            token = (await self.credential.get_token(_DEFAULT_SCOPE)).token
        return AsyncOpenAI(
            api_key="unused",
            base_url=(
                f"{self.endpoint}/agents/{self.agent_name}/endpoint/protocols/openai"
            ),
            default_query={"api-version": _API_VERSION},
            default_headers={"Authorization": f"Bearer {token}"},
        )

    async def initialize(self) -> None:
        client = await self._client()
        try:
            response = await client.responses.create(
                model=self.model,
                input="Reply with READY only.",
            )
            logger.info(
                "Hosted Agent connectivity established: name=%s status=%s",
                self.agent_name,
                response.status,
            )
        except Exception:
            logger.exception(
                "Hosted Agent startup check failed; the next Teams turn will retry"
            )
        finally:
            await client.close()

    async def cleanup(self) -> None:
        await self.credential.close()

    async def process_user_message(
        self,
        message: str,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
    ) -> str:
        activity = context.activity
        from_property = activity.from_property
        agentic_user_id = (
            activity.get_agentic_user()
            if hasattr(activity, "get_agentic_user")
            else None
        )
        user_id = agentic_user_id or getattr(from_property, "id", None) or "anonymous"

        try:
            user_token = await self._exchange_user_token(
                auth,
                auth_handler_name,
                context,
            )
            return await self._call_foundry(user_id, message, user_token)
        except Exception:
            self.conversations.pop(user_id, None)
            logger.exception("Hosted Agent invocation failed for the current Teams turn")
            return (
                "I could not complete that request because the hotel service is unavailable. "
                "Please try again."
            )

    async def handle_agent_notification_activity(
        self,
        notification_activity,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
    ) -> str:
        notification_type = notification_activity.notification_type
        if notification_type == NotificationTypes.EMAIL_NOTIFICATION:
            email = notification_activity.email
            body = getattr(email, "html_body", "") or getattr(email, "body", "")
            message = (
                "A guest-services email notification was received. Review it and respond "
                f"according to the hotel servicing policy.\n\n{body}"
            )
        elif notification_type == NotificationTypes.WPX_COMMENT:
            message = (
                "A guest-services document comment was received. Review it and respond "
                f"according to the hotel servicing policy.\n\n{notification_activity.text or ''}"
            )
        else:
            message = notification_activity.text or (
                f"Guest-services notification received: {notification_type}"
            )
        return await self.process_user_message(
            message,
            auth,
            auth_handler_name,
            context,
        )

    async def _exchange_user_token(
        self,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
    ) -> Optional[str]:
        if not auth_handler_name:
            logger.warning("Agentic user authorization handler is not configured")
            return None

        try:
            token_response = await auth.exchange_token(
                context,
                scopes=self.user_scopes,
                auth_handler_id=auth_handler_name,
            )
        except Exception:
            logger.exception("Agentic user token exchange failed")
            return None

        if not token_response or not token_response.token:
            logger.warning("Agentic user token exchange returned no token")
            return None

        logger.info("Agentic user token exchange succeeded")
        return token_response.token

    async def _call_foundry(
        self,
        user_id: str,
        message: str,
        user_token: Optional[str],
    ) -> str:
        history = list(self.conversations.get(user_id, []))
        history.append({"type": "message", "role": "user", "content": message})

        client = await self._client(user_token)
        try:
            response = await client.responses.create(
                model=self.model,
                input=history,
                extra_headers={"x-ms-user-identity": user_id},
            )
            response = await self._complete_approvals(
                client,
                history,
                response,
                user_id,
            )
        finally:
            await client.close()

        assistant_text = self._assistant_text(response)
        if not assistant_text:
            raise RuntimeError("Hosted Agent returned no assistant message")

        history.append(
            {
                "type": "message",
                "role": "assistant",
                "content": assistant_text,
            }
        )
        self.conversations[user_id] = history[-40:]
        return assistant_text

    async def _complete_approvals(self, client, history, response, user_id):
        for _ in range(5):
            approvals = [
                item
                for item in response.output
                if getattr(item, "type", None) == "mcp_approval_request"
            ]
            if not approvals:
                return response

            approval_input = list(response.output)
            approval_input.extend(
                {
                    "type": "mcp_approval_response",
                    "approve": True,
                    "approval_request_id": item.id,
                }
                for item in approvals
            )
            response = await client.responses.create(
                model=self.model,
                input=history + approval_input,
                extra_headers={"x-ms-user-identity": user_id},
            )
        raise RuntimeError("Hosted Agent exceeded the MCP approval limit")

    @staticmethod
    def _assistant_text(response) -> str:
        for item in response.output:
            if (
                getattr(item, "type", None) == "message"
                and getattr(item, "role", None) == "assistant"
            ):
                texts = [
                    content.text
                    for content in item.content
                    if getattr(content, "type", None) == "output_text"
                ]
                if texts:
                    return "\n".join(texts)
        return ""
