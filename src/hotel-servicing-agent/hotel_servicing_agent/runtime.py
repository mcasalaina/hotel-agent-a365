from __future__ import annotations

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential

from hotel_servicing_agent.config import Settings


def create_agent(settings: Settings) -> Agent:
    client = FoundryChatClient(
        project_endpoint=settings.project_endpoint,
        model=settings.model_deployment,
        credential=DefaultAzureCredential(),
    )
    return Agent(
        client=client,
        name="hotel-servicing-agent",
        description="Guest-services orchestration for a fictional hotel chain.",
        instructions=settings.instructions,
        default_options={"store": False},
    )


def main() -> None:
    settings = Settings.from_environment()
    server = ResponsesHostServer(create_agent(settings))
    server.run()
