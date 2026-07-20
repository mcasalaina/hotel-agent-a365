from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    project_endpoint: str
    model_deployment: str
    voice_live_endpoint: str
    voice_live_api_version: str
    voice_live_agent_name: str
    voice_live_agent_version: str | None
    voice_live_project_name: str
    voice_live_voice: str
    voice_live_prefer_locales: tuple[str, ...]
    search_endpoint: str
    knowledge_base_name: str
    fabric_data_agent_mcp_url: str
    fabric_workspace_id: str
    fabric_guest_services_lakehouse_id: str
    fabric_reservation_notebook_id: str
    agent365_tenant_id: str
    agent365_blueprint_client_id: str
    agent365_blueprint_secret_vault_url: str
    agent365_blueprint_secret_name: str
    agent365_instance_client_id: str
    work_iq_servers: tuple[tuple[str, str, str], ...]
    instructions: str

    @classmethod
    def from_environment(cls) -> Settings:
        dotenv_path = os.getenv("DOTENV_PATH")
        load_dotenv(dotenv_path=dotenv_path or None)
        project_endpoint = _required_environment_variable("FOUNDRY_PROJECT_ENDPOINT")
        inferred_voice_endpoint, inferred_project_name = _voice_live_defaults(project_endpoint)
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
            voice_live_endpoint=os.getenv(
                "VOICE_LIVE_ENDPOINT",
                inferred_voice_endpoint,
            ).rstrip("/"),
            voice_live_api_version=os.getenv("VOICE_LIVE_API_VERSION", "2026-04-10"),
            voice_live_agent_name=os.getenv("VOICE_LIVE_AGENT_NAME", "hotel-servicing-agent"),
            voice_live_agent_version=os.getenv("VOICE_LIVE_AGENT_VERSION") or None,
            voice_live_project_name=os.getenv(
                "VOICE_LIVE_PROJECT_NAME",
                inferred_project_name,
            ),
            voice_live_voice=os.getenv(
                "VOICE_LIVE_VOICE",
                "en-US-AvaMultilingualNeural",
            ),
            voice_live_prefer_locales=tuple(
                locale.strip()
                for locale in os.getenv("VOICE_LIVE_PREFER_LOCALES", "").split(",")
                if locale.strip()
            ),
            search_endpoint=search_endpoint,
            knowledge_base_name=knowledge_base_name,
            fabric_data_agent_mcp_url=fabric_data_agent_mcp_url,
            fabric_workspace_id=_required_environment_variable("FABRIC_WORKSPACE_ID"),
            fabric_guest_services_lakehouse_id=_required_environment_variable(
                "FABRIC_GUEST_SERVICES_LAKEHOUSE_ID"
            ),
            fabric_reservation_notebook_id=_required_environment_variable(
                "FABRIC_RESERVATION_NOTEBOOK_ID"
            ),
            agent365_tenant_id=_required_environment_variable("AGENT365_TENANT_ID"),
            agent365_blueprint_client_id=_required_environment_variable(
                "AGENT365_BLUEPRINT_CLIENT_ID"
            ),
            agent365_blueprint_secret_vault_url=_required_environment_variable(
                "AGENT365_BLUEPRINT_SECRET_VAULT_URL"
            ),
            agent365_blueprint_secret_name=_required_environment_variable(
                "AGENT365_BLUEPRINT_SECRET_NAME"
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


def _voice_live_defaults(project_endpoint: str) -> tuple[str, str]:
    marker = "/api/projects/"
    if marker not in project_endpoint:
        raise RuntimeError(
            "FOUNDRY_PROJECT_ENDPOINT must contain '/api/projects/' so Voice Live can "
            "derive the Foundry resource endpoint and project name"
        )
    resource_endpoint, project_name = project_endpoint.rstrip("/").split(marker, maxsplit=1)
    if not resource_endpoint or not project_name or "/" in project_name:
        raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT has an invalid Foundry project path")
    return resource_endpoint, project_name
