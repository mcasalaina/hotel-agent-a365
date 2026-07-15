# Deployment

The live development deployment uses the existing Foundry project, Search service, model
deployments, and storage account. Repository commands remain operator-invoked and do not deploy
implicitly.

## Foundry binding configuration

The azd project binds to the existing project through its active environment. The environment must
provide:

- `FOUNDRY_PROJECT_ENDPOINT`
- `AZURE_AI_PROJECT_ENDPOINT`
- `AZURE_AI_PROJECT_ID`
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`

Start from `config/azd.env.example`. The expected model deployment is `gpt-5.4-mini`. The project ARM ID is required by `azd ai agent init --project-id` or the active azd environment, but it is not treated as a secret.

Do not run `azd init -t` in this non-empty repository. The Hosted Agent service uses Foundry
direct-code deployment (`python_3_13`, remote dependency resolution); it does not require a local
Docker daemon.

## Predeployment checks

```bash
make check
```

The naming check is mandatory before every deployment. It scans technical configuration fields and fails when the fictional customer brand is used in Azure, Foundry, Fabric, Agent 365, package, environment, identity, URL, or item names. Customer-facing Markdown and generated business data are intentionally outside that technical scan.

## Foundry IQ setup and verification

These commands operate on the approved endpoints configured in the local environment. They do not
deploy the Hosted Agent.

```bash
make setup
.venv/bin/python scripts/setup_foundry_iq.py --dry-run
.venv/bin/python scripts/setup_foundry_iq.py
.venv/bin/python scripts/verify_deployment.py --property-id HTL-001 --as-of 2026-04-10
make check
```

`setup_foundry_iq.py` uses `DefaultAzureCredential` for Azure OpenAI embeddings and Search RBAC.
Set `AZURE_SEARCH_ADMIN_KEY` only when local key authentication is explicitly approved; it is never
logged. `AZURE_OPENAI_API_KEY` is an optional fallback for Search vectorization and answer synthesis
when the Search managed identity path is unavailable. Search stores this value encrypted and GET
responses redact it. To archive source Markdown in addition to indexing it, set both
`FOUNDRY_IQ_BLOB_CONTAINER` and `AZURE_STORAGE_ACCOUNT_URL`. Blob archival is optional.

Before running setup against provisioned resources, assign the Search service managed identity
**Cognitive Services OpenAI User** for vectorization and **Cognitive Services User** for
knowledge-base query planning on the Foundry account. The local setup identity needs permission to
manage Search indexes,
knowledge sources, and knowledge bases, and to upload index documents. The Hosted Agent/project
managed identity needs **Search Index Data Reader** on the Search service for retrieval. Assign the
equivalent reader role to any separate project or agent identity that performs retrieval. Validate
these assignments in the target subscription; this repository does not assert that any resource or
role assignment exists.

## Hosted Agent contract

- Service name: `hotel-servicing-agent`
- Current protocol: `responses` version `2.0.0`
- Container resources: 1 CPU and 2 GiB memory
- Deployment: Python 3.13 source ZIP with remote dependency resolution
- Local/container startup command: `./startup.sh`
- Model deployment: configured through `AZURE_AI_MODEL_DEPLOYMENT_NAME`
- Project endpoint: injected by Foundry in the hosted container
- Search endpoint and knowledge-base name: injected from azd environment values

Phase 3 adds `invocations_ws` version `1.0.0` to both `azure.yaml` and `src/hotel-servicing-agent/agent.manifest.yaml`, then adds the WebSocket adapter without replacing the shared orchestration.

## Live development deployment

- Search indexes: `hotel-properties-index`, `hotel-policies-index`,
  `hotel-dining-local-index`, and `hotel-operations-index`
- Knowledge sources: one `hotel-*-ks` source per index
- Knowledge base: `hotel-foundryiq`
- Source archive: 95 Markdown blobs in `hotel-docs`
- Hosted Agent: `hotel-servicing-agent`, active version 23
- Agent Search access: **Search Index Data Reader**
- Fabric workspace: `HotelAgent.Workspace`
  (`660ed238-54b7-42bd-8b1b-cf2ee47a11ba`)
- Fabric lakehouses: `HotelOperations` (`cdbf3424-785f-4121-b930-5d887e549b01`) and
  `HotelGuestServices` (`2d0890bf-5b05-4bc0-b47f-1af1935820ff`)
- Fabric semantic model: `HotelOperationsModel`
  (`9890681b-e022-44cf-92f1-ef8bbdaddab7`)
- Fabric report: `HotelOperationsReport` (`b93b57a9-d23f-45e4-b80b-247c5f2642d7`)
- Fabric ontology: `HotelOperationsOntology`
  (`6b854a1e-b051-4a43-bdab-99cf45a170c5`)
- Fabric data agent: `HotelOperationsAgent`
  (`9990b87a-d2ef-4c23-b11d-ffd72905906c`)
- Hosted Agent Fabric access: workspace **Viewer**
- Agentic user Fabric access: workspace **Contributor**

The live verification covers direct Search counts, answer synthesis with citations, dated notices,
chain policy grounding, dining guidance, unsupported-fact handling, property isolation,
operations-only and guest-services-only Fabric queries, cross-lakehouse synthesis, and an integrated
Fabric-to-Foundry-IQ property-ID handoff.

## Fabric Data Agent publication

Deploying the source-controlled draft definition is not sufficient to make imported lakehouse
elements queryable. Run `HotelDataAgentRuntimePublish` after applying the draft. It uses
`fabric-data-agent-sdk==0.1.26a0` to remove and re-add both lakehouse sources, synchronize the live
SQL schemas, select the governed tables, apply source descriptions and examples, and publish.
Calling `staging/publish` directly can leave handcrafted lakehouse elements in `NotAvailable`.

The Hosted Agent reaches the published Data Agent through
`FABRIC_DATA_AGENT_MCP_URL`. Grant its instance principal Fabric workspace Viewer access. The
runtime deliberately opens a direct MCP `ClientSession` only when the function tool is called;
eager `MCPStreamableHTTPTool` initialization failed in the Hosted Agent environment with a
cancellation-scope error.

## Agent 365 and Work IQ

- Owned blueprint: `hotel-agent-bridge Blueprint`
  - Client ID: `f1ae4991-0418-470b-96d5-7f7df43ab5d2`
- Foundry-managed blueprint dependency: `hotel-servicing-agent-fefec`
  - Client ID: `55698a0b-48c3-412e-ba56-373ebb35283d`
  - Principal ID: `11004b7e-29c5-4406-a1bd-b5defdcaacd9`
- Hosted Agent identity:
  `6b7f2f82-66cb-470b-b16a-f7775463b341`
- Container Apps bridge:
  `https://hotel-agent-bridge-a365.gentleforest-8d33b38e.westus.azurecontainerapps.io/api/messages`
  - Active revision: `hotel-agent-bridge-a365--0000005`
- Superseded non-template Microsoft 365 title:
  `T_5f1601d1-0ccc-13b2-6d7f-ec5730e45a91`
- Agentic user template ID:
  `9a2da06d-059c-4b40-910f-ca8e0a6b1730`
- Published Agent 365 template: `Hotel Guest Services`
- Agentic user instance:
  - Display name: `Hotel Guest Services`
  - UPN: `hotelguestservices@cam3652609.onmicrosoft.com`
  - Agent-user object ID: `ba923ab8-d1d8-46de-98a4-229cf0b29e6b`
  - Entra agent ID: `cc4f4078-c463-494a-a5fc-0b63a6995296`

The Container Apps bridge authenticates Agent 365 activity requests, forwards conversation history
to the Foundry Responses endpoint, and sends `x-ms-user-identity` on the initial request and every
MCP approval continuation. It prefers `activity.get_agentic_user()` over the ordinary activity
sender ID. Missing user context fails closed inside the Hosted Agent.

The Hosted Agent uses a dedicated owned-blueprint credential stored as
`agent365-blueprint-client-secret` in Key Vault `hotelagentkv4iqs`. Only the Hosted Agent managed
identity has `Key Vault Secrets User`. The runtime uses that identity to read the secret, obtains a
blueprint token with `fmi_path=cc4f4078-c463-494a-a5fc-0b63a6995296`, exchanges it for an Agent 365
instance token, and requests one delegated `user_fic` token per Work IQ V2 audience. The credential
is never present in source, azd environment values, Hosted Agent environment metadata, prompts,
browser state, or logs.

The Copilot, Mail, and Teams audiences and endpoints are source controlled in `azure.yaml`. The
positive read-only allowlists must match the exact case-sensitive names returned by each live MCP
server. The current contracts use `copilot_chat`; Mail uses `GetMessage`, `SearchMessages`,
`SearchMessagesQueryParameters`, `GetAttachments`, and `DownloadAttachment`; Teams uses only list,
get, search, and presence tools. The Hosted Agent may search, summarize, and draft, but it must not
send, post, delete, or modify Microsoft 365 content. Tool allowlists enforce this boundary; prompt
instructions are not the security control.

### Work IQ authentication troubleshooting record

1. Foundry requests failed before agent code ran because the Foundry-managed blueprint service
   principal was disabled. Re-enable principal `11004b7e-29c5-4406-a1bd-b5defdcaacd9`; this restores
   Foundry runtime storage immediately.
2. Teams reached Foundry without Work IQ context until the bridge forwarded
   `x-ms-user-identity`. Use the Agent 365 agentic user when available and preserve the header on
   approval requests.
3. Identity Proxy Manager failed with `-60018` because it selected the independently owned
   blueprint as a managed identity even though that identity is not assigned to the Hosted Agent.
4. The preview federated-credential SDK path returned `invalid_scope`. A raw Hosted Agent FIC then
   changed the error to `AADSTS700231`, proving a federated identity token cannot be reused as
   another federated assertion. Remove that invalid FIC.
5. Explicit project-managed-identity selection failed because the project identity is not exposed
   through the Hosted Agent managed-identity endpoint.
6. The working fallback keeps a dedicated blueprint credential in Key Vault and uses the Hosted
   Agent identity only to retrieve it. If credential creation succeeds but Key Vault storage fails,
   delete that credential immediately because its value cannot be recovered, fix vault RBAC, probe
   one write, and create a replacement only in a fail-fast command.
7. Authentication preflight passed in version 22, but Mail retrieval still returned no context.
   The cause was obsolete prefixed MCP allowlist names. Discover live tools with `list_tools`, use
   their exact names, and redeploy.

The blueprint has nine tenant-wide delegated grants: Messaging Bot, Microsoft Cognitive Services,
Azure Machine Learning Services, three V2 Work IQ resources, Microsoft Graph, Power Platform API,
and Agent Tools. Each required resource also has matching enumerated inheritable permissions.
Microsoft Graph, Power Platform API, and Agent Tools consent grants were found missing and added on
2026-07-14. The Hosted Agent identity has the `Agent365.Observability.OtelWrite` application role.
These are separate requirements: OAuth consent alone does not make a scope inheritable by future
agentic users, and Microsoft documents that inheritable permissions apply when a new agent identity
is created. The Hosted Agent also sets
`A365_USE_S2S_ENDPOINT=true`: its managed identity obtains an app-only token with the
`Agent365.Observability.OtelWrite` role, so the exporter must use the `/observabilityService/` route.
The delegated `/observability/` route expects an `scp` claim and rejects the app-only token with
HTTP 403 even when the role assignment is present. The runtime also pins the Agent Framework
agent `id` to `AGENT365_INSTANCE_CLIENT_ID`; otherwise generated `gen_ai.agent.id` span attributes
do not match the authenticated instance identity and the observability service rejects them.

Hosted Agent version 23 is active. The chain-wide next-week reservation regression returned the
authoritative 2026-07-12 through 2026-07-18 date window, total 214, and a complete 20-property
Markdown table with official names and IDs. Live regression also verifies exact-ID full-history
lookups, official property names, read-only mutation refusal, clean Work IQ access preflight, and
Fabric-to-Foundry-IQ property-key propagation without guessing. Version 23 live checks under agentic
user `ba923ab8-d1d8-46de-98a4-229cf0b29e6b` passed authentication for all three governed servers,
retrieved the latest Mail and Teams metadata, and refused an email-send request. No message body or
chat text was returned by the acceptance checks.
The earlier direct Foundry tenant publication is not the required Agent 365 **Agent template** and
must not be approved. The validated package at `manifest/manifest.zip` uses the same four-file
blueprint-plus-template structure as the Bank Agent: `manifest.json` declares
`agenticUserTemplates`, while `agenticUserTemplateManifest.json` links template
`9a2da06d-059c-4b40-910f-ca8e0a6b1730` to blueprint
`f1ae4991-0418-470b-96d5-7f7df43ab5d2`.

The canonical publication path is **Microsoft 365 admin center > Agents > All agents > Registry >
... > Add agent**. The **Add agent** command moves under **...** at narrower window widths. Do not
use **Settings > Integrated apps > Upload custom apps**. The live package was published to all
users on 2026-07-14 and the resulting registry item was verified as **Agent template** with Entra
agent ID `f1ae4991-0418-470b-96d5-7f7df43ab5d2`. Because the item initially remained
**Not activated**, the separate **Activate** wizard was completed for all users.

The blueprint is configured as **API Based** in Teams Developer Portal with the exact notification
endpoint from `hotel-agent-bridge-a365`:
`https://hotel-agent-bridge-a365.gentleforest-8d33b38e.westus.azurecontainerapps.io/api/messages`.
The agentic user instance was created directly by the administrator and automatically received a
Microsoft 365 Frontier for AI teammates license. It has **Azure AI Developer** at Foundry account
and project scope, **Cognitive Services User** and **Cognitive Services OpenAI User** at account
scope, and **Contributor** access to `HotelAgent.Workspace`.

Its Exchange mailbox grants **Read and manage (Full Access)** to
`mcasalaina.local@cam3652609.onmicrosoft.com` and
`aycabas.local@cam3652609.onmicrosoft.com`. Exchange accepted both assignments on 2026-07-14 and
reported a Full Access delegate count of two. This lets the operators inspect the agent inbox; it
does not grant Send As or Send on behalf.

The two earlier validation instances were deleted after the owned-blueprint instance
`Hotel Guest Services` became messageable and reached Foundry.

The separate Work IQ tenant policy was verified at **Agents > Tools > Work IQ MCP > Policies**.
**Allow write actions**, **Allow create**, **Allow partial update**, **Allow replace**, and
**Allow delete** are enabled. Although Microsoft documents a longer policy propagation window, this
tenant must be checked immediately and retried for no more than one minute. The setting only removes
the tenant-level Work IQ mutation block; the Hosted Agent remains deliberately read-only because its
server-specific positive allowlists exclude mutation tools.

Authoritative channel validation remains a real Teams DM. It must cover Mail, Teams, and cross-M365
reads and confirm that mutation attempts remain blocked. In this tenant, check permission and
configuration changes immediately and retry for no more than one minute; do not wait on longer
documentation estimates before investigating another cause. See `manifest/README.md` for the exact
current portal sequence and commands.

A 16-prompt live acceptance audit proved that all eight operational-data prompts invoked
`query_hotel_operations_data` and made the expected four-call MCP sequence against the exact
configured Fabric Data Agent endpoint. Foundry/Application Insights contains correlated root,
model, tool, and HTTP dependency spans with no orphan parents, no Agent 365 exporter HTTP 403, and
no token/credential patterns. Preview telemetry still omits agent version, hosted session ID, and
finish reason; it also retains full synthetic input/output and tool payloads. Add a payload-redacting
OpenTelemetry processor before using real customer data.

One folio request completed its Fabric tool and answer generation but then received a Foundry
storage 401 because `x-agent-foundry-call-id` no longer matched an active turn, causing caller HTTP
500. Identical retries completed successfully. Preserve the response/session IDs and retry before
treating this transient persistence race as an agent or Fabric defect.

The current `a365 query-entra` commands cannot resolve a Foundry-managed blueprint by the CLI's
conventional `<agent-name> Blueprint` display name. Audit this deployment by the live blueprint
client/principal IDs through Microsoft Graph instead of creating a duplicate `a365 setup`
blueprint.

The Bot Service must keep `publicNetworkAccess` enabled for the Teams channel. Disabling it
unconfigures channels other than Direct Line, even when the messaging endpoint itself is hosted by
Foundry.
