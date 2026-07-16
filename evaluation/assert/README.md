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

The **Hotel Guest Services Conversations** suite has 12 reviewed cases: eight fixed natural requests
and four adaptive two-turn ASSERT scenarios covering follow-ups, corrections, context isolation, and
safety boundaries.

```bash
evaluation/assert/.venv/bin/python scripts/run_assert_evaluation.py live \
  --config evaluation/assert/config/smoke.yaml \
  --suite hotel-guest-services-conversations \
  --workspace-id "$APPLICATIONINSIGHTS_WORKSPACE_ID" \
  --require-all-cases 12
```

`live` performs the no-content Work IQ preflight, runs ASSERT with inference concurrency one,
imports correlated Application Insights spans, judges the OTLP trace groups by `session.id`, and
applies the Hotel Servicing Rubric v3 gates. It fails if any target token is invalid, any reviewed
case is unjudged, trace correlation is incomplete, any weight-10 dimension fails, or the weighted
score is below `0.68`. Malformed judge responses are retried up to three times without rerunning the
agent conversation.

ASSERT scenarios are adaptive rather than scripted: the tester model generates each user turn from
the reviewed scenario description and the agent's preceding answer. `max_turns: 2` bounds the
reviewed scenarios to the intended opening and follow-up. The callable target receives the complete
ordered conversation history and keeps both turns in one correlated session.

Use `config/regression.yaml` for generated **Hotel Guest Services Coverage** conversations and
`config/adversarial.yaml` for **Hotel Guest Services Safety** conversations. Both include the tester
model required to execute generated scenarios. Generated test sets are written under ignored
`artifacts/generated/`; review them before live execution.

## Results viewer

The viewer is loaded from the same pinned ASSERT source:

```bash
python3 scripts/run_assert_ui.py
```

It binds to `http://127.0.0.1:5174`, reads this repository's ignored `artifacts/results/` directory,
and starts in read-only mode. Raw transcripts and traces must not be committed.
