from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    project_endpoint: str
    model_deployment: str
    search_endpoint: str
    knowledge_base_name: str
    fabric_data_agent_mcp_url: str
    agent365_tenant_id: str
    agent365_blueprint_client_id: str
    agent365_instance_client_id: str
    work_iq_servers: tuple[tuple[str, str, str], ...]
    instructions: str

    @classmethod
    def from_environment(cls) -> Settings:
        dotenv_path = os.getenv("DOTENV_PATH")
        load_dotenv(dotenv_path=dotenv_path or None)
        project_endpoint = _required_environment_variable("FOUNDRY_PROJECT_ENDPOINT")
        model_deployment = _required_environment_variable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        search_endpoint = _required_environment_variable("AZURE_SEARCH_ENDPOINT")
        knowledge_base_name = _required_environment_variable("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME")
        fabric_data_agent_mcp_url = _required_environment_variable("FABRIC_DATA_AGENT_MCP_URL")
        work_iq_servers = tuple(
            (
                name,
                _required_environment_variable(f"WORK_IQ_{prefix}_MCP_URL"),
                _required_environment_variable(f"WORK_IQ_{prefix}_MCP_AUDIENCE"),
            )
            for name, prefix in (
                ("work-iq-copilot", "COPILOT"),
                ("work-iq-mail", "MAIL"),
                ("work-iq-teams", "TEAMS"),
            )
        )
        instructions_path = Path(
            os.getenv("AGENT_INSTRUCTIONS_PATH", "../../agent-instructions.md")
        )
        if not instructions_path.is_file():
            raise FileNotFoundError(f"Agent instructions file does not exist: {instructions_path}")
        return cls(
            project_endpoint=project_endpoint,
            model_deployment=model_deployment,
            search_endpoint=search_endpoint,
            knowledge_base_name=knowledge_base_name,
            fabric_data_agent_mcp_url=fabric_data_agent_mcp_url,
            agent365_tenant_id=_required_environment_variable("AGENT365_TENANT_ID"),
            agent365_blueprint_client_id=_required_environment_variable(
                "AGENT365_BLUEPRINT_CLIENT_ID"
            ),
            agent365_instance_client_id=_required_environment_variable(
                "AGENT365_INSTANCE_CLIENT_ID"
            ),
            work_iq_servers=work_iq_servers,
            instructions=instructions_path.read_text(encoding="utf-8"),
        )


def _required_environment_variable(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable is not set: {name}")
    return value
