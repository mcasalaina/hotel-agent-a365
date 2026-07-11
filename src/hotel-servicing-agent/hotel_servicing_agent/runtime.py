from __future__ import annotations

import asyncio

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

from hotel_servicing_agent.config import Settings
from hotel_servicing_agent.credentials import select_azure_credential
from hotel_servicing_agent.hosting import Agent365ResponsesHostServer
from hotel_servicing_agent.tools import (
    WORK_IQ_READ_ONLY_TOOLS,
    AgenticUserTokenProvider,
    FabricDataAgentTool,
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
    work_iq_tool = WorkIQTool(
        project_endpoint=settings.project_endpoint,
        model_deployment=settings.model_deployment,
        credential=credential,
        token_provider=AgenticUserTokenProvider(
            tenant_id=settings.agent365_tenant_id,
            blueprint_client_id=settings.agent365_blueprint_client_id,
            instance_client_id=settings.agent365_instance_client_id,
        ),
        servers=tuple(
            WorkIQServer(
                name=name,
                url=url,
                audience=audience,
                allowed_tools=WORK_IQ_READ_ONLY_TOOLS[name],
            )
            for name, url, audience in settings.work_iq_servers
        ),
    )
    return Agent(
        client=client,
        name="hotel-servicing-agent",
        description="Guest-services orchestration for a fictional hotel chain.",
        instructions=settings.instructions,
        default_options={"store": False},
        tools=[
            knowledge_tool.as_function_tool(),
            fabric_tool.as_function_tool(),
            work_iq_tool.as_function_tool(),
        ],
    )


async def run() -> None:
    settings = Settings.from_environment()
    async with create_agent(settings) as agent:
        server = Agent365ResponsesHostServer(agent)
        await server.run_async()


def main() -> None:
    asyncio.run(run())
