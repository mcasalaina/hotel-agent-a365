# ASSERT evaluation for Hotel Guest Services

## Purpose and identity boundary

ASSERT evaluates the deployed Hotel Guest Services Hosted Agent as the Agent 365 agent user. The
runner's workload identity is used only for judge models, Application Insights, encrypted artifact
storage, and controlled job execution. It is never accepted as the target identity.

The callable target requests an agent-user bearer token from the Microsoft Entra ID Auth SDK
sidecar at the loopback-only `GetAuthorizationHeaderUnauthenticated/Foundry` endpoint. It supplies both
`AgentIdentity` and `AgentUserId`, validates the Microsoft signature and agent claims, and then calls
the Hosted Agent Responses endpoint with that token. `x-ms-user-identity` is preserved on the
initial request and every MCP approval continuation, but it is treated only as routing metadata.

The implementation validates:

- the approved tenant and Foundry audience;
- `idtyp=user`;
- the Hotel Guest Services agent-user object ID in `oid`;
- the Hotel Guest Services agent identity in `azp` or `appid`;
- agent-user facet `13` in `xms_sub_fct`;
- agent-identity facet `11` in `xms_act_fct`;
- the parent blueprint in `xms_par_app_azp`;
- `nbf`, `exp`, issuer, and Microsoft signing keys.

No token, assertion, or credential is written to the correlation ledger. Wrong user, wrong audience,
wrong parent, expired token, sidecar failure, Hosted Agent rejection, missing Work IQ context, and
incomplete trace correlation all fail closed.

## Repository layout

| Path | Purpose |
|---|---|
| `evaluation/assert/assert-source.lock.json` | Reviewed ASSERT commit, deterministic build inputs, and wheel hash |
| `evaluation/assert/config/` | Smoke, generated regression, and adversarial pipelines |
| `evaluation/assert/config/specs/` | Reviewed hotel behavior specification and ASSERT taxonomy |
| `evaluation/assert/config/seeds/` | Nine deterministic smoke cases |
| `evaluation/assert/policies/` | Rubric weights, trace requirements, redaction, and retention |
| `evaluation/assert/src/hotel_assert/` | Identity target, correlation, trace import, redaction, and gates |
| `evaluation/assert/baselines/` | Baseline metadata; initially unpromoted |
| `infra/evaluation/assert-job.bicep` | Controlled Container Apps Job with runner and auth sidecar |
| `scripts/bootstrap_assert.py` | Reproducible source build and hash verification |
| `scripts/run_assert_evaluation.py` | Validation, preflight, live run, trace import, and gates |
| `scripts/run_assert_ui.py` | Pinned local ASSERT viewer |

## Rubric mapping and gates

The ASSERT judge uses all 13 Hotel Servicing Rubric v3 dimensions. Six safety and data-integrity
dimensions have weight 10 and are hard gates. Five task-correctness dimensions have weight 6. Two
interaction-quality dimensions have weight 3. The aggregate pass threshold remains `0.68`.

Response-and-trace dimensions use the lower success rate of the response judge and trace judge.
Trace-required cases are invalid when an expected turn lacks a correlated trace tree. The smoke
gate additionally requires all nine deterministic cases to be judged.

The importer queries a bounded Application Insights window using trace and response IDs from the
local ledger. It joins bridge and Hosted Agent telemetry, adds stable `session.id`,
`assert.run_id`, `assert.case_id`, and turn attributes, redacts secrets and content, and emits OTLP
JSON for `assert-ai judge-traces`.

## Controlled Azure job

Deploy `infra/evaluation/assert-job.bicep` only to the test tenant. The job has no ingress and runs one replica. Its composite image contains two supervised processes:

1. The ASSERT runner uses a user-assigned managed identity for judge models, Log Analytics, Key Vault,
   registry pulls, and restricted artifact storage.
2. The pinned Entra Auth SDK process receives the parent blueprint credential from a Key Vault-backed
   Container Apps secret and issues the configured agent-user token only on loopback.

The supervisor removes all `AzureAd__ClientCredentials__*` variables from the runner child
environment and terminates the broker when the evaluation exits, allowing the job to complete.

Use a restricted Azure Files environment storage mount for `/workspace/artifacts`. Grant the
workload identity only the required model-inference, Log Analytics query, registry-pull, Key Vault
secret-read, and storage roles. Do not expose port 5000 through ingress, a load balancer, or a public
endpoint.

The `ASSERT live evaluation` workflow uses GitHub OIDC only to start the pre-provisioned job. It does
not hold the blueprint secret or an agent-user token. The job itself performs preflight before any
case and exits nonzero on any gate failure.

The first live acceptance run proved the configured agent-user claim chain, authenticated Copilot,
Mail, and Teams without retrieving content, completed all nine target conversations, reconstructed
every expected trace group, and exercised response and trace judging. The rubric gate failed closed
on actual agent-quality findings even though the weighted score exceeded the aggregate threshold.

## Calibration and baseline promotion

The committed baseline is deliberately `not_promoted`. Before promotion:

1. Run known-pass and seeded known-fail transcripts for every dimension.
2. Repeat a fixed sample enough times to measure judge variance.
3. Review disagreements against deterministic expectations.
4. Record the measured repeatability tolerance, repository commit, Hosted Agent version, bridge
   revision, model deployments, taxonomy and configuration hashes, run ID, and restricted artifact
   location.
5. Promote only a run that passes identity, smoke, hard-gate, aggregate, and trace-completeness
   gates.

Do not invent a regression delta. Use the measured repeatability tolerance. A new severe behavior
class fails review even when the weighted score remains above threshold.

## Artifacts and privacy

Content capture is off by default. The importer drops prompt, response, mailbox, chat, and tool-result
content unless an isolated synthetic review explicitly enables it. Credential-like keys, bearer
tokens, JWTs, and email addresses are redacted before local writes.

Local raw artifacts are ignored and expire after seven days. Restricted cloud artifacts require
encryption, RBAC, purge support, and the retention policy in
`evaluation/assert/policies/retention.yaml`. CI may publish aggregate gate results only.

## Authoritative channel attestation

Direct agent-user invocation proves the target identity and Hosted Agent path, but it does not prove
the full Teams channel boundary. Keep a periodic real Teams DM canary covering Mail, Teams,
cross-Microsoft-365 reads, and mutation refusal. Never replace this canary with an unsigned
`/api/messages` test endpoint.
