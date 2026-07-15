#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVALUATION_ROOT = ROOT / "evaluation" / "assert"
SOURCE_ROOT = EVALUATION_ROOT / ".runtime" / "source"


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the pinned ASSERT results viewer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5174)
    args = parser.parse_args()

    if not SOURCE_ROOT.exists():
        subprocess.run(
            [
                "python3",
                str(ROOT / "scripts" / "bootstrap_assert.py"),
                "--source-only",
            ],
            check=True,
        )
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("Node.js 18 or later and npm are required for the ASSERT viewer")
    viewer = SOURCE_ROOT / "viewer"
    if not (viewer / "node_modules").exists():
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=viewer, check=True)

    environment = os.environ.copy()
    environment["ARTIFACTS_ROOT"] = str((ROOT / "artifacts" / "results").resolve())
    environment.setdefault("VIEWER_EDIT_MODE", "0")
    os.chdir(viewer)
    os.execve(
        npm,
        [npm, "run", "dev", "--", "--host", args.host, "--port", str(args.port)],
        environment,
    )


if __name__ == "__main__":
    main()
