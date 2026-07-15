#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIDECAR_ROOT = Path("/opt/entra-auth-sidecar")
SIDECAR_DLL = SIDECAR_ROOT / "Microsoft.Identity.Web.Sidecar.dll"
DOTNET = Path("/usr/share/dotnet/dotnet")


def main() -> None:
    if not SIDECAR_DLL.is_file():
        raise RuntimeError(f"Entra Auth SDK sidecar was not found: {SIDECAR_DLL}")
    if not DOTNET.is_file():
        raise RuntimeError(f".NET runtime was not found: {DOTNET}")

    sidecar_environment = os.environ.copy()
    sidecar = subprocess.Popen(
        [str(DOTNET), str(SIDECAR_DLL)],
        cwd=SIDECAR_ROOT,
        env=sidecar_environment,
    )
    runner_environment = os.environ.copy()
    for name in list(runner_environment):
        if name.startswith("AzureAd__ClientCredentials__"):
            del runner_environment[name]
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_assert_evaluation.py"),
                *sys.argv[1:],
            ],
            cwd=ROOT,
            env=runner_environment,
            check=False,
        )
    finally:
        sidecar.terminate()
        try:
            sidecar.wait(timeout=15)
        except subprocess.TimeoutExpired:
            sidecar.kill()
            sidecar.wait(timeout=5)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
