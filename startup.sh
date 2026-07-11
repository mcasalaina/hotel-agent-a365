#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="${AGENT_ROOT:-$ROOT/src/hotel-servicing-agent}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$AGENT_ROOT"
exec "$PYTHON_BIN" main.py
