from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from agent_framework.foundry import FoundryChatClient
from hotel_servicing_agent import runtime
from hotel_servicing_agent.config import Settings
from hotel_servicing_agent.runtime import _instructions_with_current_utc_date
from openai import AsyncOpenAI


@pytest.fixture
def settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Settings:
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

    return Settings.from_environment()


def test_settings_load_required_values(settings: Settings) -> None:
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


def test_runtime_sends_sequential_stateless_responses_request(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": settings.model_deployment,
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": "Test answer", "annotations": []}
                        ],
                    }
                ],
            },
        )

    async def invoke() -> None:
        async with (
            httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client,
            AsyncOpenAI(
                api_key="offline-test", base_url="https://example.test", http_client=http_client
            ) as openai_client,
        ):

            class TestProject:
                def get_openai_client(self, **kwargs: Any) -> AsyncOpenAI:
                    return openai_client

            client = FoundryChatClient(
                project_client=TestProject(),  # type: ignore[arg-type]
                model=settings.model_deployment,
            )
            monkeypatch.setattr(runtime, "FoundryChatClient", lambda **kwargs: client)
            monkeypatch.setattr(runtime, "select_azure_credential", object)
            agent = runtime.create_agent(settings)
            response = await agent.run("Hello")
            assert response.text == "Test answer"

    asyncio.run(invoke())

    assert len(requests) == 1
    assert requests[0]["store"] is False
    assert requests[0]["parallel_tool_calls"] is False
    names = [tool["name"] for tool in requests[0]["tools"]]
    assert len(names) == len(set(names))
    assert "search_hotel_knowledge" in names
    assert "query_hotel_operations_data" in names


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
    assert "2026-07-12 through 2026-07-18, inclusive" in instructions
    assert "Never infer the current date from model training data" in instructions
