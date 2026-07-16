#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
EVALUATION_ROOT = ROOT / "evaluation" / "assert"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return cast(dict[str, Any], value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote a verified ASSERT baseline")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--generation-model", required=True)
    parser.add_argument("--hosted-agent-version", required=True)
    parser.add_argument("--bridge-revision", required=True)
    parser.add_argument("--agent-user-object-id", required=True)
    parser.add_argument("--agent-identity-id", required=True)
    parser.add_argument("--repeatability-tolerance", type=float, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=EVALUATION_ROOT / "baselines" / "baseline-manifest.json",
    )
    args = parser.parse_args()

    gate = _load(args.run_root / "gate-result.json")
    if gate.get("passed") is not True:
        raise RuntimeError("Only a run with a passing gate result can be promoted")
    if not 0 <= args.repeatability_tolerance <= 1:
        raise ValueError("repeatability tolerance must be between 0 and 1")

    manifest = _load(args.manifest)
    manifest["status"] = "promoted"
    manifest["promoted_at"] = datetime.now(UTC).isoformat()
    manifest["calibration"]["judge_repeatability_tolerance"] = args.repeatability_tolerance
    manifest["deployment"].update(
        {
            "hosted_agent_version": args.hosted_agent_version,
            "bridge_revision": args.bridge_revision,
            "agent_user_object_id": args.agent_user_object_id,
            "agent_identity_id": args.agent_identity_id,
        }
    )
    manifest["hashes"].update(
        {
            "repository_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                text=True,
            ).strip(),
            "taxonomy_sha256": _sha256(
                EVALUATION_ROOT / "config" / "specs" / "hotel-agent-taxonomy.json"
            ),
            "test_set_sha256": _sha256(
                EVALUATION_ROOT / "config" / "seeds" / "hotel-guest-services-conversations.jsonl"
            ),
            "configuration_sha256": _sha256(args.config),
            "judge_prompt_sha256": _sha256(args.config),
        }
    )
    manifest["models"].update(
        {
            "judge_deployment": args.judge_model,
            "generation_deployment": args.generation_model,
        }
    )
    manifest["run"].update(
        {
            "run_id": args.run_root.name,
            "artifact_location": str(args.run_root),
        }
    )
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
