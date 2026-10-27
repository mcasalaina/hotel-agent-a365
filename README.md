# Hotel Guest Services Agent

This repository contains the Hotel Guest Services solution built on Microsoft Foundry,
Microsoft Fabric, Foundry IQ, Work IQ, and Agent 365.

The current implementation includes the deployed Fabric data estate, Foundry IQ knowledge base,
Python Hosted Agent, Agent 365 bot/publication artifacts, a Work IQ integration, and an
authenticated Voice Live web frontend.
Cloud-changing commands remain operator-invoked; local setup and validation never deploy implicitly.

The current target runbook is the
[tenant guide on main](https://github.com/mcasalaina/hotel-agent-a365/blob/main/docs/tenant-migration-guide.md).
It records required permissions, verified deployments and the remaining acceptance
gates. Guide publication is not implementation promotion or full solution acceptance.

## Developer setup

Requirements:

- Python 3.13 or later
- Node.js 22 or later
- Docker for optional local container builds
- Azure Developer CLI 1.27 or later with the `azure.ai.agents` extension

```bash
make setup
make check
```

Copy `.env.template` to `.env` for local Hosted Agent execution. Never commit `.env`, azd environment state, generated Agent 365 configuration, tokens, or deployment packages.

Run the agent after installing dependencies:

```bash
make run
```

Build the root container parity image:

```bash
make docker-build
```

The Hosted Agent deploys from source with Foundry remote build and exposes both Responses 2.0 and
`invocations_ws` 1.0. The Voice Live adapter uses the same hosted hotel agent and its existing
orchestration and tools.

## Voice Live web frontend

The React frontend and Python proxy are under `web/`. The proxy validates the signed-in user's Entra
token, exchanges it for a short-lived opaque browser session, obtains its own Foundry service token,
and relays the duplex WebSocket without exposing service credentials to the browser.

Voice calls use raw PCM16 mono audio at 24 kHz. Voice Live uses
`en-US-AvaMultilingualNeural`, multilingual semantic VAD, automatic speech-language handling,
interim responses for tool and latency delays, and a proactive welcome. The UI also accepts
uncompressed mono or stereo 16-bit PCM WAV prompts and resamples them to the wire format for
repeatable testing.

Run the backend and Vite development server in separate terminals after configuring
`web/backend/.env` and `web/frontend/.env.local`:

```bash
set -a; source web/backend/.env; set +a
make run-web
```

```bash
npm --prefix web/frontend run dev
```

For a direct hosted-agent smoke test, use a mono, 16-bit, 24 kHz PCM WAV file:

```bash
.venv/bin/python scripts/run_voice_smoke.py prompt.wav \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
```

Build the same-origin frontend/proxy image with `make web-docker-build` after exporting the public
`VITE_ENTRA_*` build values.

See `PLAN.md` for the approved architecture, `DEPLOYMENT.md` for the controlled deployment handoff,
`docs/foundry-evaluator-rubrics.md` for evaluator creation and portal verification, and
`docs/assert-evaluation.md` for agent-user ASSERT testing, trace gates, and the local results viewer.

## ASSERT evaluation

ASSERT runs in an isolated Python 3.13 environment and invokes the deployed agent only with a
validated Lyrenza Hotel Guest Services Agent ID user token from a loopback-only Entra Auth SDK sidecar.
The reviewed **Hotel Guest Services Conversations** suite combines natural fixed requests with
adaptive two-turn ASSERT scenarios.

```bash
python3.13 -m venv evaluation/assert/.venv
evaluation/assert/.venv/bin/python scripts/bootstrap_assert.py --install
evaluation/assert/.venv/bin/python scripts/run_assert_evaluation.py validate
```

Live runs, controlled Azure execution, baseline promotion, artifact restrictions, and viewer startup
are documented in `evaluation/assert/README.md`.

## Deterministic hotel data and source documents

Generate the full deterministic source dataset and the Foundry IQ Markdown corpus:

```bash
.venv/bin/python scripts/generate_hotel_data.py --scale full
.venv/bin/python scripts/validate_hotel_data.py
```

Use `--scale demo` with explicit output paths for quick local checks. Generated CSV,
manifest, and document output under `data/generated/` is ignored.
Canonical scenario identifiers are in `data/fixtures/business_scenarios.json`.

## Foundry IQ local setup

After signing in locally with an Entra identity that has the required roles, validate the corpus
without contacting Azure:

```bash
.venv/bin/python scripts/setup_foundry_iq.py --dry-run
```

To create or refresh the approved knowledge base, configure `AZURE_SEARCH_ENDPOINT`,
`AZURE_OPENAI_ENDPOINT`, and the optional `AZURE_SEARCH_ADMIN_KEY` in your local shell or `.env`.
Without an admin key, setup uses `DefaultAzureCredential`. If Search-to-model managed identity
access is unavailable, `AZURE_OPENAI_API_KEY` is an explicit encrypted service-side fallback and
must never be committed. Then run:

```bash
.venv/bin/python scripts/setup_foundry_iq.py
.venv/bin/python scripts/verify_deployment.py --property-id HTL-001 --as-of 2026-04-10
```

`FOUNDRY_IQ_BLOB_CONTAINER` plus `AZURE_STORAGE_ACCOUNT_URL` optionally archives the source
Markdown to Blob Storage; it is not required for Search indexing. See `DEPLOYMENT.md` for RBAC
and controlled handoff requirements.
