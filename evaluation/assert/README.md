# Hotel Guest Services ASSERT evaluation

This isolated Python project evaluates the deployed Hotel Guest Services Hosted Agent through a
real Microsoft Entra Agent ID user token. It never falls back to a developer token, API key,
managed identity, or `x-ms-user-identity` header as the target identity.

## Install

Use Python 3.13. The bootstrap script clones the reviewed ASSERT commit, builds it with fixed build
inputs, verifies the wheel SHA-256 in `assert-source.lock.json`, and installs the wheel plus this
project into the active environment.

```bash
python3.13 -m venv evaluation/assert/.venv
evaluation/assert/.venv/bin/python scripts/bootstrap_assert.py --install
evaluation/assert/.venv/bin/python scripts/run_assert_evaluation.py validate
```

ASSERT remains isolated from the Hosted Agent and Agent 365 bridge dependencies. Do not replace the
source lock with an unpinned Git dependency or the published wheel.

## Live identity configuration

Run the Entra Auth SDK sidecar in the same pod or host trust boundary and expose it only on loopback.
Configure its `Foundry` downstream API with scope `https://ai.azure.com/.default`. The target requires:

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

The token must have a valid Microsoft signature and lifetime, `idtyp=user`, the configured user
`oid`, the configured agent `azp` or `appid`, agent-user subject facet `13`, agent-identity actor
facet `11`, the expected tenant and audience, and the configured parent blueprint. Any mismatch
fails the run before a Hosted Agent request is sent.

## Run

The deterministic smoke suite has nine reviewed cases:

```bash
evaluation/assert/.venv/bin/python scripts/run_assert_evaluation.py live \
  --config evaluation/assert/config/smoke.yaml \
  --suite hotel-servicing-smoke \
  --workspace-id "$APPLICATIONINSIGHTS_WORKSPACE_ID" \
  --require-all-cases 9
```

`live` performs the no-content Work IQ preflight, runs ASSERT with inference concurrency one,
imports correlated Application Insights spans, judges the OTLP trace groups by `session.id`, and
applies the Hotel Servicing Rubric v3 gates. It fails if any target token is invalid, any smoke case
is unjudged, trace correlation is incomplete, any weight-10 dimension fails, or the weighted score
is below `0.68`.

Use `config/regression.yaml` for generated functional and multi-turn coverage and
`config/adversarial.yaml` for reviewed synthetic attacks. Generated test sets are written under
ignored `artifacts/generated/`; review them before live execution.

## Results viewer

The viewer is loaded from the same pinned ASSERT source:

```bash
python3 scripts/run_assert_ui.py
```

It binds to `http://127.0.0.1:5174`, reads this repository's ignored `artifacts/results/` directory,
and starts in read-only mode. Raw transcripts and traces must not be committed.
