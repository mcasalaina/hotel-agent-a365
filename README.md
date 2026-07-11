# Hotel Guest Services Agent

This repository contains the source-controlled foundation for a fictional hotel guest-services demo built on Microsoft Foundry, Microsoft Fabric, Foundry IQ, Work IQ, and Agent 365.

The current implementation includes the deployed Fabric data estate, Foundry IQ knowledge base,
Python Hosted Agent, Agent 365 bot/publication artifacts, and a read-only Work IQ integration.
Cloud-changing commands remain operator-invoked; local setup and validation never deploy implicitly.

## Developer setup

Requirements:

- Python 3.13 or later
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

The Hosted Agent deploys from source with Foundry remote build and exposes the Responses protocol,
plus the stable Agent 365 activity endpoint. The Dockerfile provides the equivalent local/container
path. Phase 3 will add `invocations_ws` to the same agent and compose it over the shared
`orchestration`, `tools`, and `state` packages.

See `PLAN.md` for the approved architecture and `DEPLOYMENT.md` for the controlled deployment handoff.

## Deterministic demo data and source documents

Generate the full deterministic source dataset and the Foundry IQ Markdown corpus:

```bash
.venv/bin/python scripts/generate_hotel_data.py --scale full
.venv/bin/python scripts/validate_hotel_data.py
```

Use `--scale demo` with explicit output paths for quick local checks. Generated CSV,
manifest, and documents are synthetic; data output under `data/generated/` is ignored.
Canonical scenario identifiers are in `data/fixtures/demo_scenarios.json`.

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
