from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

from hotel_servicing_agent.config import Settings
from hotel_servicing_agent.credentials import (
    select_async_azure_credential,
    select_azure_credential,
)
from hotel_servicing_agent.hosting import VoiceLiveAgentHost
from hotel_servicing_agent.tools import (
    WORK_IQ_AGENT_TOOLS,
    AgenticUserTokenProvider,
    FabricDataAgentTool,
    FabricReservationMutationTool,
    FoundryIQTool,
    WorkIQServer,
    WorkIQTool,
)


def create_agent(settings: Settings) -> Agent:
    credential = select_azure_credential()
    client = FoundryChatClient(
        project_endpoint=settings.project_endpoint,
        model=settings.model_deployment,
        credential=credential,
    )
    knowledge_tool = FoundryIQTool(
        search_endpoint=settings.search_endpoint,
        knowledge_base_name=settings.knowledge_base_name,
        credential=credential,
    )
    fabric_tool = FabricDataAgentTool(
        mcp_url=settings.fabric_data_agent_mcp_url,
        credential=credential,
    )
    reservation_tool = FabricReservationMutationTool(
        workspace_id=settings.fabric_workspace_id,
        guest_services_lakehouse_id=settings.fabric_guest_services_lakehouse_id,
        reservation_notebook_id=settings.fabric_reservation_notebook_id,
        credential=credential,
        verifier=fabric_tool.query,
    )
    work_iq_tool = WorkIQTool(
        project_endpoint=settings.project_endpoint,
        model_deployment=settings.model_deployment,
        credential=credential,
        token_provider=AgenticUserTokenProvider(
            tenant_id=settings.agent365_tenant_id,
            blueprint_client_id=settings.agent365_blueprint_client_id,
            instance_client_id=settings.agent365_instance_client_id,
            blueprint_secret_vault_url=settings.agent365_blueprint_secret_vault_url,
            blueprint_secret_name=settings.agent365_blueprint_secret_name,
            credential=credential,
        ),
        servers=tuple(
            WorkIQServer(
                name=name,
                url=url,
                audience=audience,
                allowed_tools=WORK_IQ_AGENT_TOOLS[name],
            )
            for name, url, audience in settings.work_iq_servers
        ),
    )
    return Agent(
        client=client,
        id=settings.agent365_instance_client_id,
        name="hotel-servicing-agent",
        description="Guest-services orchestration for a fictional hotel chain.",
        instructions=_instructions_with_current_utc_date(settings.instructions),
        default_options={"store": False},
        tools=[
            knowledge_tool.as_function_tool(),
            fabric_tool.as_function_tool(),
            reservation_tool.as_function_tool(),
            work_iq_tool.as_access_check_tool(),
            work_iq_tool.as_function_tool(),
            work_iq_tool.as_send_email_tool(),
            work_iq_tool.as_reply_to_email_tool(),
        ],
    )


def _instructions_with_current_utc_date(
    instructions: str,
    today: date | None = None,
) -> str:
    current_date = today or datetime.now(UTC).date()
    next_week_end = current_date + timedelta(days=6)
    return (
        f"{instructions.rstrip()}\n\n"
        "Authoritative time context:\n"
        f"- Today's UTC date is {current_date.isoformat()}.\n"
        f"- A relative next-7-days window is {current_date.isoformat()} through "
        f"{next_week_end.isoformat()}, inclusive.\n"
        "- Never infer the current date from model training data."
    )


async def run() -> None:
    settings = Settings.from_environment()
    voice_credential = select_async_azure_credential()
    async with voice_credential, create_agent(settings) as agent:
        server = VoiceLiveAgentHost(agent, settings, voice_credential)
        await server.run_async()


def main() -> None:
    asyncio.run(run())
