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
exactly 20 rows, all thirteen metrics present, non-null numeric scores, Boolean
pass/fail values, nonempty reasons, and no evaluator errors. Honest quality
failures remain failures and do not prevent an execution-complete evaluation.
Failed or empty native jobs are persisted as incomplete, never reported as
passed. No local judge fallback changes that outcome.
