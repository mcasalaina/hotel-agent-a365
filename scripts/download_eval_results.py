#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Foundry evaluation row results.")
    parser.add_argument("--endpoint", required=True, help="Foundry project endpoint")
    parser.add_argument("--eval-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_client = AIProjectClient(
        endpoint=args.endpoint,
        credential=DefaultAzureCredential(),
    )
    client = project_client.get_openai_client()
    items = [
        item.model_dump()
        for item in client.evals.runs.output_items.list(
            run_id=args.run_id,
            eval_id=args.eval_id,
        )
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(items, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    failed = sum(
        any(result.get("passed") is False for result in item.get("results", [])) for item in items
    )
    print(f"Downloaded {len(items)} rows, including {failed} failed rows.")


if __name__ == "__main__":
    main()
