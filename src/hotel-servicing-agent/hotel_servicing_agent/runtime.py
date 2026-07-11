from __future__ import annotations

import asyncio

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer

from hotel_servicing_agent.config import Settings
from hotel_servicing_agent.credentials import select_azure_credential
from hotel_servicing_agent.tools import FabricDataAgentTool, FoundryIQTool


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
    return Agent(
        client=client,
        name="hotel-servicing-agent",
        description="Guest-services orchestration for a fictional hotel chain.",
        instructions=settings.instructions,
        default_options={"store": False},
        tools=[knowledge_tool.as_function_tool(), fabric_tool.as_function_tool()],
    )


async def run() -> None:
    settings = Settings.from_environment()
    async with create_agent(settings) as agent:
        server = ResponsesHostServer(agent)
        await server.run_async()


def main() -> None:
    asyncio.run(run())
