# Azure Deployment Plan

## Status

In Progress - Phase 1 foundation and Work IQ deployed; mutation, evaluation, and final Teams gates remain

## Canonical product plan

See `../PLAN.md` for the complete three-phase implementation plan, property roster, data model, test matrix, Agent 365 permission runbook, and Voice Live architecture.

## Deployment scope

- Existing Microsoft Foundry project:
  `https://4iq-foundry-project-resource.services.ai.azure.com/api/projects/4iq-foundry-project`
- Existing project ARM ID:
  `/subscriptions/27b0139a-16b4-42bf-9ec9-c6db3768245e/resourceGroups/rg-aycabas-3iqs/providers/Microsoft.CognitiveServices/accounts/4iq-foundry-project-resource/projects/4iq-foundry-project`
- Existing region: `eastus2`
- Existing model deployments:
  - `gpt-5.4-mini`
  - `text-embedding-3-small`
- Existing resource group: `rg-aycabas-3iqs`
- Existing Azure AI Search service with four hotel indexes and one Foundry IQ knowledge base.
- Existing storage account with the generic `hotel-docs` container for knowledge documents.
- Containerized Foundry Hosted Agent `hotel-servicing-agent`.
- Generic Agent 365 host/web resources needed by the approved publish path.
- Existing Application Insights associated with the target Foundry resource for tracing.

## Fabric scope

One Fabric workspace, `HotelAgent.Workspace`, with two authoritative lakehouses:

- `HotelOperations`: properties, rooms, room types, amenities, inventory, rates, outlets, associates, maintenance requests, and work orders.
- `HotelGuestServices`: guests, reservations, stays, dining reservations, folios, disputes, special requests, confirmations, idempotency records, and customer-facing audit events.

The Fabric data agent connects directly to both lakehouses to demonstrate cross-source unification. A Direct Lake semantic model uses limited source-controlled OneLake shortcuts from `HotelGuestServices` to required `HotelOperations` tables; no third lakehouse or Azure SQL database is created.

Deploy the workspace on the existing active East US 2 F16 capacity `cap3iqs5ea837a6` (`24f6590d-413b-4d9f-9c2b-601d753eda94`).

## Delivery recipe

- Azure Developer CLI and the Microsoft Foundry hosted-agent extension for agent packaging/versioning.
- Bicep or azd-managed supporting Azure resources where the existing Foundry project does not already provide them.
- Fabric REST APIs, source-controlled item definitions, and Fabric notebooks for workspace items, Delta loads, mutations, semantic model, report, ontology, and data-agent publication.
- Agent 365 CLI plus validated manifest packaging for identity and Teams publication.

## Security and identity

- Managed identity and least-privilege RBAC.
- No secrets in source control.
- No full payment-card data.
- `Lyrenza` prohibited in technical resource/item/identity names.
- Explicit confirmation before every synthetic business mutation.
- Idempotency, record-version checks, immutable audit events, and cross-lakehouse reconciliation.
- Agent 365 blueprint ownership, Agent ID roles, OBO grants, current V2 Work IQ MCP scopes, Fabric workspace access, and tenant mutation policy verified before Teams sign-off.

## Phase gates

### Phase 1

Prepare and verify synthetic data, both Fabric lakehouses, mutation notebooks, semantic model, report, ontology, published Fabric data agent, Search indexes, Foundry IQ, Work IQ integration, Hosted Agent, and Foundry evaluations.

### Phase 2

Prepare and verify Agent 365 identity, blueprint, consent, licenses, manifest, publication, Teams OBO behavior, Work IQ mutation behavior, and observability.

### Phase 3

Add `invocations_ws` to the same Hosted Agent, integrate Voice Live foreground/background processing, deploy the simulated-call web app, and rerun all prior regressions.

## Validation and deployment handoff

When implementation artifacts are complete:

1. Change this status to `Ready for Validation`.
2. Run the `azure-validate` workflow.
3. Resolve all validation findings.
4. Use the `azure-deploy` workflow for Azure deployment.
5. Run the live component and phase-gate tests in `PLAN.md`.

## Progress

- 2026-07-11: Product plan approved.
- 2026-07-11: GitHub repository created and collaborator invited.
- 2026-07-11: Azure context resolved from the supplied Foundry endpoint; use subscription `27b0139a-16b4-42bf-9ec9-c6db3768245e` and region `eastus2`.
- 2026-07-11: Repository/application bootstrap started. No cloud resources have been created or modified yet.
- 2026-07-11: Shared repository skeleton, Hosted Agent container scaffolding, safe configuration examples, technical naming guard, and baseline developer checks prepared. Status remains In Progress pending later implementation workstreams and validation.
- 2026-07-11: Bootstrap validation passed (Ruff, mypy, pytest, configuration/naming checks, dependency check, and shell syntax). Domain content and deterministic data generation started in an isolated child worktree.
- 2026-07-11: Read-only environment discovery found no subscription-scope policy assignments or resource-group locks, confirmed an active East US 2 F16 Fabric capacity, and identified the existing project Search connection as East US rather than East US 2. Plan updated to use a new generic East US 2 Search service.
- 2026-07-11: Prepared subscription-scope Bicep for a possible dedicated East US 2 Search/storage deployment, but did not execute it. This path was superseded after live Foundry IQ validation showed the project's existing Search and storage resources satisfy the Phase 1 requirements.
- 2026-07-11: Generated and validated 658,611 deterministic hotel rows, stable demo fixtures, and 95 customer-facing Foundry IQ source documents.
- 2026-07-11: Archived 95 source documents in `hotel-docs`; created four Search indexes, four knowledge sources, and `hotel-foundryiq` in the existing Search service. Direct counts and citation-backed answer synthesis passed.
- 2026-07-11: Deployed `hotel-servicing-agent` from source through the Foundry REST code-agent API after azd was found authenticated to an expired tenant. Version 4 is active; its instance identity has Search Index Data Reader.
- 2026-07-11: Live Responses checks passed for dated notices, chain policy, dining guidance, unsupported facts, and HTL-003 property isolation. Status remains In Progress because Fabric, Work IQ, Agent 365, and the full Phase 1 evaluation gate are not complete.
- 2026-07-11: Added a five-case source-controlled Foundry evaluation seed. Remote suite creation remains blocked until azd is reauthenticated from the expired `CA M365 2606` tenant to the active project tenant.
- 2026-07-11: Integrated and revalidated the data, corpus, Foundry IQ, and Hosted Agent work. Full generation produced 658,611 rows and 95 documents; all 36 local tests passed; live indexes contain 20 property, 15 policy, 20 dining/local, and 40 operations documents; a version 4 Responses invocation returned the expected HTL-001 pool hours with two approved citations.
- 2026-07-11: Prepared the Fabric topology, typed notebook contracts, dry-run-first REST deployment tooling, and schema-gated semantic-model, report, ontology, and data-agent blueprints. No Fabric workspace or items have been deployed yet.
- 2026-07-11: Deployed Fabric workspace `HotelAgent.Workspace`
  (`660ed238-54b7-42bd-8b1b-cf2ee47a11ba`) with authoritative lakehouses
  `HotelOperations` (`cdbf3424-785f-4121-b930-5d887e549b01`) and
  `HotelGuestServices` (`2d0890bf-5b05-4bc0-b47f-1af1935820ff`). Loaded and validated all
  source tables and six reporting aggregates.
- 2026-07-11: Deployed and refreshed `HotelOperationsModel`
  (`9890681b-e022-44cf-92f1-ef8bbdaddab7`), `HotelOperationsReport`
  (`b93b57a9-d23f-45e4-b80b-247c5f2642d7`), and `HotelOperationsOntology`
  (`6b854a1e-b051-4a43-bdab-99cf45a170c5`). Corrected the
  `StayAssignedRoom` source/target contextualization during live ontology validation.
- 2026-07-11: Deployed and published `HotelOperationsAgent`
  (`9990b87a-d2ef-4c23-b11d-ffd72905906c`). Definition-only lakehouse elements remained
  `NotAvailable`; the supported repair is to re-register both lakehouse sources, synchronize and
  select their live schemas with `fabric-data-agent-sdk==0.1.26a0`, apply descriptions/examples,
  and publish. `HotelDataAgentRuntimePublish` now automates that sequence. MCP tests passed for
  operations-only, guest-services-only, and cross-lakehouse questions.
- 2026-07-11: Granted the Hosted Agent principal
  `6b7f2f82-66cb-470b-b16a-f7775463b341` Fabric workspace Viewer access. Replaced the eager Agent
  Framework MCP transport, which failed during Hosted Agent initialization, with an on-demand
  function wrapper over the proven MCP `ClientSession` path.
- 2026-07-11: Deployed active Hosted Agent version 8. Isolated Foundry IQ, Fabric reservation, and
  cross-lakehouse tests passed. The combined `RES-DEMO-RATE-CHANGE` test automatically propagated
  `HTL-001` from Fabric to Foundry IQ and returned the cited `06:00-22:00` pool hours. The
  structured-data tool now requires exact property IDs in every property result to make the handoff
  deterministic.
- 2026-07-11: Reused the Foundry-managed blueprint, deployed Azure Bot Service
  `hotel-servicing-agent-bot`, and created Microsoft 365 title
  `T_5f1601d1-0ccc-13b2-6d7f-ec5730e45a91`. The stable endpoint exposes `activity` and `responses`
  with `BotServiceTenant` authorization.
- 2026-07-14: Determined that the direct Foundry tenant publication did not appear as the required
  reusable Agent 365 **Agent template**. Rebuilt the flat four-file package using the Bank Agent
  structure, linked template `9a2da06d-059c-4b40-910f-ca8e0a6b1730` to blueprint
  `55698a0b-48c3-412e-ba56-373ebb35283d`, validated both ID invariants and the Teams manifest schema,
  and generated `manifest/manifest.zip`.
- 2026-07-14: Published the package through **Agents > All agents > Registry > ... > Add agent**,
  not Integrated Apps. Verified the resulting `Hotel Guest Services` registry item is an
  **Agent template**, activated it for all users, configured its Foundry-managed blueprint as
  **API Based** with the live Bot Service `activityProtocol` endpoint, and created
  `Hotel Guest Services Agent` (`hotelguestservices@cam3652609.onmicrosoft.com`, object ID
  `dbd88b91-61f2-4ee7-92e9-0c04a6322e1b`). Granted the instance user Azure AI Developer at account
  and project scope, both required Cognitive Services user roles at account scope, and Fabric
  workspace Contributor access. Added Microsoft Cognitive Services and Azure Machine Learning
  Services `user_impersonation` tenant-wide consent grants plus matching inheritable blueprint
  permissions. Verified **Agents > Tools > Work IQ MCP > Policies** already enables write, create,
  partial-update, replace, and delete actions tenant-wide; the hotel agent remains read-only through
  its own tool allowlists. Real Teams, Work IQ, Fabric, and telemetry acceptance remains pending
  propagation.
- 2026-07-14: In Exchange admin center, granted **Read and manage (Full Access)** on
  `hotelguestservices@cam3652609.onmicrosoft.com` to
  `mcasalaina.local@cam3652609.onmicrosoft.com` and
  `aycabas.local@cam3652609.onmicrosoft.com`. Exchange confirmed both assignments and a Full Access
  count of two. Send As and Send on behalf remain unassigned.
- 2026-07-14: Audited blueprint consent against its inheritable permissions and found three missing
  tenant-wide grants: Microsoft Graph, Power Platform API, and Agent Tools. Added the minimum matching
  scopes, bringing the blueprint to nine grants. A direct synthetic `activityProtocol` request then
  returned HTTP 202, resolved Hosted Agent version 16, and produced a successful correlated
  `invoke_agent` trace and `READY` response in Foundry.
- 2026-07-14: Microsoft documentation states that inheritable permissions apply to newly created
  agent identities. Created clean validation instance `Hotel Guest Services Agent 2`
  (`hotelguestservices2@cam3652609.onmicrosoft.com`, user object
  `0711dbee-f251-41b8-a71b-2ad92283945c`, Entra agent ID
  `288dbfc9-2f41-4b55-b64d-f31a29ad4057`) after the complete grant set was in place. Granted the new
  user Azure AI Developer at Foundry account and project scope, Cognitive Services User and
  Cognitive Services OpenAI User at account scope, and Fabric workspace Contributor access.
  Preserve the original instance until this replacement passes live Teams acceptance.
- 2026-07-11: Granted the blueprint tenant-wide delegated and inheritable
  `Tools.ListInvoke.All` access for the V2 Copilot, Mail, and Teams Work IQ resources. Granted the
  Hosted Agent identity `Agent365.Observability.OtelWrite`.
- 2026-07-11: Deployed active Hosted Agent version 9 with the read-only Work IQ tool. Local checks
  pass, ordinary live retrieval remains healthy, and a direct Work IQ probe reaches `user_fic`.
  Authoritative Work IQ validation is blocked on M365 admin publication and a real Teams agentic
  user; direct Foundry callers correctly fail with `AADSTS7002200` because they have no matching
  user federated credential.
- 2026-07-11: Superseded version 9 with active version 10 after restricting Copilot, Mail, and Teams
  MCP servers to positive read-only tool allowlists and adding partial-initialization cleanup.
  Re-enabled Bot Service public network access because disabling it unconfigures Teams channels.
  The live Teams channel remains enabled, stable endpoint traffic routes 100% to `@latest`, and the
  cited HTL-001 regression passes.
- 2026-07-15: Re-enabled the disabled Foundry-managed blueprint principal, which restored Hosted
  Agent runtime storage. Replaced the nonworking Foundry-managed Agent 365 route with owned blueprint
  `f1ae4991-0418-470b-96d5-7f7df43ab5d2` and Container Apps bridge
  `hotel-agent-bridge-a365`. The bridge sends the authenticated agentic user through
  `x-ms-user-identity` on initial and MCP approval requests.
- 2026-07-15: Identity Proxy Manager, preview SDK federated credentials, a raw Hosted Agent FIC, and
  explicit project-managed-identity selection all failed for distinct identity or token-contract
  reasons. Stored a dedicated owned-blueprint credential in Key Vault `hotelagentkv4iqs`, granted
  only the Hosted Agent identity read access, and implemented the explicit blueprint, instance, and
  delegated `user_fic` token exchanges. No credential is present in source or Hosted Agent
  environment metadata.
- 2026-07-15: Deployed Hosted Agent version 23. Authentication preflight passed for Copilot, Mail,
  and Teams. Replaced obsolete prefixed MCP allowlist names with the exact live case-sensitive tool
  names, after which live Mail and Teams metadata reads passed. A send-email request was refused,
  confirming the positive read-only boundary. Permission changes in this tenant must be checked
  immediately and never waited on for more than one minute.
