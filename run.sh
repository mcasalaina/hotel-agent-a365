#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AGENT_ROOT="${AGENT_ROOT:-$ROOT/src/hotel-servicing-agent}"
export AGENT_INSTRUCTIONS_PATH="${AGENT_INSTRUCTIONS_PATH:-$ROOT/agent-instructions.md}"
export DOTENV_PATH="${DOTENV_PATH:-$ROOT/.env}"

exec "$ROOT/startup.sh"
