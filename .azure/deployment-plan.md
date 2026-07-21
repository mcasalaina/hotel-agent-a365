# Azure Deployment Plan

## Status

Deployed - Hosted Agent version 55 pinned for Voice Live

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
- East US 2 consumption-based Container Apps web host in `rg-hotel-agent-a365`, reusing the existing
  `ca31c6a7351facr.azurecr.io` registry.

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
- Dedicated Voice web managed identity with `AcrPull` only on the existing registry and
  `Azure AI Developer` only on the existing Foundry project.
- Single-tenant Entra API registration exposing delegated `HotelAgent.Access`, plus a separate SPA
  public client using Authorization Code with PKCE and the deployed
  `<HTTPS origin>/redirect.html` MSAL v5 redirect bridge as its redirect URI.
- Browser access tokens remain in memory and are validated by the proxy; the Foundry bearer token
  is acquired only by the proxy managed identity and never reaches the browser.

## Phase gates

### Phase 1

Prepare and verify synthetic data, both Fabric lakehouses, mutation notebooks, semantic model, report, ontology, published Fabric data agent, Search indexes, Foundry IQ, Work IQ integration, Hosted Agent, and Foundry evaluations.

### Phase 2

Prepare and verify Agent 365 identity, blueprint, consent, licenses, manifest, publication, Teams OBO behavior, Work IQ mutation behavior, and observability.

### Phase 3

Add `invocations_ws` to the same Hosted Agent, integrate Voice Live foreground/background processing, deploy the simulated-call web app, and rerun all prior regressions.

The prepared web deployment uses:

- `infra/voice-web.bicep` for `hotel-voice-env`, `hotel-voice-proxy`, and
  `hotel-voice-proxy-identity` in East US 2.
- Container Apps consumption with `minReplicas: 0`, `maxReplicas: 2`, HTTPS-only ingress, managed
  identity image pull, no registry credential, and no Log Analytics workspace.
- The existing East US Basic registry `ca31c6a7351facr`; no new registry is provisioned.
- `web/backend/Dockerfile` for the same-origin React frontend and aiohttp proxy image.
- Single-tenant Entra API and SPA registrations. The production frontend resolves its redirect URI
  to `<window.location.origin>/redirect.html`; that exact bridge URI is registered after
  provisioning.

Capacity checks found East US 2 App Service Basic quota is zero, while Container Apps supports the
region and the subscription has a managed-environment limit of five with one environment currently
deployed elsewhere. Container Apps consumption, ACR build/storage, and network usage are billable.
Deployment requires explicit approval for those charges, the two Entra registrations, API scope and
SPA preauthorization, and the two managed-identity role assignments.

## Validation and deployment handoff

When implementation artifacts are complete:

1. Change this status to `Ready for Validation`.
2. Run the `azure-validate` workflow.
3. Resolve all validation findings.
4. Use the `azure-deploy` workflow for Azure deployment.
5. Run the live component and phase-gate tests in `PLAN.md`.

## Section 7: Validation Proof

Validated on 2026-07-20 for subscription `27b0139a-16b4-42bf-9ec9-c6db3768245e`,
tenant `a9d9510e-7131-4355-8b7e-37e7b1e99862`, resource group
`rg-hotel-agent-a365`, and East US 2:

- `az bicep build --file infra/voice-web.bicep --stdout`: passed.
- `az deployment group validate ... --template-file infra/voice-web.bicep`: provisioning state
  `Succeeded` with no error.
- `az deployment group what-if ... --result-format ResourceIdOnly`: status `Succeeded`; only
  idempotent `Deploy` operations were reported and no deletes were present.
- `npm run build`, `npm run lint`, and `npm run typecheck` in `web/frontend`: passed; production
  output includes isolated `redirect.html`, its MSAL redirect-bridge bundle, and `favicon.svg`.
- `npm test` in `web/frontend`: 59 tests passed.
- `pytest tests/unit/test_voice_proxy.py`, Ruff check, and Ruff format check: passed.
- Subscription policy assignment query returned no assignments at subscription scope.
- Static role review verified the user-assigned proxy identity receives `AcrPull` only on the
  existing registry and `Azure AI Developer` only on the existing Foundry project. Both assignments
  use deterministic names and `ServicePrincipal` principal type.
- Revalidated on 2026-07-20 for the call and asset hotfix. Bicep compilation and resource-group
  validation passed; what-if succeeded with no resource deletion and showed the intended
  `ENTRA_API_AUDIENCE` change from the App ID URI to the v2 API client-ID GUID. The full frontend
  suite passed 59 tests plus lint, typecheck, and production build. The proxy tests and Ruff checks
  passed. Subscription policy and static/live role results remain unchanged.
- Revalidated on 2026-07-20 for the authentication cache hotfix:
  - `az bicep build` and `az bicep lint` passed.
  - `az deployment group validate` returned `Succeeded`.
  - `az deployment group what-if --result-format ResourceIdOnly` returned `Succeeded` with
    idempotent deploy operations and no deletion.
  - Azure CLI authentication is enabled for the intended subscription and tenant; no
    subscription-scope policy assignments were returned.
  - The frontend passed 59 tests, lint, typecheck, and production build. The built page forwards
    legacy root authentication responses to `/redirect.html`, while visible brand marks are inline
    SVG.
  - The proxy tests and Ruff checks passed; frontend HTML, root assets, and the redirect bridge
    return `Cache-Control: no-store`.
  - Static role review remains unchanged: `AcrPull` is scoped to the existing registry and
    `Azure AI Developer` is scoped to the existing Foundry project, both for the dedicated
    `ServicePrincipal`.
- Revalidated on 2026-07-20 for the managed-identity hotfix. Production logs at
  `2026-07-20T22:03Z`
  proved browser authentication and session creation succeeded (`POST /api/auth/session` 201) and
  the call socket upgraded (`GET /api/calls` 101), but every upstream attempt failed before the
  Foundry connection because `DefaultAzureCredential` could not select the attached user-assigned
  identity. The hotfix injects the identity client ID as `AZURE_CLIENT_ID` and passes it explicitly
  as `managed_identity_client_id`. Six focused proxy tests and Ruff checks passed, including a
  startup gate that acquires a Foundry token before the revision can become healthy. Bicep build,
  lint, and resource-group validation passed. What-if showed the intended environment addition with
  no deletion; authentication, subscription policy, and static/live least-privilege role checks
  passed.
- Revalidated on 2026-07-20 for the Hosted Agent protocol-routing hotfix:
  - Foundry session `d4067374c62d42f8b330d6e214984c64` resolved to version 46, whose live
    definition exposes only `responses`; the agent endpoint routes 100% of traffic to `@latest`.
    This proves the HTTP 400 occurs before application dispatch because `invocations_ws` is absent
    from the latest version.
  - The current `azure.yaml` and `agent.manifest.yaml` both declare `responses` 2.0.0 and
    `invocations_ws` 1.0.0.
  - `azd package hotel-servicing-agent --no-prompt` passed.
  - The 13 focused Voice Live and proxy tests passed; Ruff check and format verification passed.
  - Bicep build and lint passed for `infra/main.bicep` and `infra/voice-web.bicep`.
  - Resource-group validation of the deployed Voice web template returned `Succeeded`.
  - `azd ai agent doctor` confirmed authentication, project access, developer RBAC, and active
    Hosted Agent status. Its obsolete `agent.yaml` check is not applicable because the initialized
    project is defined by `azure.yaml`; the Foundry azd guidance explicitly states that
    `agent.manifest.yaml` is a seed format and is not retained by `azd ai agent init`.
  - `azd provision --preview` is not applicable to this application-only Hosted Agent deployment:
    the Microsoft Foundry provider injects its own generic Bicep parameters into the repository's
    separately managed subscription template. No infrastructure provisioning will be executed.
  - Azure CLI and azd authentication target subscription
    `27b0139a-16b4-42bf-9ec9-c6db3768245e`, tenant
    `a9d9510e-7131-4355-8b7e-37e7b1e99862`; the user reconfirmed that subscription and the existing
    Foundry resource group's East US location. No subscription-scope policy assignments exist.
  - `azd deploy hotel-servicing-agent --no-prompt` published active version 47 with both protocols.
    The endpoint now routes 100% to version 47 and exposes `activity`, `responses`, and `invocations`.
  - Two prerecorded Voice Live smoke calls completed through the public `invocations_ws` endpoint.
    The pinned-version run received `auth_ack`, a final user transcript, an agent transcript, and
    129,600 bytes of synthesized audio. Hosted logs show `GET /invocations_ws` returned 101.
  - Container App revision `hotel-voice-proxy--0000005` remains healthy and running at
    `https://hotel-voice-proxy.mangoground-da18d06a.eastus2.azurecontainerapps.io`.
- Revalidated on 2026-07-20 for voice-language stabilization:
  - Interim and main-agent instructions now preserve the established conversation language.
    Names, place names, accents, and isolated foreign words do not trigger a switch; switching still
    occurs for an explicit request or a complete utterance clearly in another language.
  - Eight focused Voice Live tests passed, including regression checks for both instruction layers.
  - Ruff check, Ruff format verification, and `git diff --check` passed.
  - `AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd package hotel-servicing-agent --no-prompt`
    completed successfully.
  - azd authentication, the existing Foundry project endpoint, dual-protocol version 47, and the
    confirmed deployment subscription were reverified. No subscription-scope policy assignments
    exist, and this code-only Hosted Agent update requires no infrastructure provisioning.
- Revalidated on 2026-07-21 for concise voice responses, backend activity, and guest reservation
  lookup:
  - The focused Voice Live, Voice smoke, Fabric data, and proxy suites passed all 22 tests. Ruff
    check, Ruff format verification, and `git diff --check` passed.
  - Direct Fabric MCP validation resolved Maria Garcia to the exact guest record and returned all
    ten reservations across dates and statuses. The governed query now treats "any reservations"
    and "on file" as an all-status lookup unless the caller explicitly requests active or upcoming
    records.
  - Live Voice Live probes proved `response.output_item.added` events expose
    `query_hotel_operations_data` for the activity stream. They also proved hosted-agent mode
    rejects session and per-response instruction overrides, while an injected system conversation
    item can stall after tool execution. The final package uses concise main-agent response rules
    and none of those unsupported or unreliable channel overrides.
  - A production prerecorded probe exposed a VAD/manual-commit race: trailing silence could
    auto-commit the recording before the harness sent `audio_commit`, producing `buffer too small`.
    The prerecorded client now trims long edge silence, streams PCM at its real 24 kHz rate, and
    commits immediately after speech, before the two-second VAD threshold. Live microphone mode
    retains multilingual semantic VAD, interruption, and automatic response.
  - `AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd package hotel-servicing-agent --no-prompt`
    passed again for the final dual-protocol package after removing the unreliable system-context
    path and making prerecorded streaming deterministic. `azd ai agent doctor` passed
    authentication, project access, developer RBAC, active-agent, and `azure.yaml` checks; its
    legacy `agent.yaml` check is not applicable to this `azure.yaml` hosted-agent service.
  - `az bicep build` and `az bicep lint` passed for `infra/main.bicep` and
    `infra/voice-web.bicep`. No subscription-scope policy assignments were returned.
  - Azure CLI and azd authentication target enabled subscription
    `27b0139a-16b4-42bf-9ec9-c6db3768245e` in tenant
    `a9d9510e-7131-4355-8b7e-37e7b1e99862`; the existing Foundry project reports East US 2.
    This deployment updates hosted-agent code only and does not provision infrastructure.
  - Hosted Agent version 55 is active with `responses` 2.0.0 and `invocations_ws` 1.0.0, and the
    production route resolves to version 55.
  - A prerecorded Maria Garcia production call transcribed the request correctly, emitted Fabric
    `data_source` activity, returned the ten all-status reservation records in two concise sentences,
    and synthesized 729,000 bytes of audio.
  - A simple prerecorded production call returned the expected short English welcome and synthesized
    334,800 bytes of audio without invoking a backend data source.
  - A Work IQ production probe emitted both the work-context access check and Work IQ `data_source`
    activity before its final spoken response, and synthesized 415,200 bytes of audio.
  - The production Voice web `/api/health` endpoint returns `{"status": "ok"}`. Container App revision
    `hotel-voice-proxy--0000005` remains running at 100% traffic. Live role verification confirms the
    proxy identity has only `AcrPull` on the existing registry and `Azure AI Developer` on the
    existing Foundry project.

## Role Assignment Verification

- Status: Verified.
- The existing Voice web managed identity remains scoped to `AcrPull` on the existing registry and
  `Azure AI Developer` on the existing Foundry project.
- Both assignments use deterministic names, resource-level scope, and `ServicePrincipal` principal
  type. This code-only update adds no identity, role assignment, or permission.

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
- 2026-07-16: Prepared the Phase 3 Voice Live deployment. Confirmed subscription
  `27b0139a-16b4-42bf-9ec9-c6db3768245e`, tenant
  `a9d9510e-7131-4355-8b7e-37e7b1e99862`, and East US 2. App Service Basic quota is unavailable;
  selected a scale-to-zero Container App instead. Added repeatable Bicep for the web host, dedicated
  identity, ACR pull, and Foundry project access. No Azure resources or Entra registrations were
  modified during preparation.
- 2026-07-20: Deployed Hosted Agent version 42 with active `responses` 2.0.0 and
  `invocations_ws` 1.0.0 protocols. Assigned its identity `Cognitive Services User` on the Foundry
  account and `Foundry User` on the Foundry project for Voice Live. Prerecorded mode now retains
  multilingual semantic VAD with automatic response creation disabled, waits for final
  transcription before creating the response, and omits echo cancellation.
- 2026-07-20: Deployed `hotel-voice-proxy` in the East US 2 `hotel-voice-env` Container Apps
  environment. The healthy revision uses immutable image digest
  `sha256:4094eabda5006e1a806693f0bdd388fad96bdc726de73fb4bb140b5637e140fe` and is available at
  `https://hotel-voice-proxy.mangoground-da18d06a.eastus2.azurecontainerapps.io`.
- 2026-07-20: Created single-tenant Entra API application
  `87b35858-3f43-46f6-b226-3a211eb2df25` and SPA application
  `96245d3a-eaee-43d1-9586-e2c3ef65f116`. The API exposes and preauthorizes
  `HotelAgent.Access`; the SPA redirect URI is the deployed HTTPS origin.
- 2026-07-20: Live acceptance returned 200 from health, frontend, configuration, and AudioWorklet
  routes; unauthenticated session exchange returned 401. A prerecorded Spanish prompt produced an
  automatic Spanish transcript, Spanish interim speech, and 148,800 audio bytes. Voice mode
  proactively greeted the caller and returned 193,200 audio bytes.
- 2026-07-20: Fixed the production sign-in defects. The proxy now serves `favicon.svg` as
  `image/svg+xml`, and the frontend uses the mandatory isolated MSAL v5 redirect bridge at
  `/redirect.html` instead of running the full React application in the authentication popup. The
  Entra SPA registration now contains that exact bridge URI.
- 2026-07-20: Deployed ready revision `hotel-voice-proxy--0000001` with immutable image digest
  `sha256:e1d03ac8b14d20112af8e2dc2c2f2a4d3918d27089973e0d043611204bd724ca`.
  Live checks confirmed the SVG MIME type, bridge bundle and no COOP header, production
  `/redirect.html` config, healthy API, and anonymous-session HTTP 401.
- 2026-07-20: Deployed ready revision `hotel-voice-proxy--0000002` with immutable image digest
  `sha256:b1ffa0416ec1263e77423cbbd5b96943ae9253acb0c1337d0d1f0887593c786d`.
  The live Container App now validates v2 access tokens against the API client-ID GUID. The
  Vite-managed brand asset returns `image/svg+xml`, both screens reference its hashed URL, the
  synthetic-data header label is absent, health is green, and traffic is 100% on the new revision.
  Live role verification remains limited to `AcrPull` on ACR and `Azure AI Developer` on the
  Foundry project.
- 2026-07-20: Deployed ready revision `hotel-voice-proxy--0000003` with immutable image digest
  `sha256:42c331199f1d2973310870bb14477047a7157a1336cba572f059e6c7b7bfbed8`.
  Traffic is 100% on the healthy revision. Live HTML and the MSAL redirect bridge return
  `Cache-Control: no-store`; visible brand marks are inline SVG with no image request. The Entra
  SPA keeps `/redirect.html` as the primary callback and also accepts the exact site origin for
  already-open stale clients, whose authentication responses are forwarded to the bridge. A live
  OAuth authorization probe accepted that root URI and redirected it back rather than returning
  `AADSTS50011`. Live role verification remains unchanged and least-privileged.
- 2026-07-20: Production call diagnostics proved browser token validation, session creation, and
  WebSocket ingress were healthy, while all four reconnect attempts failed when the proxy requested
  a Foundry token without selecting its user-assigned identity. Deployed ready revision
  `hotel-voice-proxy--0000005` with immutable image digest
  `sha256:5a0871b824cf08558dd669480814b7bba49994e300a8f3a43532cb8e130df838`.
  The live revision receives `AZURE_CLIENT_ID=86cc50dd-3905-4ae6-a483-f479e5903c7d`, explicitly
  configures that client ID on `DefaultAzureCredential`, and gates startup on Foundry token
  acquisition. Production startup logs show the managed-identity endpoint returned 200 and
  `DefaultAzureCredential acquired a token from ManagedIdentityCredential`. Revision `0000005` is
  healthy and receives 100% traffic; live roles remain `AcrPull` on ACR and `Azure AI Developer`
  on the Foundry project.

### Live Role Verification

- Identity: `hotel-voice-proxy-identity`
  (`a0a2277a-4d0b-4c40-9977-bfb9ae81e720`).
- `AcrPull` is present at the existing `ca31c6a7351facr` registry scope.
- `Azure AI Developer` is present at the existing `4iq-foundry-project` project scope.
- Both assignments target the current `ServicePrincipal`; status: pass.
