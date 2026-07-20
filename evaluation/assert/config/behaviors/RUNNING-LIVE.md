# Running a behavior config against the live agent

The `hotel_assert:chat` target every config in this directory uses calls the **live deployed Hotel
Guest Services Hosted Agent** through a real Microsoft Entra Agent ID **user** token — it never falls
back to a developer token, API key, managed identity, or `x-ms-user-identity` header. So a live run
needs the same identity plumbing as the parent suites, documented canonically in
[`../../README.md`](../../README.md). This file is the turnkey checklist for running **one behavior
config** end to end.

## Prerequisites (all required)

1. **Python 3.13 + pinned ASSERT.** The bootstrap builds and installs the reviewed ASSERT commit
   (verified against `evaluation/assert/assert-source.lock.json`):
   ```powershell
   py -3.13 -m venv evaluation\assert\.venv
   evaluation\assert\.venv\Scripts\python.exe scripts\bootstrap_assert.py --install
   evaluation\assert\.venv\Scripts\python.exe scripts\run_assert_evaluation.py validate
   ```
2. **Entra Auth SDK sidecar** running in the same trust boundary, exposed **only on loopback**, with
   its `Foundry` downstream API configured for scope `https://ai.azure.com/.default`.
3. **Live-identity environment variables** (names only — never commit real values; see the agent's
   committed `src/hotel-servicing-agent/.env.template` for the non-secret endpoint shape):
   ```text
   ASSERT_TENANT_ID
   ASSERT_FOUNDRY_AUDIENCE
   ASSERT_AGENT_USER_ID
   ASSERT_AGENT_IDENTITY_ID
   ASSERT_PARENT_BLUEPRINT_ID
   ASSERT_SIDECAR_URL=http://127.0.0.1:5000
   ASSERT_SIDECAR_SERVICE=Foundry
   AZURE_AI_FOUNDRY_ENDPOINT
   FOUNDRY_AGENT_NAME=hotel-servicing-agent
   FOUNDRY_MODEL_NAME
   ```
4. **A valid agent-user token** with a valid Microsoft signature and lifetime, `idtyp=user`, the
   configured user `oid`, the configured agent `azp`/`appid`, agent-user subject facet `13`,
   agent-identity actor facet `11`, and the expected tenant, audience, and parent blueprint. Any
   mismatch fails the run before a Hosted Agent request is sent.
5. **`APPLICATIONINSIGHTS_WORKSPACE_ID`** — required by `live` to import and judge the correlated
   Application Insights OTLP traces.

## Run one behavior (smallest signal)

Pick any config and run it through the `live` harness (preflight + correlated trace import). Reduce
`test_set.prompt.sample_size` / `scenario.sample_size` in the chosen YAML to `1`–`2` first for a
cheap smoke, then scale up:

```powershell
evaluation\assert\.venv\Scripts\python.exe scripts\run_assert_evaluation.py live `
  --config evaluation\assert\config\behaviors\read-only-boundaries.yaml `
  --suite hotel-guest-services-behaviors `
  --workspace-id $env:APPLICATIONINSIGHTS_WORKSPACE_ID
```

`--suite` overrides the config's `suite:` label and sets the results path
(`artifacts/results/<suite>/<run-id>/`); `--run-id` defaults to a UTC timestamp. Omit
`--require-all-cases` for these generated configs (it is meant for the fixed 12-case reviewed
`smoke.yaml`). For a plain run without trace correlation, use the `run` subcommand with the same
`--config`/`--suite`.

## Blockers observed in the current workspace (2026-05)

A live run was **not** attempted because none of the following were available and none can be
assembled without provisioning A365 infrastructure or fabricating secrets:

| Prerequisite | State here |
|---|---|
| All 10 live-identity env vars | **unset** |
| Entra Auth SDK sidecar on loopback | not running |
| Valid agent-user token (facets 13/11, etc.) | not available |
| `APPLICATIONINSIGHTS_WORKSPACE_ID` | unset |
| Python 3.13 for `bootstrap_assert.py --install` | not installed (only 3.12) |

`az` CLI is present and logged in, but that alone does not mint the agent-**user** token the target
requires; the sidecar + provisioned agent-user identity in the Foundry/A365 project are the hard
dependencies. Configs were instead schema-validated offline through the pinned ASSERT parser (see
[`README.md`](README.md)).

## Safety notes

- **Never** commit `.env`, tokens, or any real identity value. `.env` is gitignored; keep it that way.
- Generated test sets land in gitignored `artifacts/generated/`; results and raw transcripts land in
  gitignored `artifacts/results/`. Do not commit them.
- The ASSERT results viewer (`scripts/run_assert_ui.py`) binds `http://127.0.0.1:5174`. If another
  ASSERT run or viewer is already using `:5174` (or Phoenix on `:6006`), do not start a second one —
  point the viewer at a different port or wait for the other run to finish.
