# Hotel Guest Services ASSERT evaluation

The Agent 365 instance display name is `Lyrenza Hotel Guest Services`. The reusable template
remains `Hotel Guest Services`, and the instance alias remains `hotelguestservices`.

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

## Foundry catalog publication

The Foundry catalog assets are separate from the delegated ASSERT runner. Publish the reviewed
datasets and rubric versions without invoking an agent:

```bash
.venv/bin/python scripts/recreate_foundry_evaluation_assets.py \
  --environment hotel-2701 \
  --project-endpoint "$AZURE_AI_PROJECT_ENDPOINT" \
  --tenant-id "$AZURE_TENANT_ID" \
  --connection-name hotel-source-archive \
  --output src/hotel-servicing-agent/.foundry/results/hotel-2701/assets.json
```

Evaluator generation creates the catalog parent first; reviewed rubric dimensions are then
published and verified through both custom-catalog listing and version listing. Dataset content
is downloaded from its registered storage URI and compared with source SHA-256 hashes. Existing
content is never silently overwritten; `--replace-dataset-content` requires an intentional,
authorized correction before running the affected version. Generation operation IDs and partial
publication results are persisted for resumption.

The root `eval.yaml` selects 21 quality cases. The agent-root `eval.yaml` selects 27 core cases;
the temporal dataset contains three cases. All retain the strict September 1, 2026 boundary.
`RES-FAMILY-2026` belongs to Maria Garcia at `HTL-004`, September 10–12, 2026, and is future
relative to that boundary.

The core evaluator threshold is explicitly pinned to `0.5`. Retained source-worktree results
`eval_12dc65a3a74d44c6ac8a93018d0f7589/evalrun_cd491f4938584280a09b3a2d3b21aad4`
record this threshold for `hotel-core-quality` version 2. The reviewed version 4 keeps that
threshold; its dimensions are independently verified against the current source definition.
The other thresholds remain `0.68` for the Hotel rubric and `0.8` for language, temporal, and mail.

Corrected evaluation definitions use the `-r2` suffix, the SDK's required `item_schema` field,
and readback validation of required query fields. Earlier definitions and run history are retained.
Created definition IDs are cached immediately in the selected environment; subsequent runs fetch
only those IDs rather than enumerating unrelated project evaluations.
The create request calls the field `item_schema`; the official response exposes that same schema
as `data_source_config.schema.item` (`schema_` in the Python SDK). This service also returns an empty
extra `item_schema` field, so verification checks the persisted response schema rather than that
extra field. The publication record includes the normalized non-empty `itemSchema` and its source
field. Prior definitions whose response `schema.item` is empty are rejected.

```bash
.venv/bin/python scripts/run_foundry_agent_quality.py \
  --environment hotel-2701 --suite quality --register-only
.venv/bin/python scripts/run_foundry_agent_quality.py \
  --environment hotel-2701 --suite full --agent-version "$DEPLOYED_AGENT_VERSION"
.venv/bin/python scripts/run_foundry_agent_quality.py \
  --environment hotel-2701 --suite temporal --agent-version "$DEPLOYED_AGENT_VERSION"
.venv/bin/python scripts/run_multilingual_evaluator_quality.py \
  --environment hotel-2701 --connection-name hotel-source-archive
```

The runners read the selected azd environment's `.env` without modifying it. Explicit endpoint,
tenant, agent-name, and agent-version flags override those values. They never use historical
deployment claims from the source tenant's metadata. Run only after the selected target version
and its data integrations are ready. Identical runs resume by default; `--new-run` deliberately
creates another run. Results and the selected environment's metadata overlay are checkpointed
immediately, then updated with per-item outcomes and failure clusters. The multilingual command
scores three reviewed candidate responses without invoking the deployed agent. Its registered
validation subset contains only the reviewed queries and candidate responses from core cases
16, 17, and 18; it does not generate questions. The current static definition is
`hotel-language-continuity-quality-v2-r3`: dataset version `2.3` has flat `query`/`response`
columns, and the runner submits those exact verified rows through `file_content`.
Definition publication verifies those same required columns before recording success.
The earlier `2.0` wrapper format and `2.1` `evaluation_query`/`evaluation_response` format remain
historical, not alternate current schemas. Run identity includes the registered dataset version
and file hash, so a corrected file cannot silently resume a previous format's run.

`infra/evaluation/assert-job.bicep` and GitHub environment configuration are optional source-only
deployment definitions until an actual controlled-runner deployment is independently verified.
Catalog publication does not provision either.

## Bounded hosted knowledge and language evaluation

`run_hosted_knowledge_quality.py` captures eight actual Responses-protocol turns for an explicit
deployed version,
including one persistent EN → ES → ZH → AR → EN conversation. Every question concerns
Scottsdale amenities or parking, not reservations or Fabric data. It first inventories the known
Hotel evaluation runs and reuses the existing r2 language and quality definitions.

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill \
  .venv/bin/python evaluation/assert/run_hosted_knowledge_quality.py \
    --agent-version 2 --stage all
```

Captures are resumed without repeating agent calls. Actual text, response/session/conversation IDs,
request correlation IDs, the version returned by the agent, tool outputs, and judge results are
preserved under `.foundry/results/hotel-2701/agent-v<VERSION>-knowledge-language/`. Version-1
captures and runs are not overwritten or reused as version-2 outputs. These records explicitly
have `agentInvoked: true`, unlike the three reviewed static candidates.

Responses tool items are translated into chat-message roles for transcript evaluators without
changing their arguments, tool results, or generated text. Duplicate response fragments remain
verbatim rather than being cleaned up before judging. Local factual checks for USD 25/night and
07:00–21:00 are identified separately from cloud rubric scores; unexpected operations-tool calls
and errors must be reported even when the final facts are correct.
An explicit local duplicate-text assertion fails adjacent repeated full answers, paragraphs,
sentences, or sentence blocks in English, Spanish, Chinese, and Arabic. It is persisted per case,
and any duplicate fails the combined case verdict regardless of the cloud grader's score.
Inventory identifies existing actual-agent runs by version, not the static evaluator's `v2` name.
An existing version run without its complete capture files blocks new captures rather than
silently invoking the agent again. Actual function arguments and unexpected property IDs are
retained for diagnosing Scottsdale/`HTL-004` identity errors.
The combined case verdict requires the duplicate assertion, detected language, factual checks,
cloud language and primary Hotel rubric verdicts, knowledge-only tool routing, and property-ID
integrity to pass. Nonapplicable mail/temporal grader failures remain visible separately and do not
enter that combined verdict. The metadata overlay retains version-specific run references as well
as its latest-result pointer.
The reused quality definition also retains mail and temporal graders. Their nonapplicable failures
must not be presented as factual-knowledge failures: report the Hotel rubric separately, retain
all component verdicts, and do not run the source reservation/temporal datasets in this bounded mode.

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

The **Hotel Guest Services Conversations** suite has 25 reviewed cases: sixteen fixed natural requests
and nine adaptive two-turn ASSERT scenarios covering follow-ups, corrections, context isolation,
multilingual continuity, false language-switch cues, and safety boundaries.

```bash
evaluation/assert/.venv/bin/python scripts/run_assert_evaluation.py live \
  --config evaluation/assert/config/baseline-quality.yaml \
  --suite hotel-guest-services-conversations \
  --workspace-id "$APPLICATIONINSIGHTS_WORKSPACE_ID" \
  --require-all-cases 25
```

`live` performs the no-content Work IQ preflight, runs ASSERT with inference concurrency one,
imports correlated Application Insights spans, judges the OTLP trace groups by `session.id`, and
applies the 15-dimension local Hotel Servicing Rubric policy gates. It fails if any target token is
invalid, any reviewed case is unjudged, trace correlation is incomplete, any weight-10 dimension fails, or the weighted
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
