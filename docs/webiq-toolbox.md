# Web IQ and the hotel Foundry toolbox

The Contoso deployment uses a real Microsoft Web IQ resource, not Bing
Grounding or a generic web-search tool. The independent ARM template is
`config\webiq-contoso.arm.json`; it does not provision the shared Foundry
account, project, model, Search service, or Fabric estate.

Foundry objects must be created with `az`, `azd`, or supported CLI-driven
REST APIs. The Foundry portal is for verification only. Do not create,
connect, finish, or save Foundry objects through the portal.

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

The bound client ID was subsequently visible in Profile Management.
No API keys were created.

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

This verifies the connection configuration, not a native toolbox tool
call. Keep callable-tool validation separate from connection creation.

## Four-IQ toolbox

Create `hotel_foundry_toolbox` only after all four target integrations have
real project connections and reachable services:

| IQ | Toolbox representation | Required target evidence |
| --- | --- | --- |
| Foundry IQ | `mcp` | Target knowledge-base MCP endpoint and its project connection; exact discovered retrieval tool names |
| Fabric IQ | `fabric_iq_preview` | Published Fabric item endpoint, project connection, signed-in-user authentication, and exact discovered tool schemas |
| Work IQ | `mcp` | GA `https://workiq.svc.cloud.microsoft/mcp` connection with authorized delegated authentication |
| Web IQ | `web_iq_preview` | Actual Web IQ resource, onboarded AppID, verified native project connection, and a successful callable tool |

The current [Work IQ guidance](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/work-iq)
recommends the GA MCP path for new agents and toolboxes. Do not silently use
the preview `work_iq_preview` A2A tool or treat legacy V2 mail/Teams
connections as equivalent. The [GA connection quickstart](https://learn.microsoft.com/microsoft-365/copilot/extensibility/work-iq/mcp/quickstart/foundry)
requires delegated OAuth, `WorkIQAgent.Ask`, admin consent, appropriate user
licensing, and a verified redirect URI. The Agent 365 owner supplies
approved target identity and consent configuration.

The [Fabric IQ guide](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/fabric-iq)
requires published Fabric items. A Foundry Fabric data-agent connection
uses user context or an OAuth session; do not assume direct-endpoint
service-principal support makes app-only Foundry authentication valid.

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
grounding query. Check actual success and citations without persisting the
response content. A toolbox can list a manifest despite missing runtime
permission; discovery alone is insufficient.

The version-specific MCP endpoint returned by the service is suitable for
staged validation. The unversioned endpoint follows the toolbox's published
default. Do not promote an unverified version. Approval configuration must
be enforced by the consuming hosted-agent runtime: the MCP endpoint itself
does not enforce `require_approval`.

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
