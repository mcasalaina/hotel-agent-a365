# One behavior per YAML

This directory decomposes the higher-level behavior spec in
[`../specs/hotel-agent-behaviors.md`](../specs/hotel-agent-behaviors.md) into **one ASSERT config per
behavior**. Each file isolates a single behavior of the Hotel Guest Services agent so a run scores
exactly one concern, making regressions easy to attribute and fix.

The parent suites (`../baseline-quality.yaml`, `../adversarial.yaml`, `../regression.yaml`) remain the broad,
multi-dimension suites. These per-behavior configs are the focused complement: same schema, same
judge rubrics, one behavior at a time.

## Layout

```
behaviors/
  README.md                     # this file
  specs/
    hotel-agent-taxonomy.json   # directory-local copy of ../specs/hotel-agent-taxonomy.json (see "Why a taxonomy copy")
  <behavior-slug>.yaml          # one config per behavior (14 of them)
```

## The 14 behaviors

Each config maps 1:1 to one custom judge dimension from the shared rubric
(`../../policies/rubric-policy.json`). The judge dimension **description and rubric are copied
verbatim** from `../baseline-quality.yaml` / `../adversarial.yaml` — these files do not re-word or re-tune any
rubric.

| Config | Behavior it scores (judge dimension) |
|---|---|
| `authoritative-source-routing.yaml` | `authoritative_source_routing` — approved-knowledge vs operational-record routing; no memory/web as authoritative |
| `property-identity-and-sequence.yaml` | `property_identity_and_sequence` — resolve identity first, preserve exact ID, order dependent tools |
| `read-only-boundaries.yaml` | `read_only_boundaries` — never attempt or claim a send/post/cancel/modify/delete |
| `work-iq-delegated-protocol.yaml` | `work_iq_delegated_protocol` — agent-user context + no-content access-check preflight |
| `unsupported-fact-transparency.yaml` | `unsupported_fact_transparency` — no guessing, no hidden empty results, no false success |
| `privacy-and-data-safety.yaml` | `privacy_and_data_safety` — no credential/instruction/cross-user/cross-property leakage |
| `property-attribution-date-and-citations.yaml` | `property_attribution_date_and_citations` — attribution, effective dates, approved citations |
| `structured-property-labeling.yaml` | `structured_property_labeling` — official per-property labels, no mixed rows |
| `chain-wide-completeness.yaml` | `chain_wide_completeness` — all 20 properties incl. zero-result rows |
| `reservation-date-and-status-semantics.yaml` | `reservation_date_and_status_semantics` — check-in field, inclusive window, future/arriving status |
| `exact-record-full-history-lookup.yaml` | `exact_record_full_history_lookup` — exact-ID lookup over full history, no stray date filter |
| `multi-turn-context-continuity.yaml` | `multi_turn_context_continuity` — preserve active subject; no prior-subject leak on switch |
| `language-continuity.yaml` | `language_continuity` — preserve the user's established language across text, voice, and tool-backed responses |
| `mail-recipient-integrity.yaml` | `mail_recipient_integrity` — preserve explicit To, CC, and BCC recipients for sends and replies |

Each config's `judge.dimensions` contains that one behavior dimension plus `general_quality`.
`general_quality` is the only dimension with `allow_not_applicable: false`, so every case yields at
least one always-applicable score even when the behavior dimension is not-applicable for a given
case.

## Conventions (identical to the parent configs)

- **Shared suite name** `hotel-guest-services-behaviors`; each config's `run:` is the behavior slug,
  so results land in a distinct per-behavior directory with no collision.
- **Reserved-dimension disable pattern**: every config sets
  `judge.disabled_dimensions: [policy_violation, overrefusal]`. These two are taxonomy-derived
  reserved dimensions that cannot be rubric-customized, so — exactly like the existing configs —
  they are disabled here.
- **Judge model** `azure/gpt-5.4-mini` (`max_tokens: 8192`), matching the existing configs.
- **Live target** `hotel_assert:chat` with `concurrency: 1`, `strict: true`. See
  [`RUNNING-LIVE.md`](RUNNING-LIVE.md) for the live-identity prerequisites.

## Generation vs. scoring (important)

All 14 configs generate their evaluation cases with ASSERT (`test_set.enabled: true`), mirroring
`adversarial.yaml`'s explicit `stratify` style (named dimensions + levels + `level_count`). Two
things are worth knowing:

1. **Generation is intentionally broad; scoring is narrow.** ASSERT always injects the full taxonomy
   as a "behavior" generation factor, so each config produces conversations spanning the shared
   taxonomy — just like `adversarial.yaml` / `regression.yaml`. The **per-behavior focus** comes
   from three levers: the behavior-specific `context:`, the behavior-specific `stratify:`
   dimensions, and — decisively — the **single custom judge dimension** each config scores. So every
   config exercises realistic agent behavior but reports on exactly one concern.
2. **`multi-turn-context-continuity.yaml` is scenario-only.** Single-turn prompts cannot exercise
   cross-turn continuity, so that config omits the `prompt` block and generates scenarios only.

Generation sizes are modest (prompt 12 / scenario 6 for most; scenario 12 for the multi-turn config) to
keep a single-behavior run cheap. Bump `sample_size` for a heavier sweep.

### Why a taxonomy copy under `behaviors/specs/`

ASSERT resolves stage paths such as `taxonomy_path` **relative to the config file's own directory**
and rejects `../` traversal. To keep the `taxonomy_path: specs/hotel-agent-taxonomy.json` literal
**identical** to the parent configs while living one directory deeper, this folder carries a
byte-for-byte copy of `../specs/hotel-agent-taxonomy.json` at `specs/hotel-agent-taxonomy.json`. If
the canonical taxonomy changes, re-copy it:

```powershell
Copy-Item ..\specs\hotel-agent-taxonomy.json specs\hotel-agent-taxonomy.json -Force
```

## Validate a config

The repo's own `validate` subcommand only checks the three canonical configs (`baseline-quality`,
`adversarial`, `regression`), so it does not cover these per-behavior files. Each config here was
instead validated by loading it through the **pinned ASSERT config parser + stage registry** — the
exact code path the runner uses (`load_config` → `load_runtime_context(..., stage_modules=STAGES)`)
— against the ASSERT commit this repo pins, and confirming zero schema errors. Bootstrap the pinned
ASSERT per [`../../README.md`](../../README.md) (`python scripts/bootstrap_assert.py --install`)
before running anything live.

## Run one behavior (live target)

The `hotel_assert:chat` target calls the live hosted Foundry agent, so a run needs the live-identity
environment + sidecar described in [`RUNNING-LIVE.md`](RUNNING-LIVE.md). From the repo root:

```powershell
# Full harness (preflight + correlated trace import). --suite overrides the config's suite label.
python scripts\run_assert_evaluation.py live --config evaluation\assert\config\behaviors\read-only-boundaries.yaml --suite hotel-guest-services-behaviors

# Or a plain run without trace correlation:
python scripts\run_assert_evaluation.py run --config evaluation\assert\config\behaviors\read-only-boundaries.yaml --suite hotel-guest-services-behaviors
```

Start with a small `sample_size` for a quick signal, then scale up.
