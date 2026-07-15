#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
EVALUATION_ROOT = ROOT / "evaluation" / "assert"
RUNTIME_ROOT = EVALUATION_ROOT / ".runtime"
SOURCE_ROOT = RUNTIME_ROOT / "source"
DIST_ROOT = RUNTIME_ROOT / "dist"
LOCK_PATH = EVALUATION_ROOT / "assert-source.lock.json"


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    environment: dict[str, str] | None = None,
) -> None:
    subprocess.run(command, cwd=cwd, check=True, env=environment)


def _load_lock() -> dict[str, Any]:
    value = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {LOCK_PATH}")
    return cast(dict[str, Any], value)


def ensure_source(lock: dict[str, Any]) -> None:
    if not SOURCE_ROOT.exists():
        RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--filter=blob:none", lock["repository"], str(SOURCE_ROOT)])
    _run(["git", "fetch", "--depth", "1", "origin", lock["commit"]], cwd=SOURCE_ROOT)
    _run(["git", "checkout", "--detach", lock["commit"]], cwd=SOURCE_ROOT)
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=SOURCE_ROOT,
        text=True,
    ).strip()
    if actual != lock["commit"]:
        raise RuntimeError(f"ASSERT source pin mismatch: expected {lock['commit']}, got {actual}")


def build_wheel(lock: dict[str, Any]) -> Path:
    build = lock["build"]
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            f"setuptools=={build['setuptools']}",
            f"wheel=={build['wheel']}",
        ]
    )
    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    for old_wheel in DIST_ROOT.glob("assert_ai-*.whl"):
        old_wheel.unlink()
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = build["source_date_epoch"]
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-build-isolation",
            "--no-deps",
            "--wheel-dir",
            str(DIST_ROOT),
            str(SOURCE_ROOT),
        ],
        environment=environment,
    )
    wheel = DIST_ROOT / str(lock["wheel"])
    if not wheel.is_file():
        raise RuntimeError(f"Expected ASSERT wheel was not built: {wheel}")
    actual = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if actual != lock["sha256"]:
        wheel.unlink()
        raise RuntimeError(f"ASSERT wheel hash mismatch: expected {lock['sha256']}, got {actual}")
    return wheel


def install(wheel: Path) -> None:
    constraints = EVALUATION_ROOT / "constraints.txt"
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-c",
            str(constraints),
            str(wheel),
            "-e",
            f"{EVALUATION_ROOT}[dev]",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the reviewed ASSERT source pin")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    if args.clean and RUNTIME_ROOT.exists():
        shutil.rmtree(RUNTIME_ROOT)
    lock = _load_lock()
    ensure_source(lock)
    if args.source_only:
        return
    wheel = build_wheel(lock)
    if args.install:
        install(wheel)


if __name__ == "__main__":
    main()
