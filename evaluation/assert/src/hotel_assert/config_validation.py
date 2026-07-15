from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from hotel_assert.gates import load_policy


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
    for config_name in ("smoke.yaml", "regression.yaml", "adversarial.yaml"):
        path = evaluation_root / "config" / config_name
        try:
            config = _load_yaml(path)
            if config.get("pipeline", {}).get("inference", {}).get("concurrency") != 1:
                errors.append(f"{config_name}: inference.concurrency must be 1")
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

    seed_path = evaluation_root / "config" / "seeds" / "hotel-servicing-smoke.jsonl"
    try:
        rows = [
            json.loads(line)
            for line in seed_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        ids = {row["test_case_id"] for row in rows}
        if len(rows) != 9 or len(ids) != 9:
            errors.append("Smoke seed must contain exactly nine unique cases")
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        errors.append(f"Smoke seed: {exc}")
    return errors
