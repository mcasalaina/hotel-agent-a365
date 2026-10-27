from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from hotel_assert.gates import load_policy

EXPECTED_SUITES = {
    "baseline-quality.yaml": "hotel-guest-services-conversations",
    "regression.yaml": "hotel-guest-services-coverage",
    "adversarial.yaml": "hotel-guest-services-safety",
}
SMOKE_CASE_COUNT = 25
SMOKE_PROMPT_COUNT = 16
SMOKE_SCENARIO_COUNT = 9
BANNED_USER_PHRASES = (
    "approved source",
    "documented",
    "for property htl-",
)


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping: {path}")
    return value


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    evaluation_root = root / "evaluation" / "assert"
    policy_path = evaluation_root / "policies" / "rubric-policy.json"
    try:
        policies, threshold = load_policy(policy_path)
        if threshold != 0.68:
            errors.append("Rubric pass threshold must remain 0.68")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        policies = []

    expected_dimensions = {policy.name for policy in policies}
    for config_name, expected_suite in EXPECTED_SUITES.items():
        path = evaluation_root / "config" / config_name
        try:
            config = _load_yaml(path)
            if config.get("suite") != expected_suite:
                errors.append(f"{config_name}: suite must be {expected_suite}")
            inference = config.get("pipeline", {}).get("inference", {})
            if inference.get("concurrency") != 1:
                errors.append(f"{config_name}: inference.concurrency must be 1")
            tester_model = inference.get("tester", {}).get("model", {}).get("name")
            if not tester_model:
                errors.append(f"{config_name}: inference.tester.model.name is required")
            dimensions = set(config["pipeline"]["judge"]["dimensions"])
            if dimensions != expected_dimensions:
                errors.append(f"{config_name}: judge dimensions do not match rubric policy")
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
            errors.append(f"{config_name}: {exc}")

    taxonomy_path = evaluation_root / "config" / "specs" / "hotel-agent-taxonomy.json"
    try:
        taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
        categories = taxonomy["behavior_categories"]
        if not categories or any(
            not {"name", "definition", "examples", "permissible"} <= set(category)
            for category in categories
        ):
            errors.append("Taxonomy categories are incomplete")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"Taxonomy: {exc}")

    seed_path = evaluation_root / "config" / "seeds" / "hotel-guest-services-conversations.jsonl"
    try:
        rows = [
            json.loads(line)
            for line in seed_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        ids = {row["test_case_id"] for row in rows}
        if len(rows) != SMOKE_CASE_COUNT or len(ids) != SMOKE_CASE_COUNT:
            errors.append(f"Conversation seed must contain exactly {SMOKE_CASE_COUNT} unique cases")
        prompt_count = sum(row.get("type") == "prompt" for row in rows)
        scenario_count = sum(row.get("type") == "scenario" for row in rows)
        if prompt_count != SMOKE_PROMPT_COUNT or scenario_count != SMOKE_SCENARIO_COUNT:
            errors.append(
                "Conversation seed must contain exactly "
                f"{SMOKE_PROMPT_COUNT} prompts and {SMOKE_SCENARIO_COUNT} scenarios"
            )
        for row in rows:
            seed = row.get("seed")
            if not isinstance(seed, dict) or not seed.get("title") or not seed.get("description"):
                errors.append(f"{row.get('test_case_id', 'unknown')}: incomplete seed")
                continue
            if not row.get("behavior"):
                errors.append(f"{row.get('test_case_id', 'unknown')}: behavior is required")
            dimensions = row.get("dimensions")
            if not isinstance(dimensions, dict) or not dimensions.get("expected_behavior"):
                errors.append(
                    f"{row.get('test_case_id', 'unknown')}: expected_behavior is required"
                )
            description = str(seed["description"]).lower()
            for phrase in BANNED_USER_PHRASES:
                if phrase in description:
                    errors.append(
                        f"{row.get('test_case_id', 'unknown')}: user text contains {phrase!r}"
                    )
    except (OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        errors.append(f"Conversation seed: {exc}")
    return errors
