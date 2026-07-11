#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from repo_validation.configuration import validate_repository_configuration


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the bootstrap Hosted Agent configuration."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to validate.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    problems = validate_repository_configuration(args.root.resolve())
    if problems:
        for problem in problems:
            print(f"{problem.field}: {problem.message}")
        return 1
    print("Hosted Agent configuration is internally consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
