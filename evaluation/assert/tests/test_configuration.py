from __future__ import annotations

import builtins
import importlib
import json
from pathlib import Path

import yaml

from hotel_assert.config_validation import validate_repository

ROOT = Path(__file__).resolve().parents[3]


def test_repository_assert_configuration_is_consistent() -> None:
    assert validate_repository(ROOT) == []


def test_reviewed_suite_mixes_natural_prompts_and_multiturn_scenarios() -> None:
    seed_path = (
        ROOT
        / "evaluation"
        / "assert"
        / "config"
        / "seeds"
        / "hotel-guest-services-conversations.jsonl"
    )
    rows = [json.loads(line) for line in seed_path.read_text().splitlines() if line]

    assert sum(row["type"] == "prompt" for row in rows) == 16
    assert sum(row["type"] == "scenario" for row in rows) == 9
    assert all(row["dimensions"]["expected_behavior"] for row in rows)
    assert all(
        row["dimensions"]["conversation_shape"] != "single_turn"
        for row in rows
        if row["type"] == "scenario"
    )


def test_reviewed_suite_configures_two_turn_tester() -> None:
    config_path = ROOT / "evaluation" / "assert" / "config" / "baseline-quality.yaml"
    config = yaml.safe_load(config_path.read_text())
    inference = config["pipeline"]["inference"]

    assert config["suite"] == "hotel-guest-services-conversations"
    assert inference["max_turns"] == 2
    assert inference["tester"]["model"]["name"] == "azure/gpt-5.4-mini"


def test_reviewed_suite_covers_multilingual_continuity() -> None:
    seed_path = (
        ROOT
        / "evaluation"
        / "assert"
        / "config"
        / "seeds"
        / "hotel-guest-services-conversations.jsonl"
    )
    rows = [json.loads(line) for line in seed_path.read_text().splitlines() if line]
    multilingual = [row for row in rows if row["behavior"] == "language_continuity_broken"]

    assert len(multilingual) == 4
    assert {row["dimensions"]["user_language"] for row in multilingual} == {
        "arabic",
        "english",
        "japanese",
        "spanish",
    }


def test_language_continuity_behavior_is_independently_runnable() -> None:
    behavior_root = ROOT / "evaluation/assert/config/behaviors"
    config = yaml.safe_load((behavior_root / "language-continuity.yaml").read_text())
    dimensions = config["pipeline"]["judge"]["dimensions"]

    assert config["run"] == "language-continuity"
    assert set(dimensions) == {"language_continuity", "general_quality"}
    assert (
        behavior_root.joinpath("specs/hotel-agent-taxonomy.json").read_bytes()
        == ROOT.joinpath("evaluation/assert/config/specs/hotel-agent-taxonomy.json").read_bytes()
    )


def test_reviewed_suite_covers_fixed_temporal_boundary_and_maria_email() -> None:
    seed_path = (
        ROOT
        / "evaluation"
        / "assert"
        / "config"
        / "seeds"
        / "hotel-guest-services-conversations.jsonl"
    )
    rows = [json.loads(line) for line in seed_path.read_text().splitlines() if line]
    temporal = [row for row in rows if row.get("dimensions", {}).get("temporal_boundary")]

    assert len(temporal) == 3
    assert {row["dimensions"]["temporal_boundary"] for row in temporal} == {
        "past_strict",
        "future_strict",
    }
    assert any("Maria Garcia" in row["seed"]["title"] for row in temporal)


def test_reviewed_suite_covers_scottsdale_valet_reliability() -> None:
    seed_path = (
        ROOT
        / "evaluation"
        / "assert"
        / "config"
        / "seeds"
        / "hotel-guest-services-conversations.jsonl"
    )
    rows = [json.loads(line) for line in seed_path.read_text().splitlines() if line]
    scottsdale = [row for row in rows if row["seed"]["title"] == "Scottsdale valet reliability"]

    assert len(scottsdale) == 1
    assert "USD 25 per night" in scottsdale[0]["dimensions"]["expected_behavior"]


def test_reviewed_suite_covers_new_and_reply_cc_preservation() -> None:
    seed_path = (
        ROOT
        / "evaluation"
        / "assert"
        / "config"
        / "seeds"
        / "hotel-guest-services-conversations.jsonl"
    )
    rows = [json.loads(line) for line in seed_path.read_text().splitlines() if line]
    recipient_cases = [row for row in rows if row["behavior"] == "cc_recipient_omitted"]

    assert len(recipient_cases) == 2
    assert {row["dimensions"]["recipient_mode"] for row in recipient_cases} == {
        "new_message_with_cc",
        "reply_with_cc",
    }
    assert all(
        "Marco Casalaina" in row["dimensions"]["expected_behavior"] for row in recipient_cases
    )


def test_reviewed_suite_covers_mail_orchestration_and_readback() -> None:
    seed_path = (
        ROOT
        / "evaluation"
        / "assert"
        / "config"
        / "seeds"
        / "hotel-guest-services-conversations.jsonl"
    )
    rows = [json.loads(line) for line in seed_path.read_text().splitlines() if line]
    orchestration = [row for row in rows if row["behavior"] == "mail_orchestration_incomplete"]

    assert len(orchestration) == 3
    assert any("combined" in row["seed"]["title"].lower() for row in orchestration)
    assert any("recovery" in row["seed"]["title"].lower() for row in orchestration)
    assert any("readback" in row["seed"]["title"].lower() for row in orchestration)


def test_source_validation_does_not_require_telemetry_dependencies(monkeypatch) -> None:
    real_import = builtins.__import__

    def offline_import(name, *args, **kwargs):
        if name in {"hotel_assert.app_insights", "azure.monitor.query"}:
            raise ModuleNotFoundError("Telemetry is unavailable for this offline check")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", offline_import)
    cli = importlib.reload(importlib.import_module("hotel_assert.cli"))
    assert cli.main is not None
    assert cli._command_validate(None) == 0
