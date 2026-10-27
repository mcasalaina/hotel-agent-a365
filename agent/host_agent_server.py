import asyncio
import logging
import os
from os import environ

from aiohttp.web import Application, Request, Response, json_response, run_app
from aiohttp.web_middlewares import middleware as web_middleware
from microsoft_agents.activity import Activity, load_configuration_from_env
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.aiohttp import (
    CloudAdapter,
    jwt_authorization_middleware,
    start_agent_process,
)
from microsoft_agents.hosting.core import (
    AgentApplication,
    AgentAuthConfiguration,
    AuthenticationConstants,
    Authorization,
    ClaimsIdentity,
    MemoryStorage,
    RouteRank,
    TurnContext,
    TurnState,
)
from microsoft_agents_a365.notifications import EmailResponse
from microsoft_agents_a365.notifications.agent_notification import (
    AgentNotification,
    AgentNotificationActivity,
    ChannelId,
    NotificationTypes,
)
from microsoft_agents_a365.observability.core.config import configure
from microsoft_agents_a365.observability.core.middleware.baggage_builder import (
    BaggageBuilder,
)
from microsoft_agents_a365.runtime.environment_utils import (
    get_observability_authentication_scope,
)

from agent_interface import AgentInterface, validate_agent_class
from inbound_compat import NormalizedBodyRequest
from token_cache import cache_agentic_token

logger = logging.getLogger(__name__)


class NormalizingCloudAdapter(CloudAdapter):
    """CloudAdapter that canonicalizes known entity types before Activity validation.

    The Agent 365 email channel sends a lowerCamelCase ``productInfo`` entity that the pinned
    SDK rejects, which surfaced as HTTP 500 before any handler ran. Authentication is untouched:
    claims are still read from the wrapped request.
    """

    async def process_request(self, request, agent):
        if request is not None:
            request = NormalizedBodyRequest(request)
        return await super().process_request(request, agent)


def create_and_run_host(agent_class: type[AgentInterface]) -> None:
    validate_agent_class(agent_class)
    configure(
        service_name="HotelGuestServicesAgentTracing",
        service_namespace="HotelGuestServicesAgent",
    )
    host = GenericAgentHost(agent_class)
    host.start_server(host.create_auth_configuration())


class GenericAgentHost:
    def __init__(self, agent_class: type[AgentInterface]) -> None:
        validate_agent_class(agent_class)
        self.auth_handler_name = os.getenv("AUTH_HANDLER_NAME") or None
        self.agent_class = agent_class
        self.agent_instance: AgentInterface | None = None

        configuration = load_configuration_from_env(environ)
        self.storage = MemoryStorage()
        self.connection_manager = MsalConnectionManager(**configuration)
        self.adapter = NormalizingCloudAdapter(connection_manager=self.connection_manager)
        self.authorization = Authorization(
            self.storage,
            self.connection_manager,
            **configuration,
        )
        self.agent_app = AgentApplication[TurnState](
            storage=self.storage,
            adapter=self.adapter,
            authorization=self.authorization,
            **configuration,
        )
        self.agent_notification = AgentNotification(self.agent_app)
        self._register_handlers()

    async def _prepare_turn(self, context: TurnContext):
        if self.agent_instance is None:
            await context.send_activity("The hotel service is not available.")
            return None

        recipient = context.activity.recipient
        tenant_id = recipient.tenant_id
        agent_id = recipient.agentic_app_id
        if self.auth_handler_name:
            try:
                token = await self.agent_app.auth.exchange_token(
                    context,
                    scopes=get_observability_authentication_scope(),
                    auth_handler_id=self.auth_handler_name,
                )
                cache_agentic_token(tenant_id, agent_id, token.token)
            except Exception:
                logger.exception("Agent 365 observability token exchange failed")
        return tenant_id, agent_id

    def _handler_options(self) -> dict:
        if self.auth_handler_name:
            return {"auth_handlers": [self.auth_handler_name]}
        return {}

    def _register_handlers(self) -> None:
        options = self._handler_options()

        async def help_handler(context: TurnContext, _: TurnState) -> None:
            await context.send_activity(
                "Hello. I can help with hotel properties, reservations, folios, "
                "special requests, and maintenance requests."
            )

        self.agent_app.conversation_update("membersAdded", **options)(help_handler)
        self.agent_app.message("/help", **options)(help_handler)

        # Notifications are also "message" activities without text. Rank the catch-all message
        # route last and the notification route first so notifications are never swallowed here.
        @self.agent_app.activity("message", rank=RouteRank.LAST, **options)
        async def on_message(context: TurnContext, _: TurnState) -> None:
            prepared = await self._prepare_turn(context)
            if prepared is None:
                return
            tenant_id, agent_id = prepared
            message = context.activity.text or ""
            if not message.strip() or message.strip() == "/help":
                return

            with BaggageBuilder().tenant_id(tenant_id).agent_id(agent_id).build():
                typing_task = None
                channel_id = getattr(context.activity, "channel_id", "") or ""
                if "email" not in channel_id.lower():
                    await context.send_activity(Activity(type="typing"))
                    typing_task = asyncio.create_task(self._send_typing(context))
                try:
                    response = await self.agent_instance.process_user_message(
                        message,
                        self.agent_app.auth,
                        self.auth_handler_name,
                        context,
                    )
                    await context.send_activity(response)
                finally:
                    if typing_task:
                        typing_task.cancel()
                        try:
                            await typing_task
                        except asyncio.CancelledError:
                            pass

        @self.agent_notification.on_agent_notification(
            channel_id=ChannelId(channel="agents", sub_channel="*"),
            rank=RouteRank.FIRST,
            **options,
        )
        async def on_notification(
            context: TurnContext,
            _: TurnState,
            notification_activity: AgentNotificationActivity,
        ) -> None:
            prepared = await self._prepare_turn(context)
            if prepared is None:
                return
            tenant_id, agent_id = prepared
            logger.info(
                "Agent notification received: type=%s",
                notification_activity.notification_type,
            )
            with BaggageBuilder().tenant_id(tenant_id).agent_id(agent_id).build():
                handler = getattr(
                    self.agent_instance,
                    "handle_agent_notification_activity",
                    None,
                )
                if handler is None:
                    await context.send_activity(
                        "This notification type is not supported."
                    )
                    return
                response = await handler(
                    notification_activity,
                    self.agent_app.auth,
                    self.auth_handler_name,
                    context,
                )
                if (
                    notification_activity.notification_type
                    == NotificationTypes.EMAIL_NOTIFICATION
                ):
                    await context.send_activity(
                        EmailResponse.create_email_response_activity(response)
                    )
                else:
                    await context.send_activity(response)
                logger.info(
                    "Agent notification reply sent: type=%s",
                    notification_activity.notification_type,
                )

    @staticmethod
    async def _send_typing(context: TurnContext) -> None:
        try:
            while True:
                await asyncio.sleep(4)
                await context.send_activity(Activity(type="typing"))
        except asyncio.CancelledError:
            return

    async def initialize_agent(self, _app: Application) -> None:
        self.agent_instance = self.agent_class()
        await self.agent_instance.initialize()

    async def cleanup(self, _app: Application) -> None:
        if self.agent_instance:
            await self.agent_instance.cleanup()

    @staticmethod
    def create_auth_configuration() -> AgentAuthConfiguration | None:
        client_id = environ.get("CLIENT_ID")
        tenant_id = environ.get("TENANT_ID")
        client_secret = environ.get("CLIENT_SECRET")
        if client_id and tenant_id and client_secret:
            return AgentAuthConfiguration(
                client_id=client_id,
                tenant_id=tenant_id,
                client_secret=client_secret,
                scopes=["5a807f24-c9de-44ee-a3a7-329e88a00ffc/.default"],
            )
        if environ.get("WEBSITE_SITE_NAME"):
            raise RuntimeError("Agent 365 authentication is not configured")
        return None

    def start_server(
        self,
        auth_configuration: AgentAuthConfiguration | None,
    ) -> None:
        async def messages(request: Request) -> Response:
            return await start_agent_process(
                request,
                request.app["agent_app"],
                request.app["adapter"],
            )

        async def health(_request: Request) -> Response:
            return json_response(
                {
                    "status": "ok",
                    "agent": self.agent_class.__name__,
                    "initialized": self.agent_instance is not None,
                }
            )

        middlewares = []
        if auth_configuration:

            @web_middleware
            async def jwt_with_health_bypass(request, handler):
                if request.path == "/api/health":
                    return await handler(request)
                return await jwt_authorization_middleware(request, handler)

            middlewares.append(jwt_with_health_bypass)
        else:

            @web_middleware
            async def local_claims(request, handler):
                request["claims_identity"] = ClaimsIdentity(
                    {
                        AuthenticationConstants.AUDIENCE_CLAIM: "local",
                        AuthenticationConstants.APP_ID_CLAIM: "local",
                    },
                    False,
                    "Local",
                )
                return await handler(request)

            middlewares.append(local_claims)

        app = Application(middlewares=middlewares)
        app.router.add_post("/api/messages", messages)
        app.router.add_get("/api/messages", lambda _: Response(status=200))
        app.router.add_get("/api/health", health)
        app["agent_configuration"] = auth_configuration
        app["agent_app"] = self.agent_app
        app["adapter"] = self.agent_app.adapter
        app.on_startup.append(self.initialize_agent)
        app.on_shutdown.append(self.cleanup)

        run_app(
            app,
            host="0.0.0.0",
            port=int(environ.get("PORT", "3978")),
            handle_signals=True,
        )
