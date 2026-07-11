from __future__ import annotations

from pathlib import Path

from repo_validation.configuration import (
    EXPECTED_AGENT_NAME,
    EXPECTED_MODEL,
    validate_repository_configuration,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_bootstrap_configuration_is_consistent() -> None:
    assert validate_repository_configuration(REPOSITORY_ROOT) == []


def test_expected_generic_agent_and_model_names() -> None:
    assert EXPECTED_AGENT_NAME == "hotel-servicing-agent"
    assert EXPECTED_MODEL == "gpt-5.4-mini"
