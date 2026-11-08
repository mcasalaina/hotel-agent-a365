# Web IQ and the hotel Foundry toolbox

The Contoso deployment uses a real Microsoft Web IQ resource, not Bing
Grounding or a generic web-search tool. The independent ARM template is
`config\webiq-contoso.arm.json`; it does not provision the shared Foundry
account, project, model, Search service, or Fabric estate.

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
