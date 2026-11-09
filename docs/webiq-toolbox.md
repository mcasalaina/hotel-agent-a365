# Web IQ and the hotel Foundry toolbox

The Contoso deployment uses a real Microsoft Web IQ resource, not Bing
Grounding or a generic web-search tool. The independent ARM template is
`config\webiq-contoso.arm.json`; it does not provision the shared Foundry
account, project, model, Search service, or Fabric estate.

Foundry objects must be created with `az`, `azd`, or supported CLI-driven
REST APIs. The Foundry portal is for verification only. Do not create,
connect, finish, or save Foundry objects through the portal.

## Weather-only Hotel policy

Web IQ is restricted to weather questions. Only the governed weather
adapter may invoke the actual `web` primitive; raw Web IQ tools must not
be exposed directly to the Hotel model. Do not use Web IQ for news,
generic search, hotel policies, amenities, reservation records, or
fallbacks for other IQ services. Authentication/schema discovery is
distinct from content retrieval.

All live content probes going forward must be weather-only. The earlier
official-document lookup evidence below predates this restriction and
must not be reused as a release smoke query. Release verification must
also include a non-weather Hotel request with **zero Web IQ calls**,
which the weather/hosted owners enforce and verify.

## Deployment prerequisites

- Target tenant: `b59f9d73-de1c-42c5-829a-e19034e2bcb3`.
- Target subscription: `d0aad12c-e3db-4b57-a951-d1b179e2516b`.
- Target resource group: `rg-mcasalainas-4iqs-zmansoor`.
- The user must explicitly accept the
  [Web IQ Terms of Use](https://www.microsoft.com/en-us/webiq/webiq-legal)
  before resource creation, portal onboarding, or API use.
- Web IQ requires a paid subscription; Azure credits do not pay for it.
- The subscription must have Web IQ enabled. Provider registration alone
  does not prove service entitlement.

## Resource definition and preflight

The [official Azure CLI deployment guide](https://learn.microsoft.com/web-iq/get-started/deploy-azure-cli)
specifies `Microsoft.WebIQ/accounts`, API `2026-06-01-preview`,
`WebIQ.Grounding`, SKU `G3`, and `statisticsEnabled: false`. Web IQ's
location is `global`, even though the shared Foundry project is in `eastus2`.

The requested name is `mcasalaina_webiq_contoso`. Do not replace underscores
without an actual service rejection and user approval. On November 8, 2026,
the following **non-provisioning** check succeeded with `validationLevel:
Provider`, `error: null`, and correlation ID
`f4728df4-0fc0-44c2-a624-0e2960aade37`:

```powershell
az deployment group validate `
  --subscription d0aad12c-e3db-4b57-a951-d1b179e2516b `
  --resource-group rg-mcasalainas-4iqs-zmansoor `
  --name webiq-contoso-preflight `
  --template-file .\config\webiq-contoso.arm.json `
  --validation-level Provider
```

This validates the exact requested name and definition, but is **not**
evidence that the resource exists, the subscription is entitled to use it,
or a callable Web IQ application has been onboarded.

After the user's explicit terms acceptance, the exact resource was created
and independently retrieved successfully on November 8, 2026:

```text
/subscriptions/d0aad12c-e3db-4b57-a951-d1b179e2516b/resourceGroups/rg-mcasalainas-4iqs-zmansoor/providers/Microsoft.WebIQ/accounts/mcasalaina_webiq_contoso
```

Deployment correlation ID: `da4b43b0-1846-44b4-9a12-4f5ecda16b66`.
The GET returned `provisioningState: Succeeded`, `WebIQ.Grounding`, `G3`,
`global`, and `statisticsEnabled: false`. This does not prove AppID
onboarding or callable tools.

After explicit terms acceptance, deploy the template in incremental mode:

```powershell
az deployment group create `
  --subscription d0aad12c-e3db-4b57-a951-d1b179e2516b `
  --resource-group rg-mcasalainas-4iqs-zmansoor `
  --name webiq-contoso `
  --template-file .\config\webiq-contoso.arm.json `
  --mode Incremental
```

Verify the resource rather than treating template outputs as proof:

```powershell
az resource show `
  --subscription d0aad12c-e3db-4b57-a951-d1b179e2516b `
  --resource-group rg-mcasalainas-4iqs-zmansoor `
  --name mcasalaina_webiq_contoso `
  --resource-type Microsoft.WebIQ/accounts `
  --api-version 2026-06-01-preview
```

## AppID, authentication, and project connection

The Azure resource handles metering and billing; applications call
`https://api.microsoft.ai/v3` directly. A Web IQ AppID is separate from both
the ARM resource and an Entra application/client ID.

Follow the [documented portal onboarding](https://learn.microsoft.com/web-iq/get-started/deploy-azure-portal):
sign into the target tenant/subscription, connect the actual resource, and
confirm the newly issued Web IQ AppID. Do not reuse a source-tenant AppID.

**Service-specific prerequisite:** The current public Web IQ deployment
and authentication documentation publishes AppID onboarding, API-key
creation, and Entra client-ID binding as Web IQ Customer Site/Profile
Management operations. The live ARM provider operation list exposes no
corresponding AppID-create, key-create, or client-binding action. The
public Web IQ SDK documents runtime calls, not these administrative
operations. Do not invent a hidden administrative API, treat the ARM
`internalId` as an onboarded AppID, or work around this through Foundry
portal creation. The migration owner explicitly authorized the documented
Web IQ Customer Site prerequisite as distinct from Foundry. That supported
service-specific onboarding was completed; Foundry objects remained
CLI-created.

The [authentication guide](https://learn.microsoft.com/web-iq/get-started/authentication)
supports an API key in the `x-apikey` header or app-only Entra authentication
with scope `https://api.microsoft.ai/.default`. Entra authentication requires
binding the application's client ID to the Web IQ AppID in Profile
Management. Additional bindings/access grants require separate approval.
Keep credentials in an approved secret manager or Foundry's connection
credential store; never put them in toolbox definitions or handoffs.

A native Foundry Web IQ toolbox tool requires a real Web IQ project
connection. Its [published SDK schema](https://learn.microsoft.com/javascript/api/@azure/ai-projects/webiqpreviewtoolboxtool)
is `type: web_iq_preview`, `project_connection_id`, optional `server_label`,
and optional `require_approval` (default `always`). Verify the connection's
actual category, target, and authentication through official connection
creation and subsequent listing. Do not infer a connection category or MCP
URL from the Web IQ REST API endpoint.

The [official Web IQ MCP integration](https://learn.microsoft.com/web-iq/integrations/mcp)
does explicitly publish `https://api.microsoft.ai/v3/mcp`, authenticated
with `x-apikey` or an Entra token. Its tools are `web`, `videos`, `browse`,
`news`, and `images`; the actual list is filtered by the AppID's allowed
services. This is a verified Web IQ endpoint, not a generic Bing
replacement. It still requires onboarded authentication. The `web` tool
uses the [Web Search parameters](https://learn.microsoft.com/web-iq/reference/web-search).
Live names/input schemas and a successful call must be discovered through
the completed toolbox; the documented tool names alone are not live
evidence.

### Verified target identity and connection

The target Web IQ billing account is linked to subscription
`d0aad12c-e3db-4b57-a951-d1b179e2516b` and the exact resource
`mcasalaina_webiq_contoso`. The Customer Site shows one Production profile,
`mcasalaina_webiq_contoso - Default`, with Web, Videos, Browse, News, and
Images enabled and a 15-QPS quota.

The project managed identity was independently resolved through
`az ad sp show`, then its exact **client ID** was bound in the Web IQ
Customer Site:

| Identity field | Value |
| --- | --- |
| Entra client ID | `ecf72e28-3deb-4e88-b83b-b6f5321ffc2e` |
| Object/principal ID | `a0af173f-0597-49b2-8dcc-ea66c0e4d1a9` |
| Service principal type | `ManagedIdentity` |

The bound client ID was subsequently visible in Profile Management after
a fresh page load. No API key was manually created or exported. Opening
the Web IQ Playground later generated its own default key automatically;
that service-managed key was not used by the Foundry connection.

With the isolated target azd environment selected, the following command
created the actual Foundry connection:

```powershell
azd ai connection create hotel-web-iq `
  --kind remote-tool `
  --target https://api.microsoft.ai/v3/mcp `
  --auth-type project-managed-identity `
  --audience https://api.microsoft.ai `
  --project-endpoint https://mcasalainas-4iqs-zmansoor-resource.services.ai.azure.com/api/projects/mcasalainas-4iqs-zmansoor `
  --no-prompt
```

`azd ai connection show hotel-web-iq` and an independent ARM GET verified
`category: RemoteTool`, `authType: ProjectManagedIdentity`,
`audience: https://api.microsoft.ai`, and the official MCP target.
The connection ARM ID is:

```text
/subscriptions/d0aad12c-e3db-4b57-a951-d1b179e2516b/resourceGroups/rg-mcasalainas-4iqs-zmansoor/providers/Microsoft.CognitiveServices/accounts/mcasalainas-4iqs-zmansoor-resource/projects/mcasalainas-4iqs-zmansoor/connections/hotel-web-iq
```

### Verified callable Web IQ transport

The working integration uses the documented standard MCP transport to
the **genuine Web IQ endpoint**, not a Bing substitute. Use the full ARM
connection ID and exact server label in the tool definition:

```json
{
  "type": "mcp",
  "server_label": "hotel-web-iq",
  "server_url": "https://api.microsoft.ai/v3/mcp",
  "project_connection_id": "/subscriptions/d0aad12c-e3db-4b57-a951-d1b179e2516b/resourceGroups/rg-mcasalainas-4iqs-zmansoor/providers/Microsoft.CognitiveServices/accounts/mcasalainas-4iqs-zmansoor-resource/projects/mcasalainas-4iqs-zmansoor/connections/hotel-web-iq",
  "allowed_tools": ["web"],
  "require_approval": "never"
}
```

For the explicitly approved public-document smoke request, `tool_choice:
"required"` produced response
`resp_04d63f09fcbbdd7e016af10d0878d081959db5e2689d9910e2` with an actual
`mcp_call(name="web", status="completed", error=null)`. A second successful
protocol-shape probe returned
`resp_0a05526b15237b37016af10dc6201481908d0c8555718a5082`.

Earlier preview-wrapper and short-connection-ID/different-label probes
returned downstream HTTP 403. Preserve the exact proven full-ID/label
pair; those probes do not isolate which change caused the error. The
actual project managed identity's token issuance to `MAIGroundingV3` was
also verified in Entra managed-identity sign-in logs.

The discovered `web` input schema requires `query: string` and exposes:

| Optional field | Advertised type/default |
| --- | --- |
| `contentFormat` | string |
| `language` | string, default `en` |
| `location` | string |
| `maxLength` | integer |
| `maxResults` | integer, default `10` |
| `region` | string, default `US` |
| `safeSearch` | string, default `strict` |

The tool's advertised `annotations` is empty. It does **not** advertise
`readOnlyHint`; a `read_only` approval selector therefore produces an
approval request, not execution. The exact `web` allowlist bounds the
automatic approval shown above. Do not broaden it to other verticals
without inspecting their schemas and semantics.

There is no advertised output schema. The native Responses `mcp_call`
output is a string containing adjacent, pretty-printed JSON objects,
not one JSON document and not one complete JSON object per line. The
observed first object has `webResults`, `riskLevel`, `querySignals`,
`instrumentationCitationBase`, and `traceId`; the second has
`structuredResponse`. Preserve the structured/citation information in
the consuming runtime. Protocol verification retained only schemas,
field names, counts, and IDs, never returned web content.

## Four-IQ toolbox

Create `hotel_foundry_toolbox` only after all four target integrations have
real project connections and reachable services:

| IQ | Toolbox representation | Required target evidence |
| --- | --- | --- |
| Foundry IQ | `mcp` | Target knowledge-base MCP endpoint and its project connection; exact discovered retrieval tool names |
| Fabric IQ | `fabric_iq_preview` | Published Fabric item endpoint, project connection, signed-in-user authentication, and exact discovered tool schemas |
| Work IQ | `mcp` | GA `https://workiq.svc.cloud.microsoft/mcp` connection with authorized delegated authentication |
| Web IQ | `mcp`, exact `web` allowlist | Actual Web IQ resource/profile, bound project identity, full `hotel-web-iq` connection ARM ID, and successful callable `web` tool |

The current [Work IQ guidance](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/work-iq)
recommends the GA MCP path for new agents and toolboxes. Do not silently use
the preview `work_iq_preview` A2A tool or treat legacy V2 mail/Teams
connections as equivalent. The [GA connection quickstart](https://learn.microsoft.com/microsoft-365/copilot/extensibility/work-iq/mcp/quickstart/foundry)
requires delegated OAuth, `WorkIQAgent.Ask`, admin consent, appropriate user
licensing, and a verified redirect URI. The Agent 365 owner supplies
approved target identity and consent configuration.

The actual `hotel-work-iq` project connection was created through
CLI-driven REST with `category: RemoteTool` and `authType: OAuth2`. It
uses the ordinary, single-tenant OAuth supporting app
`f2764a7c-a43e-4fe8-94fa-ce195df4863e` (object
`108ebd85-41fe-4c02-85ef-e9a3dc895517`), not an interactive
Agent Identity Blueprint. The exact scopes are
`api://workiq.svc.cloud.microsoft/WorkIQAgent.Ask` and `offline_access`.
Authorization, token, and refresh URLs use the target tenant
`b59f9d73-de1c-42c5-829a-e19034e2bcb3`; token and refresh paths are
`/oauth2/v2.0/token`.

One owned password was generated and immediately transferred to the
native connection credential store, solely in process memory. A
`finally` rollback guard removes only that newly created password if
transfer/readback fails. No secret was put in source, `.env`, command
arguments, chat, or logs. The owned key ID is
`0daa4c8f-785d-461c-9e02-a5979aa56f74`, expiring
`2027-02-06T23:54:41Z`; app readback confirmed exactly one password.

The native connection returned this actual `properties.redirectUrl`:

```text
https://global.consent.azure-apim.net/redirect/2dd23e78352a4957af57c19864da2361
```

The Agent 365 owner registered and read back that exact URL in the
supporting app's Web redirects. Do not invent a callback or overwrite
other redirects.
Content-free initialization produced response
`resp_062cc06ff9242dee016af10e60ef608195a7502be08b324053` with an
`oauth_consent_request`, not authenticated tool execution.

The real target operator subsequently completed the tenant-specific
OAuth flow; the provider displayed `Authentication successful`.
Authenticated response
`resp_0036ac7ef1618280016af10fc3240c819498c9b19951c12faa` advertised the
actual tools `retrieve`, `fetch_blob`, `ask`, `list_agents`,
`delete_entity`, `do_action`, `create_entity`, `get_schema`,
`search_paths`, `call_function`, `fetch`, and `update_entity`.

A separate, narrowly approved `fetch` invocation used exactly
`entityUrls: ["/me?$select=id,userPrincipalName"]`. Response
`resp_0004148ad707739a016af11042ca788196945b49c2551afdd3` contained one
successful `mcp_call(name="fetch")`, HTTP 200, and an actual tool-result
identity matching the approved target operator. Verification retained
only the match result and operational IDs, not the profile values or any
mail/file/meeting/Teams content.

The discovered `fetch` schema requires `entityUrls: string[]` and
optionally accepts nullable `agentId`. `get_schema` accepts nullable
`path`, `operationType`, `format`, and `agentId`; `call_function`
requires `functionUrl: string` and optionally accepts `jsonBody` and
nullable `agentId`. Their advertised annotations are empty, so do not
assume provider `readOnlyHint` metadata.

This proves the operator's native OAuth context, not an Agent 365
channel's agent-user identity. Inspect the actual advertised read/action
scopes before any grant expansion; don't use `Ask` as a substitute for
missing `Read` or `Act` authorization. No scope expansion was needed for
the successful `/me` probe.

The [Fabric IQ guide](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/fabric-iq)
requires published Fabric items. A Foundry Fabric data-agent connection
uses user context or an OAuth session; do not assume direct-endpoint
service-principal support makes app-only Foundry authentication valid.

The documented native user-context contract is `RemoteTool` with
`authType: UserEntraToken`, audience
`https://analysis.windows.net/powerbi/api`, and delegated scope
`https://analysis.windows.net/powerbi/api/DataAgent.Execute.All`. The
[user-delegation guide](https://learn.microsoft.com/azure/foundry/agents/how-to/configure-user-delegation#use-supported-scopes)
allows explicit scopes or its mapped default for this recognized target.
This audience differs from the direct Fabric MCP client's
`https://api.fabric.microsoft.com/.default`.

Target Graph readback verified Power BI Service application
`00000009-0000-0000-c000-000000000000`, service principal
`5e67384c-0715-498a-ae30-c20e0ae76ae5`, and enabled delegated permission
`DataAgent.Execute.All`, ID `c6756612-6853-4145-a661-90c1d045b2dc`.
No grant was changed during this discovery. Agent blueprint declaration,
inheritance, and any required consent belong to the identity owner.
Use real signed-in-user/call-ID context for the Foundry path; the
project MI's Viewer grant or a successful direct operator query does
not prove this connection can execute. If user context cannot be used,
the documented alternative is separate native OAuth, not app-only
substitution or reuse of the Work IQ connection's credentials.

The [toolbox guide](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox)
and `azd ai toolbox create --help` document JSON/YAML definitions with
`connections` and raw `tools`. Existing project connections are a
prerequisite. Raw `tools` supports native types such as `web_iq_preview`
without inventing a generic connection wrapper.

No partial toolbox or placeholder connection proves four-IQ integration.
After creation, inspect the toolbox's stored version and project connection
listing. Initialize its MCP endpoint using a Foundry token
(`https://ai.azure.com/.default`), enumerate `tools/list`, preserve exact
names and input schemas, and invoke Web IQ with a public, non-sensitive
weather query. Check actual success and citations without persisting the
response content. A toolbox can list a manifest despite missing runtime
permission; discovery alone is insufficient.

The version-specific MCP endpoint returned by the service is suitable for
staged validation. The unversioned endpoint follows the toolbox's published
default. Do not promote an unverified version. Approval configuration must
be enforced by the consuming hosted-agent runtime: the MCP endpoint itself
does not enforce `require_approval`.

`scripts\verify_hotel_toolbox.py` provides repeatable, content-free live
verification after the real toolbox exists. Supply the actual returned
MCP endpoint, target subscription, four observed IQ namespace prefixes
with `--expect-prefix`, and the exact discovered Web IQ primitive name
with `--web-tool`. It negotiates MCP, sends the initialized notification,
validates JSON/SSE response IDs and input-schema properties, requires all
four namespaces, and invokes only a public weather query. It prints tool
names and result counts, never credentials or returned web content.
Unit regressions cover the weather-only probe and token/content
non-disclosure. This operator-level transport check does not replace the
Hotel model's non-weather zero-WebIQ or Agent 365 channel-user tests.

## Web content handling

The Web IQ terms restrict storage, caching, derivative datasets, and using
returned content to train or evaluate models. Retain only content-free
operational evidence such as status, latency, resource/connection IDs,
tool schemas, and trace IDs. Preserve source attribution in the
user-facing grounding workflow. Web IQ supplies public-web facts; it must
not replace property-specific Foundry IQ knowledge or Fabric hotel records.

## Work IQ supporting billing plan

The documented [Power Platform billing-policy list API](https://learn.microsoft.com/rest/api/power-platform/licensing/billing-policy/list-billing-policies)
is callable through `az rest` with resource `https://api.powerplatform.com`.
The first target-tenant list returned `value: []`. The Microsoft 365 Cost
Management UI also showed first-time setup, not an existing spending
policy to reuse.

Current [Work IQ tenant setup](https://learn.microsoft.com/microsoft-365/copilot/extensibility/work-iq/enable-work-iq)
requires usage-based billing and an assigned user. The
[Copilot Cost Management API](https://learn.microsoft.com/microsoft-365/copilot/extensibility/api/admin-settings/cost-management/overview)
supports spending policies and group assignments through Microsoft Graph.
The existing Azure CLI Graph token returned `403 forbidden` on
`/beta/copilot/costManagement/spendingPolicies`; this is not evidence of
an empty Copilot spending-policy list. Requesting the policy-read scope
with Azure CLI returned `AADSTS65002` because the Microsoft-owned Azure
CLI app is not preauthorized for it. Ordinary tenant admin consent cannot
fix first-party preauthorization.

The documented [Microsoft 365 Cost Management setup](https://learn.microsoft.com/copilot/implement/usage-based-billing-copilot-credits-setup)
was therefore completed in the authorized Microsoft 365 admin center,
using the existing target SSO session. This is separate from the
Foundry portal; all Foundry connection/toolbox creation remains CLI-only.

The saved, enabled spending policy is:

| Setting | Verified value |
| --- | --- |
| Policy name | `Hotel Work IQ Contoso` |
| Policy ID | `a1ee4ea7-a7a2-446a-8373-786f3b796f19` |
| Service | Work IQ API for custom apps and agents only |
| Scope | Specific groups: `Hotel Work IQ Contoso users` |
| Audience group ID | `8a8549ed-0022-4c84-95b7-887b43b695d8` |
| Audience membership | Exactly the approved demo operator, independently checked with Azure CLI |
| Future service auto-enrollment | Off |
| Billing subscription | `d0aad12c-e3db-4b57-a951-d1b179e2516b` |
| Billing geography | United States |
| Resource group | `rg-mcasalainas-4iqs-zmansoor` |
| Spending limits | Documented `No limit` default |
| Alerts | Off |

The policy's persisted details URL exposes the actual ID:

```text
https://admin.cloud.microsoft/#/copilot/costmanagement/configuration?policyId=a1ee4ea7-a7a2-446a-8373-786f3b796f19
```

An independent ARM GET confirmed its real billing instrument:

```text
/subscriptions/d0aad12c-e3db-4b57-a951-d1b179e2516b/resourceGroups/rg-mcasalainas-4iqs-zmansoor/providers/Microsoft.PowerPlatform/accounts/a1ee4ea7-a7a2-446a-8373-786f3b796f19
```

A standalone Power Platform billing-policy prototype was not sufficient
for this Microsoft 365 user policy. Once the real mapping was verified,
that self-created, unused prototype and its Azure resource were removed
after checking that no environments or enabled product meters used it.
The final deployment retains only the actual Microsoft 365 billing
instrument, not a duplicate standalone plan.

Do not enable unrelated Power Platform meters or expand the audience.
Billing enablement and group membership do not prove a Work IQ tool call:
the Agent 365 owner still verifies delegated consent/inheritance, while
the hosted-agent owner verifies per-request caller-context propagation.
