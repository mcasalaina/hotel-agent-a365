from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from hotel_servicing_agent.config import Settings
from hotel_servicing_agent.runtime import _instructions_with_current_utc_date


def test_settings_load_required_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    instructions = tmp_path / "instructions.md"
    instructions.write_text("Test instructions", encoding="utf-8")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.test/projects/hotel")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://search.example.test")
    monkeypatch.setenv("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME", "hotel-foundryiq")
    monkeypatch.setenv(
        "FABRIC_DATA_AGENT_MCP_URL",
        "https://api.fabric.microsoft.com/v1/mcp/workspaces/workspace/dataagents/agent/agent",
    )
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

    assert settings.project_endpoint == "https://example.test/projects/hotel"
    assert settings.model_deployment == "gpt-5.4-mini"
    assert settings.search_endpoint == "https://search.example.test"
    assert settings.knowledge_base_name == "hotel-foundryiq"
    assert settings.fabric_data_agent_mcp_url.endswith("/dataagents/agent/agent")
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
    assert "2026-07-12 through 2026-07-18, inclusive" in instructions
    assert "Never infer the current date from model training data" in instructions
