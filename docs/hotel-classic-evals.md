# Hotel classic native evaluations

`scripts/run_hotel_classic_evals.py` captures 20 synthetic, everyday customer
interactions from the deployed `hotel-servicing-agent` and submits their actual
responses to a native Foundry evaluation. Both the evaluation group and every
run are named exactly `hotel-servicing-classic-evals`.

The reference definition is
`eval_f801b4c226ef4db5a3cffd872a263e4c`
(`bank-servicing-standard-20-standard-20-20261028-v9-corrected`).
The runner copies its criteria, initialization parameters, and input mappings
unchanged, omitting only server-generated criterion IDs. Its thirteen metrics are:

- groundedness, coherence, relevance, fluency
- tool_call_accuracy, tool_selection, tool_input_accuracy
- tool_output_utilization, tool_call_success, tool_use_quality
- intent_resolution, task_completion, task_adherence

The judge remains the reference deployment, `gpt-5.4-mini`. The bank agent is
never invoked, and a substitute model never generates the hotel answers.

## Evidence and safety

The dataset is `evaluation/hotel-servicing-classic-interactions.jsonl`. It asks
about policies, property information, accessibility, fees, dates, privacy, and
booking clarification. It does not authorize reservations, changes, charges,
staff contacts, or messages. Each item starts an independent hosted response
with `store: false`. The runner checks the endpoint's latest version before and
after capture; changing versions invalidates the run.

The exact hosted output is retained, including function calls, arguments, call
IDs, tool outputs, and the final answer. Grounding context contains the
observed user query and tool outputs; an interaction without tool use gets an
empty tool-output array, not invented evidence. Tool names, descriptions, argument types, required arguments,
and property enums are extracted from registered source definitions without
importing optional hosting dependencies.

Runtime requests, captures, evaluation/run IDs, status, per-item output, and
summary are ignored artifacts under:

`src/hotel-servicing-agent/.foundry/results/dev/hotel-servicing-classic-evals/`

This independent workflow does not modify the rubric evaluator or its metadata.

## Running and resuming

Use the repository's configured Python environment:

```bash
python scripts/run_hotel_classic_evals.py capture
python scripts/run_hotel_classic_evals.py prepare
python scripts/run_hotel_classic_evals.py run
python scripts/run_hotel_classic_evals.py poll
```

All Azure requests and writes use `az rest`; only read-only per-item result
download uses the Azure AI Projects SDK with `AzureCliCredential`. Capture is
resumable and rejects cached responses for another target or dataset. `prepare`
reuses the persisted group only after checking its live metric definitions.

`run --source <path>` accepts a native `data_source` JSON object, allowing a
registered dataset/file reference instead of inline JSONL when the service
requires it. Without this option it submits the exact captured items using
`jsonl` / `file_content`.

A terminal status alone is not success. The runner requires `completed`,
exactly 20 rows, all thirteen metrics present, finite numeric scores and Boolean
pass/fail values for applicable results, nonempty reasons, and no evaluator errors.
Top-level native tool-metric N/A results are accepted only with null score/pass values,
an explicit native `Not applicable:` reason, and actual captured output containing
messages but no tool calls. Composite N/A submetrics require the parent's
explicit skipped-evaluator list, an empty failed-evaluator list, and their own
nonempty reasons. N/A results are
reported separately, never assigned invented scores or counted as metric passes.
Unexplained nulls, missing metrics, quality-metric nulls, and evaluator errors
remain incomplete. Honest quality
failures remain failures and do not prevent an execution-complete evaluation.
Failed or empty native jobs are persisted as incomplete, never reported as
passed. No local judge fallback changes that outcome.

## Completed native execution, November 6, 2026 UTC

The exact run `hotel-servicing-classic-evals` completed with all 20 customer
interactions and all 13 unchanged banking-reference criteria. Native result counts
are 4 passed, 16 quality failures, zero execution errors, and zero skipped rows.
The downloaded evidence contains every expected case ID, no incomplete rows,
and criteria identical to the banking reference apart from server-generated IDs.

- Group: `eval_1911543c25dd4a8880ca239b0fea1401`
- Completed run: `evalrun_08584076767204657932148607209CU37`
- [Native evaluation report](https://ai.azure.com/nextgen/r/ji1zPie9TfWL5dalQFKRBg,rg-mcasalaina-4iqs-2701,,mcasalaina-4iqs-2701-resource,mcasalaina-4iqs-2701/build/evaluations/eval_1911543c25dd4a8880ca239b0fea1401/run/evalrun_08584076767204657932148607209CU37)

The source is 20 actual deployed version-8 responses, not replacement-model
answers. Eighteen interactions used tools. `classic-13` correctly requests
clarification of reversed stay dates, and `classic-17` asks what information is
needed for a folio investigation. Those two responses contain no tool calls.
The service explicitly marked their inapplicable tool results N/A, including
composite submetrics, for 19 N/A result entries in total. Those are not missing
evaluations or execution errors.

| Metric | Passed | Quality failed | Native N/A |
| --- | ---: | ---: | ---: |
| groundedness | 20 | 0 | 0 |
| coherence | 20 | 0 | 0 |
| relevance | 20 | 0 | 0 |
| fluency | 20 | 0 | 0 |
| tool_call_accuracy | 16 | 2 | 2 |
| tool_selection | 18 | 0 | 2 |
| tool_input_accuracy | 9 | 9 | 2 |
| tool_output_utilization | 20 | 0 | 0 |
| tool_call_success | 19 | 0 | 1 |
| tool_use_quality | 8 | 10 | 2 |
| intent_resolution | 20 | 0 | 0 |
| task_completion | 18 | 2 | 0 |
| task_adherence | 20 | 0 | 0 |

The dominant judge-reported quality issue is unsupported temporal arguments:
many knowledge searches supply `as_of: 2026-09-01`, which the judge cannot ground
in the customer query. Some composite results also question inferred property
identifiers. The two task-completion failures are unanswered check-in/checkout
times and breakfast details. Standalone and composite tool judgments differ on
some rows, so their original results remain separate rather than being reconciled
or overwritten. These are quality judgments requiring review, not runtime
failures or proof that every criticized inference is wrong. No agent runtime
changes or redeployment were made.

The completed run used the project-managed-identity scheduling path documented
in [the native execution workaround](foundry-evaluator-rubrics.md#native-execution-workaround).
The scheduler's appended display-name suffix was removed using a supported
display-name-only update. Neither status nor scores were edited.
The temporary schedules and project-role assignment were removed and their
absence independently verified.

Native status, SDK-downloaded per-item results, summary, requests, and cleanup
evidence are retained under the ignored
`src/hotel-servicing-agent/.foundry/results/dev/managed-identity-bounded-cron/`
directory, with `classic-` prefixes. `classic-summary.json` and the shared
`verified-results.json` record `execution_complete: true`. The standard runner's
`run.json` now points to this completed run, so `poll` downloads and validates it.

## Earlier direct-submission failures

The following unsuccessful attempts are preserved for diagnosis. They do not
describe the completed scheduled run above. Direct delegated-user submission
remains blocked in this project, so use the documented scheduling workaround
instead of assuming that another identical direct submission will work.

All twenty actual hotel version-8 responses were captured. Eighteen included
tool traces. No booking mutations or outbound messages were requested.
The native criteria preserve all thirteen reference metrics unchanged.

Group `eval_1911543c25dd4a8880ca239b0fea1401`, delegated-user run
`evalrun_277a7d0a6d3a4694a12601113a545dee`, has status `failed`, zero scored
rows, `error: null`, no report URL, and no backend log reference.
Retries remained unsuccessful after the approved Foundry account storage-role
assignment and its propagation wait. The native rubric workflow fails at
the same pre-scoring stage. At that point no classic evaluation had completed.
The source of the shared early failure is not established.

The exact run status, original service counts, and empty output are retained
in the ignored result directory, including files prefixed with the run ID.
`execution_complete: false` is authoritative. Zero row-level errors or zero
quality failures in an empty result are not evidence of success.

A subsequent certificate-authenticated application-identity attempt submitted the same group,
twenty captured interactions, and all thirteen unchanged reference criteria. Run
`evalrun_d15b0799716c47b38c806d0e6b5fc8a5` also failed with zero scored rows and no
native error detail or report URL. Its raw status and output are retained under the adjacent
ignored `application-identity-retry/` directory. The temporary application, service principal,
role assignment, and local credential/profile were removed, with active directory and role
queries independently confirming cleanup.

The legacy rubric submission endpoint additionally exposes an Azure ML backend token-exchange
failure, `Getting user token was not successful.` This is concrete authentication-stage evidence
for that submission path, not proof of the underlying cause of the classic run's silent failure.
Fresh user tokens, explicit ML-token forwarding, and application authentication did not resolve
the failures. See [authentication-stage diagnostics](foundry-evaluator-rubrics.md#authentication-stage-diagnostics-november-6-2026-utc)
for the shared investigation. Both requested native evaluations subsequently
completed through the managed-identity scheduling path.
