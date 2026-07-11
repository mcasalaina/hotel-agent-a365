from __future__ import annotations

from pathlib import Path

import pytest
from hotel_servicing_agent.config import Settings


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
    monkeypatch.setenv("AGENT_INSTRUCTIONS_PATH", str(instructions))

    settings = Settings.from_environment()

    assert settings.project_endpoint == "https://example.test/projects/hotel"
    assert settings.model_deployment == "gpt-5.4-mini"
    assert settings.search_endpoint == "https://search.example.test"
    assert settings.knowledge_base_name == "hotel-foundryiq"
    assert settings.fabric_data_agent_mcp_url.endswith("/dataagents/agent/agent")
    assert settings.instructions == "Test instructions"


def test_settings_fail_when_required_value_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")

    with pytest.raises(RuntimeError, match="FOUNDRY_PROJECT_ENDPOINT"):
        Settings.from_environment()
