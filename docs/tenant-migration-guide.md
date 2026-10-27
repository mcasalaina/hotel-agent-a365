# Complete tenant migration guide

This runbook moves the complete Hotel Guest Services solution to a new Microsoft
365 and Azure tenant. It covers Microsoft Foundry, Foundry IQ, Fabric, evaluators,
Agent 365, Teams, email, and the authenticated voice frontend. Follow the dependency
order below. A successful deployment is not acceptance, and an administrator's
successful request does not prove that the agent identity can use the same service.

Use tenant-local identities and resource IDs throughout. Keep new resource names
generic, such as `hotel-servicing-agent`, `HotelOperations`, and `hotel-voice-proxy`.
Do not put `migration` or the fictional customer brand in newly provisioned
technical resource names.

## Contents

- [1. Establish the implementation baseline](#1-establish-the-implementation-baseline)
- [2. Inventory and authenticate](#2-inventory-and-authenticate)
- [3. Obtain administrative and runtime permissions](#3-obtain-administrative-and-runtime-permissions)
- [4. Prepare Azure and Foundry](#4-prepare-azure-and-foundry)
- [5. Move canonical data and the Fabric estate](#5-move-canonical-data-and-the-fabric-estate)
- [6. Configure and publish the Fabric Data Agent](#6-configure-and-publish-the-fabric-data-agent)
- [7. Rebuild Foundry IQ](#7-rebuild-foundry-iq)
- [8. Create the Agent 365 blueprint and permissions](#8-create-the-agent-365-blueprint-and-permissions)
- [9. Deploy the messaging bridge](#9-deploy-the-messaging-bridge)
- [10. Publish the template and create the instance](#10-publish-the-template-and-create-the-instance)
- [11. Deploy and verify the hosted agent](#11-deploy-and-verify-the-hosted-agent)
- [12. Recreate evaluator assets and run evaluations](#12-recreate-evaluator-assets-and-run-evaluations)
- [13. Accept Teams and email](#13-accept-teams-and-email)
- [14. Deploy and accept voice](#14-deploy-and-accept-voice)
- [15. Complete the release evidence and rollback plan](#15-complete-the-release-evidence-and-rollback-plan)
- [16. Troubleshooting](#16-troubleshooting)
- [17. Verified rollout status and remaining work](#17-verified-rollout-status-and-remaining-work)

## 1. Establish the implementation baseline

### Important: documentation is not code promotion

At the time this guide was written, the validated target rollout included changes
that were still in active worktrees, not all committed to `main`. This guide's
publication does not merge those changes, deploy them, or make the whole solution
accepted. Record and promote the reviewed implementation commit before treating a
fresh checkout as a reproducible release.

Narrow reviewed source repairs are preserved on branch
`mcasalaina-hotel-agent-2701`: `115c954` adds memory-only popup-free sign-in,
`7c09cf0` preserves the deployed stateless email/sender-resolution repair, and
`6668898` adds the real prerecorded acceptance input. `9885ef8` preserves fresh
call/session binding, `3c99302` preserves model descriptions and blocks unsafe
existing-model replacement, and `432e668` adds supported proxy replica affinity.
`3a93357` preserves evaluation rubrics, datasets and reproducible runners.
`6febbec` preserves the hosted runtime, Agent 365 notification normalization,
stable SDK pins and the directly required IQ setup/verification helpers.
`7c0b7e0` preserves Container Apps infrastructure, target template identifiers,
the permission contract and guarded provisioning helpers. `9c4815c` preserves
the remaining web configuration and production offline-playback guards.
`7d45cc9` preserves the deterministic Fabric/data/knowledge source, V2 ontology
and native-state replacement guard. Its complete staged source passed 373
offline unit tests and the repository's lint, formatting, type, naming and
configuration checks.
These commits do not promote all remaining worktree changes or merge the
implementation branch into main. Source preservation does not itself redeploy
the hosted agent, bridge, evaluators or browser proxy.

The historical `main` baseline examined for this guide was
`8cdb88ffed2a738f4851297702bf88ce94130af2`. In that baseline:

- `infra/agent365-bridge.bicep` deploys App Service, not the target rollout's
  Container Apps bridge with Key Vault secret references.
- `infra/voice-web.bicep` contains previous-environment defaults and grants a broader
  project role than the target's separately assigned `Foundry User` role.
- `scripts/deploy_semantic_model_and_report.py` is a placeholder, not a deployment
  implementation.
- Sample environment files and several deployment documents contain historical
  tenant IDs, resource IDs, endpoints, and version numbers.

Do not execute the Container Apps examples below against an incompatible template.
First promote or obtain the reviewed implementation with these contracts:

| Area | Required behavior before release |
|---|---|
| Hosted orchestration | `create_agent` sets `default_options={"store": False, "allow_multiple_tool_calls": False}`. The actual Foundry request has `parallel_tool_calls: false`. |
| Property provenance | Fabric must retrieve the property for a guest reservation before property-scoped IQ retrieval. A claimed property in model text is not evidence. |
| Reservation identity | Resolve the real guest from the incoming message or explicit guest context, never from the bridge or administrator identity. Unknown guests fail closed. |
| Bridge authentication | Exchange the real Agent 365 agent-user context and pass the resulting bearer to Foundry. No fabricated `x-ms-user-identity` header. |
| Email ownership | The hosted agent composes one grounded guest-facing answer without sending it. The bridge sends the reply once. |
| Fabric publication | Preserve native source configuration, validate the exact draft, and compare published source fingerprints. Do not replace native settings with a generated draft. |
| Voice | Signed Entra browser authentication, opaque short-lived WebSocket sessions, managed-identity Foundry access, and no production offline fallback. |
| Infrastructure | Container Apps bridge, managed-identity registry pulls, Key Vault references, and a voice template compatible with the selected environment reuse strategy. |

Review the corresponding code, configuration, and tests, not just this table.
Keep `agent-instructions.md` and the hosted agent's instruction copy identical.
Run `make check` on the intended release checkout. Retain the commit SHA, package
locks, passing results, and immutable image tags. Do not deploy from an unexplained
dirty worktree.

### Tools and secret handling

Use Python 3.13, Node.js 22, Azure CLI, Azure Developer CLI with the
`azure.ai.agents` extension, Agent 365 CLI, and Git. Docker is optional when using
Foundry remote source builds and ACR remote container builds.

For a new development environment, install the repository's declared dependencies
with `make setup`. Check the configured package feed first. In environments where
`files.pythonhosted.org` is blocked, use the approved internal feed, not a bypass.
The target voice image used `https://packagefeedproxy.microsoft.io/pypi/simple/`.

Never commit `.env`, `.azure`, generated Agent 365 configuration, deployment-state
files containing environment bindings, credentials, bearer tokens, mail bodies,
or generated ZIP packages. Keep operational evidence in approved private storage.
This public runbook deliberately uses placeholders rather than tenant-specific
operator addresses and private acceptance artifacts.

## 2. Inventory and authenticate

Create a private source-to-target mapping before changing anything. Record:

| Layer | Values to discover in the target |
|---|---|
| Directory and Azure | Tenant ID/domain, subscription, operator object ID, resource groups, region, providers, quotas, licenses |
| Foundry | Account and project ARM IDs, project endpoint, model deployment/version, hosted agent name/version/identity, App Insights |
| Supporting Azure | Search, storage, registry, Container Apps environment, Key Vault, bridge and proxy identities |
| Fabric | Capacity, workspace, both lakehouses and SQL endpoints, model, report, ontology, notebooks, Data Agent |
| Agent 365 | Blueprint application/client ID, application object ID, service-principal object ID, template ID, instance ID, agent-user object ID |
| Channels | Agent mailbox/alias, manager, Teams availability, callback FQDN, voice API/SPA registrations and redirect URI |
| Evaluations | Evaluator names/versions, definition IDs, dataset versions/hashes, judge model, run IDs and trace IDs |

Application/client IDs, application object IDs, service-principal object IDs, and
user object IDs are different kinds of identifiers. Never copy a service-principal
object ID from the source tenant. Do not assume two identifiers are equal even if
they happened to be equal for a particular blueprint.

Set shell variables to reviewed target values, not the sample file's old defaults:

```bash
export TARGET_TENANT_ID="<target-tenant-guid>"
export TARGET_SUBSCRIPTION_ID="<target-subscription-guid>"
export TARGET_ENV="hotel-target"
export FOUNDRY_RG="<target-foundry-resource-group>"
export FOUNDRY_ACCOUNT="<target-foundry-account>"
export FOUNDRY_PROJECT="<target-foundry-project>"
export BRIDGE_RG="<target-channel-resource-group>"
export ACR_NAME="<target-registry-name>"
```

Authenticate and verify the effective directory and subscription:

```bash
az login --tenant "$TARGET_TENANT_ID"
az account set --subscription "$TARGET_SUBSCRIPTION_ID"
az account show --query '{tenant:tenantId,subscription:id,user:user.name}'
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd auth login \
  --tenant-id "$TARGET_TENANT_ID"
a365 setup requirements
```

Check `a365 --help` for the installed version's authentication behavior. The
rollout CLI derives its tenant from Azure CLI or explicit `--tenant-id`.
Successful Azure login is not proof of Graph, Fabric, or Power BI consent.

Use Azure CLI for Azure exploration and changes. Use supported Microsoft 365,
Fabric, and Power BI management surfaces for their product-specific configuration.
For interactive steps in a restricted browser session, reuse the existing
authenticated built-in browser tabs. Do not open a new browser process or canvas
to work around a missing session or authorization.

## 3. Obtain administrative and runtime permissions

There are five independent authorization layers: Azure RBAC, Entra/Graph consent,
Agent 365 inheritance, Fabric item/data access, and Work IQ tenant policy. Passing
one layer does not establish the others.

### Administrative authority

| Operator responsibility | Required authority |
|---|---|
| Azure resource deployment | Contributor or narrower deployment permissions on the target resource groups |
| Azure role assignments | Role Based Access Control Administrator, User Access Administrator, or another approved role with assignment authority at the exact scope |
| Blueprint creation/configuration | Agent ID Developer, blueprint ownership, and Agent ID Administrator where required by the supported management operation |
| Tenant-wide delegated consent | Global Administrator for the Agent 365 CLI flow used in this rollout |
| Agent template publication/activation | Appropriate Microsoft 365 agent-registry administrator and available target licenses |
| Fabric workspace/item administration | Workspace Admin for setup, capacity assignment authority where needed, and enabled tenant features |
| Power BI model editing | Model write access, Build where required, and supported XMLA/read-write or Prep for AI access for the chosen operation |
| Agent mailbox delegation | Exchange recipient-management authority, separate from Graph runtime consent |
| Credential creation and vault storage | Blueprint credential-management authority and approved Key Vault secret-write access |

Directory roles and Graph token permissions are separate requirements. For example,
the Graph blueprint APIs document `AgentIdentityBlueprint.Create` for creation,
with additional permissions depending on subsequent operations. Do not assign
every Graph administration scope to the runtime agent. Use the supported CLI or
an approved administrator tool whose token has the permissions required by the
specific management API.

### Runtime identities

| Identity | Target access and purpose |
|---|---|
| Foundry hosted-agent/project identity | Foundry model/runtime access, Search Index Data Reader on the Search service, and Fabric workspace/item access for the actual runtime path |
| Hosted identity for Voice Live | Cognitive Services User on the Foundry account and Foundry User on the project, verified independently of the web proxy |
| Agent 365 instance user | Azure AI Developer on account and project, Cognitive Services User on account, and Fabric workspace Contributor in the validated target configuration |
| Bridge managed identity | AcrPull on its registry and Key Vault Secrets User, or equivalent secret-read access, on the required vault |
| Voice proxy managed identity | AcrPull on the registry and Foundry User on the project. Set `AZURE_CLIENT_ID` to this attached user-assigned identity. |
| Search managed identity | Cognitive Services User for knowledge-base model query planning. Add Cognitive Services OpenAI User only if vectorization is actually configured. |
| Setup/content-loading identity | Search Service Contributor for objects, Search Index Data Contributor for uploads, and Storage Blob Data Contributor only if archiving source blobs |
| Human mailbox operator | Exchange Full Access only when mailbox observation is required. This is not Send As and is not an agent runtime permission. |
| ASSERT runner identity | Only the evaluator-model, telemetry, vault, registry, and restricted artifact-storage access required by the evaluation job |

The reference Fabric workspace used Admin for the operator, Contributor for the
agent user, and Viewer for the hosted principal. Also verify the selected items,
underlying data permissions, and any model Build requirement. A workspace role
alone does not prove every SQL, DAX, ontology, or workload-identity path works.
Do not reduce or broaden these grants without running the affected identity's
real acceptance tests.

Assign roles with the actual principal ID and correct principal type:

```bash
az role assignment create \
  --assignee-object-id "$AGENT_USER_OBJECT_ID" \
  --assignee-principal-type User \
  --role "Azure AI Developer" --scope "$FOUNDRY_PROJECT_ARM_ID"
```

Use `ServicePrincipal` for managed identities. Read back assignments at the exact
scope. Do not add account-wide grants to fix an unexplained project failure.
Record approval and the before/after state for every access change.

## 4. Prepare Azure and Foundry

1. Select the approved existing project, or provision an explicitly approved new
   Foundry account/project with Azure CLI. Enable the required resource providers.
   Verify regional availability and quota for the model, hosted agents, and Voice
   Live. The accepted reference deployment used `gpt-5.4-mini`.
2. Discover the project ARM ID and endpoint from the actual resource. Record the
   account, project, hosted, and Search identities separately. Do not construct
   resource IDs from a guessed subscription or resource group.
3. Reuse approved Search, storage, ACR, App Insights, and Container Apps resources
   where intended. `infra/main.bicep` is an optional dedicated-supporting-resource
   path, not an instruction to create duplicates beside an existing project.
4. Create or select the target channel resource group, user-assigned bridge
   identity, and Key Vault. Configure managed-identity registry pulls and vault
   secret reads. Keep public/key authentication disabled where supported.
5. Review every Bicep parameter. Historical defaults refer to the previous
   environment. Use `az deployment group what-if` before the corresponding
   `az deployment group create`.

Create or select the azd environment without reinitializing this nonempty repository:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env new "$TARGET_ENV"
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set \
  AZURE_SUBSCRIPTION_ID "$TARGET_SUBSCRIPTION_ID" -e "$TARGET_ENV"
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set \
  AZURE_AI_PROJECT_ID "$FOUNDRY_PROJECT_ARM_ID" -e "$TARGET_ENV"
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set \
  AZURE_AI_PROJECT_ENDPOINT "$FOUNDRY_PROJECT_ENDPOINT" -e "$TARGET_ENV"
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd env set \
  FOUNDRY_PROJECT_ENDPOINT "$FOUNDRY_PROJECT_ENDPOINT" -e "$TARGET_ENV"
```

For an existing environment, do not run `env new` again. Populate the remaining
nonsecret values from [`config/azd.env.example`](../config/azd.env.example),
replacing every tenant binding. In particular set the model, Search endpoint,
knowledge-base name, Voice Live endpoint/voice, Fabric workspace/lakehouse/notebook
IDs, Data Agent MCP URL, and Agent 365 bindings. `azure.yaml` is the service wiring
contract. Inspect effective settings privately rather than printing all environment
values into a shared log.

Foundry uses Python 3.13 remote source deployment for this agent. Do not run
`azd init -t` over this repository or require Docker for a source deployment.
See the [hosted-agent documentation](https://learn.microsoft.com/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry).

## 5. Move canonical data and the Fabric estate

### Freeze and validate the source

Export the approved source data and the matching Foundry IQ corpus. Retain a
manifest of file names, row/document counts, and SHA-256 hashes. Do not regenerate
the corpus from a stale root folder or mix one generation of reservation CSVs with
another generation of hotel policies.

Keep stable business identifiers. The reference acceptance fixture is:

| Field | Canonical value |
|---|---|
| Guest | `GST-000001` |
| Reservation | `RES-FAMILY-2026` |
| Property | `HTL-004`, Scottsdale |
| Room type | `HTL-004-RT-03` |
| Stay | September 10-12, 2026, two rooms |
| Business reference date | September 1, 2026 |
| Scottsdale knowledge | Valet USD 25/night, pool 07:00-21:00 |

Map demo mailbox addresses to real provisioned target demo accounts, preserving
guest identity relationships. Never infer the guest from the administrator's UPN.
Preserve strict `check_in` past/future semantics against the configured business
reference date, not the machine's current date.

### Deploy the workspace and data

1. Enable the required Fabric/Data Agent/ontology preview features and applicable
   API access policies. Assign an approved Fabric capacity to the workspace.
   The reference used F16, which is an observed configuration, not a universal
   minimum sizing recommendation.
2. Create or adopt `HotelAgent.Workspace`. Discover existing items before creating
   new ones. There must be exactly two intended lakehouses: `HotelOperations` and
   `HotelGuestServices`.
3. Review [`fabric/topology.json`](../fabric/topology.json) and a private copy of
   [`scripts/fabric/config.example.json`](../scripts/fabric/config.example.json).
   Set the target workspace, canonical source root, authentication mode, and
   private deployment-state path.
4. Validate and inspect the plan before execution:

   ```bash
   .venv/bin/python -m scripts.fabric.cli validate --config "$FABRIC_CONFIG"
   .venv/bin/python -m scripts.fabric.cli plan --config "$FABRIC_CONFIG"
   .venv/bin/python -m scripts.fabric.cli apply --config "$FABRIC_CONFIG"
   ```

   Without `--execute`, `apply` is a dry run. Do not execute the generic plan
   against reviewed native Data Agent configuration or a user-owned semantic
   model. Full-definition replacement cannot prove preservation of native AI
   state. The retained declarative draft also contains a legacy graph datasource,
   which is not the supported ontology-context configuration. Review the exact
   supported artifact operations before adding `--execute`, and use the native
   configuration/publication workflow in Section 6 for the Data Agent.
   Placeholder scripts, a valid legacy draft, and successful local tests are not
   substitutes for a native-preserving deployment path.
   Source `7d45cc9` now refuses requested existing Data Agent or semantic-model
   replacements before any write or deployment-state save. Discovery failure
   also stops execution. There is no bypass flag. New-item creation, unrelated
   non-native updates and read-only dry runs remain supported, but do not
   establish native configuration or acceptance.
5. Upload the reviewed source bundle and fixtures to the correct lakehouse:

   ```bash
   .venv/bin/python scripts/upload_onelake_files.py \
     --source "$CANONICAL_SOURCE_ROOT" \
     --fixtures "$CANONICAL_FIXTURES_FILE" \
     --workspace-name HotelAgent.Workspace \
     --lakehouse-name HotelOperations
   ```

   Review the topology/notebook contract for any additional upload target. A
   successful file upload does not create Delta tables.
6. Bind the load/reset/validation notebooks to the new workspace and lakehouses.
   Run the load notebook, wait for the real job result, and validate row counts,
   primary/foreign keys, duplicate boundaries, fixture identities, and target
   guest addresses. Do not run reset against a populated workspace accidentally.
7. Rebind the limited `ops_` shortcuts in Guest Services to the target Operations
   lakehouse. Do not copy all operational data into a third lakehouse.
8. Deploy the controlled-mutation and aggregate-refresh notebooks. Set the hosted
   runtime's reservation notebook ID to the actual target item. Verify idempotency
   and access under the execution identity before enabling write scenarios.
9. Wait for the SQL endpoints to expose the expected tables and columns. Run SQL
   against both lakehouses, including the exact family reservation fixture.

### Semantic model, report, and ontology

Deploy `HotelOperationsModel` from [`fabric/semantic-model`](../fabric/semantic-model)
with target Direct Lake bindings. Deploy `HotelOperationsReport` from
[`fabric/report`](../fabric/report) and bind it to that target model. Validate
relationships, measures, refresh/framing, and a real DAX query. Preserve intentional
`BLANK()` results for unsupported Food and Beverage Revenue and TRevPAR, rather
than inventing a revenue fact.

Deploy `HotelOperationsOntology` from [`fabric/ontology`](../fabric/ontology) using
the supported V2 definition and target data bindings. The reference V2 artifact
contained 28 definition parts, 10 entity types, 46 properties, and 8 relationships.
Check the full definition and entity/relationship bindings, not only item creation.

Ontology is native context for the Data Agent. It is not a fourth SQL/DAX query
source. Do not repeat the rejected legacy operation that registers ontology as a
normal query data source. Preserve the expected `GuestBookedReservation`
relationship and test whether the production agent actually uses that context.

## 6. Configure and publish the Fabric Data Agent

Create or adopt `HotelOperationsAgent`. Attach the two lakehouse SQL sources and
the semantic model. Native configuration must survive updates and publication.

### Required source-by-source configuration

| Source | Selected schema in the reference rollout | Descriptions, instructions, examples, and Topics |
|---|---|---|
| HotelOperations SQL | 12 tables, 76 columns | Native source description/instructions, every selected table/column described, 11 native SQL examples, real native SQL Topics |
| HotelGuestServices SQL | 29 tables, 273 columns | Native source description/instructions, every selected table/column described, 10 native SQL examples, real native SQL Topics |
| HotelOperationsModel | 9 tables, 41 columns, 21 measures | Model-owned descriptions, AI Schema, Prep for AI instructions, and actual Verified Answers |

For each SQL source:

1. Select only the intended tables/columns and verify target item IDs.
2. Populate its native description, instructions, and complete schema dictionary.
   Explain ownership, join keys, guest/property boundaries, allowed mutations,
   status meanings, and reference-date rules.
3. Save examples in the native example-query collection, not merely as Markdown
   inside instructions. Run every saved SQL example on its actual source.
4. Select the Data Agent's preview runtime, which is required for SQL schema
   object descriptions and Topics. Select the SQL source and open Data source
   topics. Save subject-organized Markdown in that native editor, not in the
   source-instructions field. Test direct and cross-topic questions, then inspect
   the Open Data Source Topic run step's selected heading path and returned
   instructions. Read back the saved configuration after reopening the editor.
   A heading called `Topics` in an ordinary instruction string is not a Topic.
5. Check native ontology context and refresh its target bindings through the
   supported editor.

Semantic models have a different contract. Data Agent source descriptions,
source instructions, native examples, and Topics are not effective semantic-model
NL2DAX configuration. Use the model's supported Power BI Prep for AI route,
AI Schema, AI instructions, and Verified Answers. The reference instructions
contained 11 DAX examples, but this did not prove that NL2DAX consumed them.

Populate ordinary TOM descriptions on every model table, column, and measure.
The full reference model has nine tables, 63 columns, and 21 measures, including
columns outside the Data Agent's selected schema. Preserve approved descriptions
in the canonical model templates so a later deployment does not erase them.
For an existing model, prefer a narrow supported TOM update, such as
`sempy.fabric.create_tom_server(..., readonly=False)` in a Fabric notebook,
changing only missing `Description` properties and calling `Model.SaveChanges()`.
Read back the live model, compare all protected metadata, and run representative
DAX. Do not replace the entire model definition merely to add descriptions,
especially when it contains user-owned Prep for AI state.

The Data Agent REST `/elements.description` property is a user-set override, not
a guaranteed mirror of model TOM descriptions. Schema-object description
overrides are supported for SQL sources. Empty semantic-source element fields
alone do not establish that NL2DAX metadata is stale or that a schema refresh is
required. Verify the live model and real Data Agent answers separately. See
[Schema object descriptions](https://learn.microsoft.com/fabric/data-science/data-agent-schema-object-descriptions)
and the
[published element contract](https://learn.microsoft.com/rest/api/fabric/dataagent/published/list-datasource-elements).

In the Power BI service, open the target model's Prep data for AI experience.
Use Simplify data schema for the AI Schema, Add AI instructions for the model's
business rules, and the supported Verified Answers workflow to save approved
visuals and their trigger questions. Create at least ten reviewed actual Verified
Answers for the intended scenarios, execute them, and read them back from the
model's supported management surface. Include dependent schema objects and avoid
hidden fields that Verified Answers cannot use. Do not fabricate opaque AI
metadata or count instruction text as a Verified Answer.

Do not label unsupported model-specific Topics as configured. Record
`not supported` with the supported model-owned substitute. For SQL Topics or
ontology context that cannot be read back, record `unverified`, not `passed`.

The product contracts are documented in
[Data agent configurations](https://learn.microsoft.com/fabric/data-science/data-agent-configurations),
[SQL Topics](https://learn.microsoft.com/fabric/data-science/data-agent-topics), and
[Semantic model best practices](https://learn.microsoft.com/fabric/data-science/semantic-model-best-practices).
The semantic-model guidance explicitly says that model metadata and Prep for AI
drive DAX generation. General Data Agent instructions still govern cross-source
routing and response presentation, but do not replace model-owned DAX guidance.

### Staging, publication, and evidence

Export the actual draft definition, staging sources, selected schemas, native
examples, and settings. Follow pagination. If definition export returns HTTP 202
with no body, follow the returned operation location to completion and fetch its
`/result`. An empty initial response is not an empty definition.

Bind the reviewed native-readiness evidence to the exact draft digest. Recheck
that digest immediately before publishing. The normal publication notebook must
preserve native configuration and refuse stale or incomplete readiness evidence.
Never write a success-shaped readiness receipt to get past the gate.

The supported public API can publish an existing reviewed staging configuration:

```bash
export FABRIC_AGENT_BASE="https://api.fabric.microsoft.com/v1/workspaces/$FABRIC_WORKSPACE_ID/dataAgents/$FABRIC_DATA_AGENT_ID"

az rest --method post --resource https://api.fabric.microsoft.com \
  --url "$FABRIC_AGENT_BASE/staging/publish" \
  --headers "Content-Type=application/json" \
    "x-ms-fabric-skill=semantic-model-authoring" \
  --body '{"publishedDescription":"Hotel guest services: operations, reservations, guest services, and semantic analytics."}'
```

This is a publication operation, not a native-readiness bypass or an acceptance
test. The reference operator explicitly directed publication of the reviewed,
unchanged staging configuration before every native feature had been accepted.
That left native acceptance incomplete. Do not silently substitute this operation
for the normal release gate.

After publication, read:

```text
GET <agent-base>/staging/datasources
GET <agent-base>/datasources
GET <agent-base>/staging/settings
GET <agent-base>/settings
```

Compare source bindings, selected business elements, descriptions/instructions,
native examples, and stable canonical fingerprints between staging and production.
The reference selected-element totals were 88, 302, and 71 respectively, including
their table/container elements. Keep these separate from column counts.

Set the hosted runtime's production MCP URL to:

```text
https://api.fabric.microsoft.com/v1/mcp/workspaces/<workspace-id>/dataagents/<data-agent-id>/agent
```

Run all seven direct production MCP isolation cases, retaining actual responses:

| Case | Required evidence |
|---|---|
| Folio/minibar dispute | Correct known charge and reservation linkage |
| Official hotel name | Correct official property-name routing |
| Scottsdale services | Correct parking/transport/pool values and source |
| Past reservations | Strict check-in boundary against the business reference date |
| Family reservation | Correct guest, Scottsdale, September 10-12, and two rooms |
| Semantic analytics | Correct completed-stay measure from the model |
| Ontology relationship | Actual expected `GuestBookedReservation` context, not a SQL bridge's unrelated `primary` value |

A created item is not a published item. A published endpoint is not seven passing
cases. Six of seven is not full Data Agent acceptance.

## 7. Rebuild Foundry IQ

Use the frozen canonical Markdown corpus from section 5. Create or adopt:

- `hotel-properties-index`, 20 documents
- `hotel-policies-index`, 15 documents
- `hotel-dining-local-index`, 20 documents
- `hotel-operations-index`, 40 documents

The total is 95 source-matched documents, one corresponding knowledge source per
index, and the `hotel-foundryiq` knowledge base. Verify counts, document IDs,
source paths, and content hashes, not just index existence.

Configure Search and model access from section 3. The accepted target used
semantic lexical retrieval with the existing chat deployment. Do not add an
embedding deployment or vectorization role unless choosing a reviewed vector
architecture. Blob archival is optional and requires both
`FOUNDRY_IQ_BLOB_CONTAINER` and `AZURE_STORAGE_ACCOUNT_URL`.

After setting the target environment and reviewed source paths:

```bash
.venv/bin/python scripts/setup_foundry_iq.py --dry-run
.venv/bin/python scripts/setup_foundry_iq.py
```

Inspect the script's effective corpus before execution. Never use successful
setup as a reason to overwrite target knowledge with a stale generated folder.
Run direct hotel/property/date-specific knowledge queries, including Scottsdale
valet USD 25/night and pool 07:00-21:00. Verify citations identify actual retrieved
content. Apply the same checks to non-Scottsdale properties so a hardcoded answer
cannot pass.

## 8. Create the Agent 365 blueprint and permissions

Read [`a365/README.md`](../a365/README.md) and review the permission matrix against
this section. Create a tenant-local single-tenant blueprint, not a copy of the
source application's object IDs:

```bash
a365 setup blueprint --agent-name hotel-agent-bridge \
  --tenant-id "$TARGET_TENANT_ID" --no-endpoint
```

Do not run this again if the intended blueprint already exists. Discover it and
use its generated private configuration. Keep `AzureADMyOrg`. Do not broaden its
audience to repair a missing owner, endpoint, or grant.

### Complete permission matrix

The full-feature reference blueprint has ten delegated resource grants: Microsoft
Graph plus nine other audiences. This is the reviewed feature baseline, not a
recommendation to grant this breadth to unrelated agents. A smaller feature set
requires an explicitly reviewed matrix and corresponding acceptance tests.

Microsoft Graph resource application ID:
`00000003-0000-0000-c000-000000000000`.
Its 29 delegated scopes are:

```text
BookingsAppointment.ReadWrite.All
Calendars.ReadWrite
Channel.ReadBasic.All
ChannelMember.Read.All
ChannelMessage.Read.All
Chat.ReadWrite
ChatMessage.Send
Contacts.ReadWrite
Directory.Read.All
Files.Read.All
Group.Read.All
Mail.ReadWrite
Mail.Send
MailboxSettings.ReadWrite
Notes.Read.All
OnlineMeetingTranscript.Read.All
OnlineMeetings.ReadWrite
People.Read.All
Place.Read.All
Presence.Read.All
Sites.Read.All
Tasks.ReadWrite
Tasks.ReadWrite.Shared
Team.ReadBasic.All
TeamMember.Read.All
User.Read
User.Read.All
Files.ReadWrite.All
ChannelMessage.Send
```

| Resource | Application ID | Delegated scopes |
|---|---|---|
| Power Platform API | `8578e004-a5c6-46e7-913e-12f58912df43` | `Connectivity.Connections.Read` |
| Messaging Bot API | `5a807f24-c9de-44ee-a3a7-329e88a00ffc` | `AgentData.ReadWrite` |
| Agent365Observability | `9b975845-388f-4429-889e-eab1ef63949c` | `Agent365.Observability.OtelWrite` |
| Agent Tools | `ea9ffc3e-8a23-4a7d-836d-234d7c7565c1` | `McpServers.Mail.All`, `McpServers.Teams.All`, `McpServersMetadata.Read.All` |
| Work IQ Copilot MCP | `ab7c82de-7946-4454-ac28-70249d17c95e` | `Tools.ListInvoke.All` |
| Work IQ Mail MCP | `16b1878d-62c7-4009-aa25-68989d63bbad` | `Tools.ListInvoke.All` |
| Work IQ Teams MCP | `ce5029ee-c1d3-45c0-bdcc-efb5a4245687` | `Tools.ListInvoke.All` |
| Microsoft Cognitive Services | `7d312290-28c8-473c-a0ed-8e53749b6d6d` | `user_impersonation` |
| Azure Machine Learning Services | `18a66f5f-dbdf-4c17-9dd7-1634712a9cbe` | `user_impersonation` |

The Observability resource also has one application-role assignment:
`Agent365.Observability.OtelWrite`. Do not turn the delegated Graph scopes into
application permissions.

### Grant, inherit, and read back

1. Resolve the blueprint service principal and each resource service principal in
   the target tenant by application ID. Verify exposed scope values and the
   Observability application's enabled role ID. Fail if a required resource or
   permission is absent, rather than silently skipping it.
2. Configure required-resource declarations and tenant-wide administrator consent.
   Agent 365 CLI offers `setup permissions mcp`, `setup permissions bot`, and
   `setup permissions custom`. Inspect their dry run and reconcile the complete
   matrix after execution. For example:

   ```bash
   a365 setup permissions custom --agent-name hotel-agent-bridge \
     --tenant-id "$TARGET_TENANT_ID" \
     --resource-app-id 7d312290-28c8-473c-a0ed-8e53749b6d6d \
     --scopes user_impersonation
   ```

3. Each tenant-wide `oauth2PermissionGrant` uses the blueprint service-principal
   object ID as `clientId`, the target resource service-principal object ID as
   `resourceId`, `consentType: AllPrincipals`, `principalId: null`, and the reviewed
   space-delimited scope set. Read back actual grants, not just application
   declarations or an administrator's successful consent page.
4. Assign the Observability application role using its actual target role ID.
5. Create a matching blueprint inheritable-permission entry for every resource.
   The reference contract uses `allAllowed` for scopes and roles:

   ```json
   {
     "resourceAppId": "<resource-application-id>",
     "inheritableScopes": {
       "@odata.type": "microsoft.graph.allAllowedScopes",
       "kind": "allAllowed"
     },
     "inheritableRoles": {
       "@odata.type": "microsoft.graph.allAllowedRoles",
       "kind": "allAllowed"
     }
   }
   ```

   Use the supported Graph API for the installed Agent ID version. The rollout
   used `/beta/applications/<blueprint-object-id>/microsoft.graph.agentIdentityBlueprint/inheritablePermissions`.
   `allAllowed` does not itself grant consent, and changes to the blueprint's
   grants change what can be inherited. Review that trust boundary.
6. Verify all ten actual delegated grants, all ten inheritance entries, and the
   single application-role assignment before creating the instance.

Do not add an optional Microsoft 365 AppCatalogServices catalog-manager assignment
by default. It was not required in the target rollout. Do not assume later
inheritance additions repair an already-created instance retroactively.

See Microsoft's [inheritable-permission API](https://learn.microsoft.com/graph/api/agentidentityblueprint-post-inheritablepermissions?view=graph-rest-beta)
and [blueprint creation API](https://learn.microsoft.com/graph/api/agentidentityblueprint-post?view=graph-rest-1.0).
Preview contracts can change, so confirm the operation's permissions and payload
against the installed CLI and current API documentation.

### Credential custody

Reuse a valid existing blueprint credential when adopting an environment. Do not
rotate it as a side effect of setup. For an explicitly authorized new credential,
use approved tooling that transfers the one-time returned value directly from
Graph into Key Vault in memory. Do not use a command that prints the value, puts it
in a shell argument, saves it in a temporary file, or logs the full Graph response.

Store it as `agent365-blueprint-client-secret`. Store the telemetry connection
string separately if the bridge requires it. Record only nonsecret key IDs,
expiration, secret URI/version, owner, and renewal procedure. Grant the bridge's
managed identity read access to those secrets. Verify credential validity before
deployment and plan renewal before expiry. Generated CLI configuration containing
credentials stays private and out of Git.

## 9. Deploy the messaging bridge

Use the reviewed Container Apps implementation from section 1. Do not deploy the
historical App Service template by assuming it has Container Apps parameters.
Read [`agent/README.md`](../agent/README.md) for SDK and authentication details,
but replace historical resource names and revision receipts.

1. Configure the target tenant, blueprint client ID, Foundry endpoint/agent/model,
   managed-identity client ID, Messaging Bot connection, and Agentic authorization.
   Point secret references at the target Key Vault, not plaintext environment
   values.
2. Ensure `FOUNDRY_USER_TOKEN_SCOPES=https://ai.azure.com/.default`.
   Pass the exchanged agent-user bearer directly to Foundry. There is no supported
   header-only impersonation substitute.
3. Preserve the SDK's required `productInfo` compatibility handling and tested
   message-reference behavior. The EmailReference SDK used in the rollout exposes
   `type`, `id`, `conversation_id`, and `html_body`, not a reliable sender/subject.
   Fetch exact message metadata through Work IQ using the reference. Never invent
   missing fields or substitute the operator's identity. In the reviewed hosted
   implementation, the exposed Work IQ tool is `query_work_context`. Explicitly
   request that exact-message read before resolving the guest and querying their
   reservation. A guest signature is not verified sender metadata.
4. The email prompt must forbid send/reply/forward operations by the hosted agent,
   require actual hotel and reservation retrieval before facts, and request only
   the guest-facing reply in the guest's language. The bridge owns delivery.
   Keep notification invocations stateless. Never key their hosted history by
   the transport sender ID, which can be the same across unrelated guests and
   email threads. A notification must neither inherit nor alter ordinary Teams
   history, including on failure. Test different email conversation IDs sharing
   one transport sender, and confirm ordinary Teams turns retain their history.
5. Build from the `agent` directory, which is the bridge's container build context:

   ```bash
   export BRIDGE_IMAGE_TAG="<immutable-release-tag>"
   (
     cd agent &&
     az acr build --registry "$ACR_NAME" \
       --image "hotel-agent-bridge:$BRIDGE_IMAGE_TAG" \
       --file Dockerfile .
   )
   ```

6. Deploy the reviewed `infra/agent365-bridge.bicep` with a private parameter file
   containing nonsecret target IDs and Key Vault secret URIs:

   ```bash
   az deployment group what-if --resource-group "$BRIDGE_RG" \
     --template-file infra/agent365-bridge.bicep \
     --parameters @"$BRIDGE_PARAMETERS_FILE"
   az deployment group create --resource-group "$BRIDGE_RG" \
     --template-file infra/agent365-bridge.bicep \
     --parameters @"$BRIDGE_PARAMETERS_FILE"
   ```

7. Read back the Container App's actual FQDN, image digest, revision health, running
   status, ready revision, and traffic. Require the intended revision to receive
   100% of traffic before interpreting a channel test as evidence of the fix.
   Retain the previous revision/image for rollback.
8. Reconcile the intended messaging registration. If the selected channel
   architecture includes Azure Bot Service, review and deploy its target
   parameters with
   [`infra/agent365/bot-service.bicep`](../infra/agent365/bot-service.bicep).
   Preserve public network access where the Teams channel requires it. This
   legacy template does not by itself configure the Agent 365 API Based callback.
   Do not add a separate bot to an API Based architecture or create a duplicate
   as a workaround for Agent 365 routing.
9. Register the actual HTTPS `<bridge-fqdn>/api/messages` callback on the owned
   blueprint. Use the supported endpoint-only CLI flow or the Teams developer
   blueprint configuration page. The installed CLI provides:

   ```bash
   a365 setup blueprint --agent-name hotel-agent-bridge \
     --tenant-id "$TARGET_TENANT_ID" --endpoint-only \
     --messaging-endpoint "$BRIDGE_MESSAGES_URL"
   ```

Read back the API Based notification endpoint. A healthy bridge does not prove the
blueprint routes messages to it.

## 10. Publish the template and create the instance

### Package and registry

Review [`manifest/README.md`](../manifest/README.md). Replace all tenant-specific
manifest values and increment the package version. Ensure:

- `manifest.json.id` equals the template manifest's `agentIdentityBlueprintId`.
- `manifest.json.agenticUserTemplates[0].id` equals the template manifest's `id`.
- Blueprint, template, instance, and agent user remain distinct recorded objects.

Build a ZIP with exactly these four root entries:
`manifest.json`, `agenticUserTemplateManifest.json`, `color.png`, and `outline.png`.
`a365 publish --dry-run` can inspect packaging changes, but a generated ZIP is not
publication evidence.

In Microsoft 365 admin center:

1. Open Agents > All agents > Registry > Add agent. On a narrow window, Add agent
   can be under More actions.
2. Upload the package as an agent template, not through Integrated apps' ordinary
   custom-app upload.
3. Select the approved publication and activation audience and the agent-template
   policy. The reference used All users with the default template policy, but this
   is an administrator's explicit exposure decision, not a universal default.
4. Complete publication and any separate activation wizard.
5. Reopen the registry item. Verify type Agent template, the target blueprint
   Entra agent ID, package version, audience, policy, and status Available.

Retain an independent registry readback. The source package and a successful
upload wizard do not prove the final published catalog entry is correct.

### Instance, mailbox, and access

After the complete grant/inheritance matrix is verified, use Add instance. Choose
the approved display name, alias `hotelguestservices`, human owner/reports-to user,
and licensing. The reference instance display name is
`Lyrenza Hotel Guest Services`, while the reusable template remains generic.

Record the actual instance identity and agent-user object IDs. Verify the enabled
instance, manager, mailbox/UPN, license, and Teams availability. If an instance
request is created by a nonadministrator through the store, approve that request
through the supported registry workflow.

Assign the agent user the Foundry and Fabric runtime permissions from section 3.
Grant optional human mailbox Full Access separately. Do not add Send As or Send
on behalf merely to let an operator observe replies.

For Fabric workspace assignment, the supported payload for this target setup is:

```json
{
  "principal": {
    "id": "<agent-user-object-id>",
    "type": "User"
  },
  "role": "Contributor"
}
```

Post it to `/v1/workspaces/<workspace-id>/roleAssignments` using an authorized
Fabric administrator, then read it back. Never assume a successful administrator
query proves the agent user has permission.

In Microsoft 365 admin center, open Agents > Tools > Work IQ MCP > Policies.
Enable Allow write actions and only the create/update/delete capabilities approved
for the solution. Use the generic Work IQ MCP entry, not an individual preview
server. This tenant mutation policy is independent of OAuth consent, mailbox
licensing, and the runtime tool allowlist. Refresh long-running hosts' cached
authentication after policy changes.

If an instance was created before its blueprint was fully configured, first
diagnose actual token and routing failures. If a replacement is required, create
and accept the replacement before requesting deletion of the old instance.

## 11. Deploy and verify the hosted agent

Complete the actual target bindings in `azure.yaml` and the selected azd
environment. In particular:

- Use the production Fabric MCP URL, not a staging or source-tenant URL.
- Use the target Search endpoint and reviewed `hotel-foundryiq` knowledge base.
- Set the target Agent 365 instance/blueprint/vault references.
- Bind the reservation notebook to the target Guest Services lakehouse.
- Preserve Responses `2.0.0` and `invocations_ws` `1.0.0`.
- Preserve the provenance guard and sequential model tool calls.

Run `make check`, including technical-name validation, on the release checkout.
Deploy and read back the actual active version:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd deploy \
  hotel-servicing-agent -e "$TARGET_ENV" --no-prompt
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd ai agent show \
  hotel-servicing-agent -e "$TARGET_ENV"
```

Record the returned version, identity, creation time, status, code/build receipt,
protocols, and effective bindings. Set `HOSTED_VERSION` to that returned version,
not the source tenant's version number.

Invoke a fresh conversation explicitly against it:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd ai agent invoke \
  hotel-servicing-agent \
  "For the canonical family guest, confirm the upcoming reservation and the valet price at that hotel." \
  --protocol responses --version "$HOSTED_VERSION" \
  --new-session --new-conversation -e "$TARGET_ENV"
```

Do not combine `--agent-endpoint` with the positional agent name or `--protocol`.
Do not assume `invoke` supports `--output json`.

Run the exact guest identity wording used by the frozen acceptance dataset, plus
an unknown-guest negative control. For the reference fixture, require Scottsdale,
September 10-12, 2026, and USD 25/night. For the unknown guest, require an honest
inability to confirm the reservation/property/price.

Inspect real App Insights tool spans, not just plausible answer text:

1. Fabric completes successfully and actually returns `HTL-004`.
2. Only afterward, IQ starts with the retrieved property ID and supported
   reservation provenance.
3. IQ succeeds and supplies the actual Scottsdale facts and citations.
4. The answer uses both sources without inventing reservation or policy details.

Instructions alone did not prevent parallel dependent tool calls in the rollout.
The v7 runtime fix set `allow_multiple_tool_calls=False`, which the framework
translated to the Responses API's `parallel_tool_calls: false`. Test the actual
client request serialization. Do not disable intentional parallel work inside an
independent tool merely because model-level dependent calls must be sequential.

Use time-bounded telemetry queries and keep their text and results with the
private release evidence. Avoid logging tokens or full guest mail content.

## 12. Recreate evaluator assets and run evaluations

Remote evaluator, definition, dataset, and run IDs are project-local. Export the
reviewed rubric dimensions, weights, applicability, thresholds, and canonical
inputs. Recreate assets in the target project instead of copying source IDs.

Follow [`docs/foundry-evaluator-rubrics.md`](foundry-evaluator-rubrics.md):

1. Create a rubric generation job with the final evaluator resource name and
   display name, then wait for success. This establishes the catalog parent.
2. Create the reviewed hand-edited version while preserving the always-applicable
   `general_quality` dimension. The Hotel rubric has 13 dimensions, weight tiers
   10/6/3, and threshold 0.68.
3. Verify both custom evaluator catalog listing and version listing. A successful
   exact-version GET can refer to an orphan invisible in the catalog.
4. Recreate the language evaluator and the Hotel/language evaluation definitions,
   datasets, and explicit target-version bindings.
5. Save verified target references in the appropriate private
   `src/hotel-servicing-agent/.foundry/agent-metadata.<environment>.yaml` overlay.
   Keep azd-owned deployment values in azd rather than duplicating them.
6. Run the original eight-case knowledge/language batch once on the selected
   deployed version, with unchanged input hashes, rubrics, and thresholds.
   Retain every response, rubric score, verdict, run ID, and trace correlation.
7. Report language, primary Hotel rubric, strict combined checks, and definition
   aggregate separately. Inapplicable definition graders can make the aggregate
   misleading. Do not rename a primary-rubric result as an aggregate pass.

Preserve earlier failures and inconsistent judge results. Do not edit the rubric,
retry individual cases, or rerun batches until green without recording the reason
and the original evidence.

For agent-user ASSERT testing, follow
[`docs/assert-evaluation.md`](assert-evaluation.md) and
[`infra/evaluation/assert-job.bicep`](../infra/evaluation/assert-job.bicep).
The loopback-only Entra Auth sidecar supplies the real agent-user token. The
runner's workload identity is separate and must not impersonate the target via
an unsigned header, developer credential, or managed-identity fallback. Require
the no-content Work IQ authentication checks, all 12 conversation cases, zero
weight-10 failures, score at least 0.68, and complete trace correlation.

## 13. Accept Teams and email

### Teams

Send a real Teams DM to the provisioned instance from its approved manager.
Bot Web Chat and Direct Line do not supply the same Agent 365 user context.
Verify both channel delivery and Foundry telemetry.

Test a knowledge-only question, the reservation-to-property-to-IQ question,
supported language behavior, and an unknown-guest control. Confirm the answering
identity is the actual instance, not a similarly named template or old bot.
Require real tools and source citations where the scenario needs them.

### Email

Use the actual provisioned demo guest mailbox. Address the actual agent mailbox
and resolve the operator Cc to a real recipient chip. A compose window or Drafts
entry is not a sent message.

For Spanish, French, Arabic, and Chinese:

1. Send one uniquely identifiable knowledge-only request from the guest.
2. Confirm its Sent Items entry and actual original To/Cc headers.
3. Wait for and open the real reply. Confirm exactly one delivered reply, not two
   senders or a summary plus a separate answer.
4. Inspect the reply's actual To and Cc headers. The original Cc alone does not
   prove Reply all or operator inclusion.
5. Require a guest-facing answer entirely in the requested language, Scottsdale
   valet USD 25/night, pool 07:00-21:00, and source grounding.
6. Reject action summaries such as "I replied in Spanish and copied the operator."
   That is not the guest-facing response.
7. Run a separate reservation-grounded email after the current hosted version's
   Fabric-to-IQ positive test passes. Confirm the real sender resolves to the
   canonical guest and the answer combines reservation and property knowledge.

Retain per-language message references, times, reply counts, header readback,
deployed bridge revision, hosted version, and relevant traces privately. Do not
relabel an older-version channel test as a newer-version result.

## 14. Deploy and accept voice

### Registrations and identity

Create a target single-tenant API registration and SPA registration:

- The API exposes delegated `HotelAgent.Access`.
- Its access-token version is 2. The API audience is its application client-ID
  GUID, while the scope URI is `api://<api-client-id>/HotelAgent.Access`.
- The SPA requests that exact delegated scope. Do not add a SPA client secret.
- Register the deployed origin's exact `/redirect.html` as an SPA redirect URI.
  Local development uses `http://localhost:5173/redirect.html`.
- Use the operator's approved delegated consent where permitted. Do not replace
  this with a CLI client's grant or tenant-wide consent as a shortcut.

For an approved operator-only grant, resolve the SPA and API service-principal
object IDs with `az ad sp show --id <application-client-id> --query id`. Resolve
the approved operator's user object ID separately. Read existing
`/v1.0/oauth2PermissionGrants` before creating anything. An authorized administrator
can create the specifically approved missing grant with Azure CLI:

```bash
az rest --method post \
  --url https://graph.microsoft.com/v1.0/oauth2PermissionGrants \
  --body '{
    "clientId": "<SPA-service-principal-object-id>",
    "consentType": "Principal",
    "principalId": "<approved-operator-user-object-id>",
    "resourceId": "<API-service-principal-object-id>",
    "scope": "HotelAgent.Access"
  }'
```

`clientId` and `resourceId` here are service-principal object IDs, not application
client IDs. Read the resulting grant back and verify all five fields. Do not
change it to `AllPrincipals`, add scopes, or create a duplicate grant. Persisted
consent alone does not prove that the browser can authenticate.

Attach the dedicated user-assigned proxy identity, grant its registry AcrPull and
project-scoped Foundry User access, and set `AZURE_CLIENT_ID`. The hosted identity
separately requires the inner Voice Live permissions in section 3.

### Build and deploy

Use the reviewed voice template. Override all registry, project, and environment
defaults. For a shared existing Container Apps environment, the reviewed template
must support `createManagedEnvironment=false`, the existing environment's name,
and its resource group. Do not modify a shared environment by accident.

```bash
export VOICE_IMAGE_TAG="<immutable-release-tag>"

az acr build --registry "$ACR_NAME" \
  --image "hotel-voice-proxy:$VOICE_IMAGE_TAG" \
  --file web/backend/Dockerfile \
  --build-arg VITE_ENTRA_CLIENT_ID="$VOICE_SPA_CLIENT_ID" \
  --build-arg VITE_ENTRA_AUTHORITY="https://login.microsoftonline.com/$TARGET_TENANT_ID" \
  --build-arg VITE_ENTRA_REDIRECT_URI=auto \
  --build-arg VITE_ENTRA_API_SCOPE="api://$VOICE_API_CLIENT_ID/HotelAgent.Access" \
  .

az deployment group what-if --resource-group "$BRIDGE_RG" \
  --template-file infra/voice-web.bicep \
  --parameters @"$VOICE_PARAMETERS_FILE"
az deployment group create --resource-group "$BRIDGE_RG" \
  --template-file infra/voice-web.bicep \
  --parameters @"$VOICE_PARAMETERS_FILE"
```

The parameter file must bind the image, tenant, API client ID, target registry,
Foundry project endpoint/agent, identity, and environment strategy supported by
the reviewed template. Frontend `VITE_ENTRA_*` values are public build-time
configuration, not secret storage.

Read back image digest, ready revision, health, and 100% traffic. Startup must
successfully obtain a `https://ai.azure.com/.default` token before health succeeds.

For an application-only update, build from a source-only context that preserves
the Dockerfile's `web/` layout. Exclude local environment files, private `.foundry`
receipts, dependency caches, and unrelated worktree artifacts. After validation,
update only the existing app image:

```bash
az containerapp update --name hotel-voice-proxy --resource-group "$BRIDGE_RG" \
  --image "<registry>/hotel-voice-proxy@sha256:<verified-digest>"

az containerapp ingress sticky-sessions set \
  --name hotel-voice-proxy --resource-group "$BRIDGE_RG" --affinity sticky
```

Do not reapply infrastructure or change roles just to ship frontend code.

### Authentication and audio acceptance

The supported flow is:

```text
SPA Entra sign-in
  -> POST /api/auth/session with bearer
  -> short-lived opaque session handle
  -> /api/calls WebSocket, authenticated in its first frame
  -> proxy managed identity
  -> Foundry invocations_ws
  -> hosted agent / Voice Live
```

Never put raw browser or Foundry bearer tokens in a WebSocket URL. Production
must not fall back to scripted/offline playback after an authentication or network
error. `/api/config` contains public configuration, and `/api/health` is not
authenticated end-to-end voice acceptance.

The reviewed frontend keeps tokens in MSAL `memoryStorage`. Ordinary sign-in uses
a popup. Where popups are unavailable, its explicit **Use existing Microsoft
session** action passes the entered hotel account email as `loginHint` to
`ssoSilent`. It requires an existing Entra browser session, approved API consent,
and usable IdP session cookies. It never falls back to a popup. In this mode,
sign-out clears only local app authentication, not the shared Microsoft session.
Token renewal requiring interaction surfaces a reconnect error.

Do not replace this with full-page MSAL redirect sign-in while retaining
`memoryStorage`. That combination is unsupported. `AADSTS50058` means silent
sign-in did not receive a usable IdP session.

The separate **Sign in in this tab** action uses `oidc-client-ts` Authorization
Code + PKCE, not MSAL redirect authentication. Add the exact owned origin plus
`/` to the existing application's SPA redirect URIs, preserving `/redirect.html`.
The new flow uses `response_type=code`, `response_mode=fragment`, `openid profile`
and the existing API scope. It requests no offline-access scope or client secret.
Only short-lived PKCE request state uses session storage. User records and all
tokens use `InMemoryWebStorage`. The callback removes authorization parameters
from the URL before processing, and the library rejects unknown state.
Reloading loses authentication. Expired tokens require another interactive
sign-in. Sign-out clears local app authentication, not other Microsoft sessions.
The root callback stays in the app even if the original tab has an opener.
MSAL popup and silent flows continue to use their dedicated `/redirect.html`
bridge, not the root callback.

Record the actual browser result. Do not weaken token storage, alter browser
cookie policy, borrow a CLI bearer, or claim authentication from consent,
registered redirects, a successful image deployment, or health alone.

With the required `{"clientContext":"web"}` JSON request body, verify
missing/invalid browser tokens return HTTP 401. An invalid client context returns
HTTP 400 before token validation. Verify invalid WebSocket
handles produce an authentication error and policy close, not a live session.
Then sign in with the real approved SPA user and require authenticated session
creation, a successful WebSocket, final user transcript, final agent transcript,
and audible synthesized audio.

Bind the WebSocket auth frame's `opaqueHandle` and `agentSessionId` to the same
session-creation response. Never combine a new handle with an ended call's
session ID. Reconnects retain their own call's matching pair. Starting a new
call must cancel old retries and clear prior guest data from the UI.
Test a text call, End call, then a prerecorded call without reloading between
them. A successful first call alone does not cover this lifecycle regression.

The proxy's opaque-handle store is process-local. The reviewed template enables
supported session affinity in single-revision HTTP mode, so session creation
and WebSocket requests return to the same replica. The platform routing cookie
is not an authentication token or the browser-session handle. Run one Python
process per replica. Multiple application workers need shared state, and a
replica restart loses its handles. Affected calls need a fresh session.
One successful single-replica run does not establish multi-replica load behavior. See
[Container Apps session affinity](https://learn.microsoft.com/azure/container-apps/sticky-sessions).

For direct hosted-agent audio testing:

```bash
.venv/bin/python scripts/run_voice_smoke.py "$PCM_WAV_FILE" \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT" --expect-activity
```

Use mono, 16-bit, 24 kHz PCM for the direct harness. Choose a prompt that genuinely
requires a tool when using `--expect-activity`. Also test the deployed browser
path, because a developer-credential direct harness does not prove SPA/proxy
authorization.

Verify welcome audio, transcription, hotel/reservation grounding, multilingual
response, barge-in, echo handling, and failure handling. The reference voice is
`en-US-AvaMultilingualNeural`. Confirm both hosted protocols exist before routing
voice traffic. Pin only an actually tested target version where supported, never
the previous tenant's version number.

## 15. Complete the release evidence and rollback plan

Keep a private release receipt with the following independent gates:

| Gate | Required evidence |
|---|---|
| Code | Reviewed commit, dependency locks, passing checks, identical instructions |
| Azure | Effective target IDs, identities, exact scoped roles, image digests |
| Fabric data | Source hashes, row/key/fixture validation, SQL and DAX results |
| Native Data Agent | Per-source schema/descriptions/instructions/examples, actual SQL Topics, model AI configuration, actual ontology context |
| Publication | Exact draft digest, stable staging/production fingerprints, seven production MCP cases |
| Foundry IQ | 95 matched documents, actual property retrieval and citations |
| Hosted agent | Active version/protocols, positive and negative controls, actual sequential tool traces |
| Agent 365 | Blueprint grants/inheritance, registry template readback, enabled instance/user/mailbox |
| Evaluations | Immutable inputs/rubrics, actual run results and all trace IDs |
| Teams/email | Actual delivered messages, language/content, single reply, actual reply To/Cc, reservation grounding |
| Voice | SPA authentication, session/WebSocket authorization, transcripts, real audio and backend activity |

Do not mark an unavailable feature as passed. Record whether it is unsupported,
unverified, failed, or explicitly out of scope. An instruction string is not
native configuration, and a saved JSON file is not independent live readback.

Before cutover, export current definitions, settings, source fingerprints,
resource parameter values, template package version, image digests, hosted
versions, and channel routing. Preserve the old working environment while the new
one is accepted. Avoid changing source routing during a target-only test.

Rollback the smallest affected layer: restore the previous healthy channel image
and traffic, restore a known accepted hosted version/route, or restore the exact
reviewed Fabric definition and republish. Recheck downstream bindings after every
rollback. Never delete or recreate the whole workspace, blueprint, mailbox, or
resource group as a troubleshooting shortcut. Revoke only specifically approved
obsolete grants/credentials after replacement acceptance and an explicit cleanup
decision.

## 16. Troubleshooting

| Symptom | Check before changing anything |
|---|---|
| Teams silent, no Foundry trace | Blueprint callback, template activation, actual instance/user, complete grant/inheritance matrix, real manager DM |
| Work IQ tools listed but writes denied | Generic Work IQ MCP mutation policy, actual resource consent, cached pre-policy tokens, runtime allowlist |
| Foundry OBO authorization failure | Both Cognitive Services and Azure ML `user_impersonation` grants and inheritance, agent-user account/project roles, actual bearer audience |
| Fabric "Failed to get publish info" | Real production publication, not just a draft definition or saved notebook |
| Fabric metadata disappears | A redeploy replaced native sources. Restore reviewed settings and adopt/preserve rather than overwrite. |
| Wrong property or valet price | Guest resolution, canonical source bundle, actual Fabric property evidence, IQ property filter, returned source content |
| Reservation found but policy unavailable | Dependent Fabric/IQ calls ran in parallel. Inspect actual tool timestamps and serialized `parallel_tool_calls`. |
| Two email replies | Both Work IQ and bridge are sending. Restore one delivery owner and verify actual inbox counts. |
| Reply is an action summary | Email final-answer prompt is wrong. Require only guest-facing text and grounded facts. |
| Email remains in Drafts | Unresolved recipient chips or Send did not complete. Verify Sent Items before retrying. |
| Semantic source instructions appear saved but DAX ignores them | Use model-owned Prep for AI/AI Schema/Verified Answers, not Data Agent SQL-source settings |
| Ontology question answered with SQL `primary` | Native ontology context is not accepted. Do not weaken the expected relationship assertion. |
| Evaluator GET works but catalog is empty | Orphaned direct-created version. Create the evaluator catalog parent through generation, then the reviewed version. |
| Voice HTTP 400 during handshake | Target version still exposes `invocations_ws`, correct route/protocol, no source-tenant version pin |
| Voice health passes but sign-in/call fails | SPA redirect/scope/audience/consent, authenticated session, proxy identity versus hosted identity |
| Azure/Graph/Fabric HTTP 403 | Identify the failing plane and principal. Do not solve it by adding unrelated broad roles. |
| Definition export HTTP 202, empty body | Follow the operation location, wait for success, then fetch its result |

Check immediately after a permission change and use bounded retries. Do not call
an unexplained failure "propagation" indefinitely. Retain the actual error,
effective identity, endpoint, and trace before changing the next layer.

## 17. Verified rollout status and remaining work

The reference rollout as of October 27, 2026 established:

- Hosted version 7 was active. Its exact family-reservation-to-Scottsdale-valet
  test passed, with successful sequential Fabric then IQ tool spans. An unknown
  guest control declined to invent the property, dates, or price.
- The original eight-case v7 batch passed language 8/8, primary Hotel rubric 8/8,
  and strict combined checks 8/8. The Hotel definition aggregate was 0/8 because
  of inapplicable graders. It remained a separate reported result, not an
  aggregate pass.
- The Fabric Data Agent was actually published with matching native source
  fingerprints. Six of seven production MCP isolation cases passed. The ontology
  relationship case failed and remained recorded as a failure.
- The v6 knowledge-only email batch produced one correct-language reply each in
  Spanish, French, Arabic, and Chinese with the expected Scottsdale facts.
  This was v6 evidence, not v7 channel acceptance.
- A subsequent narrow TOM repair populated all nine table and 63 column
  descriptions, preserving all 21 existing measure descriptions/formulas and
  other model metadata. A published Data Agent question correctly explained the
  booking-pace date and booked-revenue semantics. This did not establish
  `/elements.description` propagation or complete model-owned Prep for AI.
- Source preservation commit `3c99302` subsequently retained the 72 approved
  table/column descriptions and three inherited measure descriptions in the
  canonical templates, with all other table bytes preserved. Its self-contained
  candidate passed 34 tests, including exact template-setting preservation for
  both Q&A flag values. The dirty Q&A toggle was not promoted. Existing semantic
  model replacement now fails before any definition request/write because an
  export cannot prove preservation of opaque or unexported user-owned AI state.
  Use supported field-level TOM with preservation verification or Power BI
  tooling for existing models. This source commit made no additional live-model
  change and did not configure Prep for AI.
- The initial v7 reservation email received a safe refusal without any tool calls. Its
  input exposed history shared across eight distinct email threads. Bridge
  `em4` added stateless notification turns and an explicit exact-message Work IQ
  read instruction. A fresh 7c email then produced exactly one correct delivered
  reply. Its actual trace showed one initial input, exact-message sender retrieval,
  the matching Fabric reservation, and property-specific IQ retrieval. This
  verifies the reservation-email repair, but not the outgoing reply To/Cc headers.
- The approved operator-only voice SPA grant was persisted and read back.
  Voice frontend revision `sso1` was deployed healthy with all traffic. Actual
  existing-tab silent sign-in returned `AADSTS50058`, with no authenticated API,
  WebSocket, or audio acceptance reached. The deployment did not change hosted
  version 7 or bridge `em4`, and it did not weaken memory-only token storage.
- A separate direct v7 prerecorded-audio test initially failed at the inner
  Voice Live handshake with HTTP 401. The actual hosted identity then received
  the documented account-scoped Cognitive Services User and project-scoped
  Foundry User assignments after the user's renewed instruction to proceed.
  Independent role readback confirmed both grants. A fresh direct session
  `hotel2701-voice-acceptance-20261027b` returned `auth_ack`, the actual Maria ASR,
  correct Scottsdale reservation dates and USD 25 valet answer, and 1,120,800
  output audio bytes. This establishes direct hosted voice, not browser SPA/proxy
  authentication, browser audio playback, or a separately traced IQ call.
- Same-tab PKCE frontend revision `pkce2` was subsequently deployed Healthy,
  Running, and receiving all traffic. Both same-origin SPA redirects were read
  back. The live bundle contains the correct tenant, application and API scope.
  The existing-tab authenticated browser acceptance remained pending at this
  deployment checkpoint. A subsequent actual operator-tab test completed
  same-tab sign-in with no popup and reached an active authenticated text call.
  Its Maria reservation question returned Scottsdale, September 10-12, 2026,
  and USD 25 valet, with Fabric followed by Foundry IQ in the activity timeline.
  The root no longer forwards authorization responses to the MSAL bridge based
  on an opener. Hosted version 7 and bridge `em4` were unchanged.
- Revision `audio1` subsequently added the real synthetic question WAV through
  the existing same-origin static audio route. The live file matched the direct
  voice test's SHA-256. The actual prerecorded attempt after an ended text call
  failed before `auth_ack`, with four invalid-or-expired session errors, no WAV
  transcription and zero output audio bytes. The old text transcript was not
  counted as speech recognition.
- Source repair `9885ef8` binds each fresh connection and retry to the matching
  handle/session-ID pair from the same POST response, clears previous guest data
  on a new call and cancels old retries. Its exact staged snapshot passed 85
  frontend tests, TypeScript build and lint. The same 85 tests and six proxy
  tests passed in the implementation worktree. ACR run `chx` produced immutable
  digest `sha256:3ed316d00c929147a1fac488f319606bd9c95666203b2661c522d68076d84992`.
  Revision `session1` is Healthy, Running and receives all traffic. The live
  bundle verified the matching-pair binding. Actual browser second-call audio
  acceptance is paused by explicit user instruction while on a call, not
  established by source tests or readiness. The operator tab remains signed in
  on session1 with a text call active. Its second text turn was not confirmed,
  the text/end/prerecorded sequence was not run, and there is no second-call
  audio result. No observers are installed. Do not end, retry, refresh or
  navigate that tab, including to Fabric, until the user explicitly resumes.
- The same existing proxy subsequently enabled supported single-revision HTTP
  sticky sessions without changing the image, replica limits or roles. Live
  root, config and health responses issued `acaAffinity`, and an in-memory
  cookie jar returned it on the next same-origin request. Cookie values were
  not logged. Revision `session1` remained Healthy, Running and received all
  traffic. This verifies the configured routing-cookie path, not a multi-replica
  load test or browser audio acceptance.
- Live proxy negative checks rejected missing/invalid bearer tokens with HTTP
  401 and an invalid WebSocket handle with an auth error and close code 1008.
  Correct rejection behavior did not establish a successful authorized call.
- Independent Microsoft 365 admin catalog details showed Hotel Guest Services
  as an Agent template, Available, version 1.0.1, with the expected Entra blueprint
  ID and one linked instance. The UI's Last published field was unpopulated, so
  no published timestamp was claimed.
- Evaluation source preservation `3a93357` passed 77 isolated offline tests,
  configuration validation, lint, formatting and type checking. Five evaluator
  dimension/threshold definitions and three datasets matched retained registered
  readbacks. The retained v7 language, primary-Hotel and strict-combined results
  remain 8/8 each. The aggregate Hotel definition remains 0/8, not a passing
  result. New local runner fixes were not remotely rerun. No exact historical
  generation-prompt or runtime-build fingerprint match is asserted.
- Runtime source preservation `6febbec` passed 112 isolated focused tests and
  type checking of 19 runtime source files. A separate disposable environment
  imported the real bridge server using production SDK pins, Agent 365 runtime
  and notifications 1.0.0 with hosting core 1.2.0, and passed all 12 bridge tests.
  This avoids treating the shared local environment's older hosting SDK as
  production-pin validation. The reviewed source and staged bytes matched.
  This commit did not redeploy or restart hosted v7 or bridge `em4`.
- Infrastructure/configuration source `7c0b7e0` passed 19 isolated tests,
  configuration type checking, and compilation of all three changed Bicep
  templates. The bridge keeps Key Vault references and one replica. The proxy
  keeps Single-mode sticky sessions and no broad Foundry developer-role module.
  The package contains exactly four root files with matching template/blueprint
  identifiers. No provisioning helper, credential operation, permission grant,
  package upload or infrastructure deployment was executed.
- Web source `9c4815c` passed 85 isolated frontend tests, production build and
  lint, plus three proxy configuration cases. Offline scripted playback is
  enabled only for development, never production/staging or an authentication
  failure. This source commit made no browser action, voice call or deployment.
- Fabric/data/knowledge source `7d45cc9` preserves the business fixtures, source
  generators, all 95 generator-matched corpus documents, V2 ontology and
  readiness-gated publication inputs. Its guard prevents the generic apply
  path from replacing existing native Data Agent or model definitions before
  any writes or state saves. Eleven negative/compatibility regressions cover
  refusal, discovery failure, unchanged state, safe new-item/non-native
  operations and dry runs. The combined exact staged source passed 299
  repository/provisioning/proxy unit tests and 74 evaluator tests with external
  network and subprocess operations blocked during tests. Full lint/format
  checks, 77-source-file type checking, technical naming, configuration and
  ASSERT validation also passed. The human-facing agent-user display name is
  allowed without exempting technical identity names or UPNs. Seven formatting
  adjustments preserved identical Python ASTs.
  The dirty Q&A toggle and all user-owned AI configuration were excluded.
  This is source preservation only. No live workload, permission, credential,
  publication, browser or voice action was executed. Native acceptance remains
  incomplete, and the retained legacy declarative graph source is not a
  substitute for the supported ontology-context workflow.

At that checkpoint, SQL native Topics readback, ontology-context acceptance,
model-owned AI setup/Verified Answers, all actual email reply To/Cc headers,
and browser audio acceptance were not complete. Browser authentication and
text-mode retrieval were verified separately. Do not use this guide, the
publication operation, or the successful v7 direct invocation as a claim that
those remaining gates passed.

For a new tenant, run every gate again against that tenant's actual resources and
identities. Previous-tenant receipts are reference material, not target acceptance.
