#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from repo_validation.naming import default_technical_files, find_naming_violations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reject customer branding in technical configuration names."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Optional technical files to scan instead of the repository defaults.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root used for default discovery and relative diagnostics.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    paths = [path.resolve() for path in args.paths] or default_technical_files(root)
    violations = find_naming_violations(paths)
    if violations:
        for violation in violations:
            print(violation.format(root))
        return 1
    print(f"Technical naming policy passed for {len(paths)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
