from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import pytest
from agent_framework import Message
from agent_framework.foundry import FoundryChatClient
from azure.core.credentials import AccessToken
from hotel_servicing_agent.config import Settings
from hotel_servicing_agent.language import LANGUAGE_RESPONSE_GUIDANCE
from hotel_servicing_agent.runtime import _instructions_with_current_utc_date, create_agent


def test_settings_load_required_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    instructions = tmp_path / "instructions.md"
    instructions.write_text("Test instructions", encoding="utf-8")
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://example.test/api/projects/hotel",
    )
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://search.example.test")
    monkeypatch.setenv("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME", "hotel-foundryiq")
    monkeypatch.setenv(
        "FABRIC_DATA_AGENT_MCP_URL",
        "https://api.fabric.microsoft.com/v1/mcp/workspaces/workspace/dataagents/agent/agent",
    )
    monkeypatch.setenv("FABRIC_WORKSPACE_ID", "workspace-id")
    monkeypatch.setenv("FABRIC_GUEST_SERVICES_LAKEHOUSE_ID", "lakehouse-id")
    monkeypatch.setenv("FABRIC_RESERVATION_NOTEBOOK_ID", "notebook-id")
    monkeypatch.setenv("AGENT365_TENANT_ID", "tenant-id")
    monkeypatch.setenv("AGENT365_BLUEPRINT_CLIENT_ID", "blueprint-id")
    monkeypatch.setenv(
        "AGENT365_BLUEPRINT_SECRET_VAULT_URL",
        "https://vault.example.test",
    )
    monkeypatch.setenv("AGENT365_BLUEPRINT_SECRET_NAME", "blueprint-secret")
    monkeypatch.setenv("AGENT365_INSTANCE_CLIENT_ID", "instance-id")
    for prefix in ("COPILOT", "MAIL", "TEAMS"):
        monkeypatch.setenv(
            f"WORK_IQ_{prefix}_MCP_URL",
            f"https://agent365.example.test/{prefix.lower()}",
        )
        monkeypatch.setenv(f"WORK_IQ_{prefix}_MCP_AUDIENCE", f"{prefix.lower()}-audience")
    monkeypatch.setenv("AGENT_INSTRUCTIONS_PATH", str(instructions))

    settings = Settings.from_environment()

    assert settings.project_endpoint == "https://example.test/api/projects/hotel"
    assert settings.model_deployment == "gpt-5.4-mini"
    assert settings.voice_live_endpoint == "https://example.test"
    assert settings.voice_live_project_name == "hotel"
    assert settings.voice_live_voice == "en-US-AvaMultilingualNeural"
    assert settings.search_endpoint == "https://search.example.test"
    assert settings.knowledge_base_name == "hotel-foundryiq"
    assert settings.fabric_data_agent_mcp_url.endswith("/dataagents/agent/agent")
    assert settings.fabric_workspace_id == "workspace-id"
    assert settings.fabric_guest_services_lakehouse_id == "lakehouse-id"
    assert settings.fabric_reservation_notebook_id == "notebook-id"
    assert settings.agent365_blueprint_client_id == "blueprint-id"
    assert settings.agent365_blueprint_secret_vault_url == "https://vault.example.test"
    assert settings.agent365_blueprint_secret_name == "blueprint-secret"
    assert settings.work_iq_servers[1] == (
        "work-iq-mail",
        "https://agent365.example.test/mail",
        "mail-audience",
    )
    assert settings.instructions == "Test instructions"


def test_settings_fail_when_required_value_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")

    with pytest.raises(RuntimeError, match="FOUNDRY_PROJECT_ENDPOINT"):
        Settings.from_environment()


def test_runtime_instructions_include_authoritative_utc_date() -> None:
    instructions = _instructions_with_current_utc_date("Base instructions", date(2026, 7, 12))

    assert "Today's UTC date is 2026-07-12" in instructions
    assert "Past reservations have check_in before 2026-07-12" in instructions
    assert "Future or upcoming reservations have check_in after 2026-07-12" in instructions
    assert "A check_in on 2026-07-12 is neither past nor future" in instructions
    assert "2026-07-13 through 2026-07-19, inclusive" in instructions
    assert "Never infer the current date from prior knowledge" in instructions
    assert "Final response requirement: use the user's established conversation language" in (
        instructions
    )
    assert LANGUAGE_RESPONSE_GUIDANCE in instructions
    assert "An English utterance requires an English response" in instructions
    assert "do not infer a visitor's preferred language" in instructions


def test_instructions_distinguish_knowledge_lookup_from_current_record_resolution() -> None:
    instructions = Path("agent-instructions.md").read_text()

    assert instructions == Path("src/hotel-servicing-agent/agent-instructions.md").read_text()
    assert "Never guess an identifier" in instructions
    assert "Do not query operations data merely to resolve a named hotel" in instructions
    assert "Only for a request that combines a current business record" in instructions
    assert "name the actual returned source title and its effective date" in instructions
    assert "Confirmed from Fabric: HTL-###" in instructions
    assert "do not invent that" in instructions
    assert "Say that the reservation could not be verified" in instructions
    assert "An English utterance requires an English response" in instructions
    assert "do not infer a\n  visitor's preferred language" in instructions
    assert "title verbatim as a proper name" in instructions
    assert "Quoting a policy sentence is not a substitute for naming its" in instructions


def test_runtime_serializes_dependent_tool_calls_in_the_actual_model_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoNetworkCredential:
        def get_token(self, *scopes: str, **kwargs: object) -> AccessToken:
            raise AssertionError("Preparing a model request must not acquire a token")

    monkeypatch.setattr(
        "hotel_servicing_agent.runtime.select_azure_credential",
        NoNetworkCredential,
    )
    settings = Settings(
        project_endpoint="https://example.test/api/projects/hotel",
        model_deployment="gpt-5.4-mini",
        voice_live_endpoint="https://example.test",
        voice_live_api_version="2026-04-10",
        voice_live_agent_name="hotel-servicing-agent",
        voice_live_agent_version=None,
        voice_live_project_name="hotel",
        voice_live_voice="en-US-AvaMultilingualNeural",
        voice_live_prefer_locales=(),
        search_endpoint="https://search.example.test",
        knowledge_base_name="hotel-foundryiq",
        fabric_data_agent_mcp_url="https://fabric.example.test/mcp",
        fabric_workspace_id="workspace-id",
        fabric_guest_services_lakehouse_id="lakehouse-id",
        fabric_reservation_notebook_id="notebook-id",
        agent365_tenant_id="tenant-id",
        agent365_blueprint_client_id="blueprint-id",
        agent365_blueprint_secret_vault_url="https://vault.example.test",
        agent365_blueprint_secret_name="blueprint-secret",
        agent365_instance_client_id="instance-id",
        work_iq_servers=(("work-iq-mail", "https://agent365.example.test/mail", "mail-audience"),),
        instructions="Resolve the reservation before looking up its hotel's valet price.",
    )

    async def prepare() -> dict[str, object]:
        async with create_agent(settings) as agent:
            assert isinstance(agent.client, FoundryChatClient)
            return await agent.client._prepare_options(
                [
                    Message(
                        role="user",
                        contents=["Find Maria's reservation and its hotel's valet price."],
                    )
                ],
                agent.default_options,
            )

    options = asyncio.run(prepare())

    assert options["parallel_tool_calls"] is False
    assert "allow_multiple_tool_calls" not in options
    assert options["store"] is False
    tool_names = {tool["name"] for tool in options["tools"]}
    assert {"query_hotel_operations_data", "search_hotel_knowledge"} <= tool_names
