# Supporting Azure infrastructure

This directory is an optional dedicated-resource fallback and is not the active deployment path.
The live development deployment successfully reuses the existing project Search and storage
resources, while `azure.yaml` uses the `microsoft.foundry` provider. Do not deploy this Bicep
unless the architecture is deliberately changed back to dedicated supporting resources.

`main.bicep` is a subscription-scope deployment that:

- creates `rg-hotel-agent-a365`;
- creates one East US 2 Azure AI Search service and one StorageV2 account;
- creates the private `hotel-docs` blob container;
- grants the Foundry project and Search managed identities the required data-plane roles;
- grants the azd deployment principal the roles required to load and verify content; and
- creates the `hotel-search` connection in the existing Foundry project.

The existing Foundry account, project, model deployments, Application Insights resource, and unrelated East US Search service are referenced or left unchanged.

The Search and storage resources use managed identities and disable local/key authentication. Resource names are generic and receive a deterministic uniqueness suffix.

## Agent 365 bridge

The current tenant-local bridge runs as Container App `hotel-agent-bridge-a365`
in `rg-hotel-agent-a365-2701`. It uses the existing Container Apps environment
`cae-mcasalaina-4iqs-2701`, registry `mcasalaina4iqs2701acr`, user-assigned identity
`id-hotel-agent-bridge-2701`, and Key Vault `kv-hotel-a365-2701`.
`agent365-bridge.bicep` declares the deployed Container App and references the managed environment
only by ARM ID. Configure the Agent 365 blueprint's API notification URL to the
bridge's actual HTTPS `/api/messages` endpoint. Bot Service Web Chat does not
supply the delegated Agent 365 user context required by Work IQ.

The voice template no longer creates a broad Foundry developer-role assignment.
Assign and verify project-scoped `Foundry User` separately for the proxy identity.
When reusing the deployed environment, pass `createManagedEnvironment=false`
and its actual resource group/name rather than creating a duplicate environment.

## Voice web application

`voice-web.bicep` is the active deployment template for the browser frontend and authenticated proxy.
It can create a dedicated environment or reuse an existing one, alongside a
scale-to-zero Container App and a dedicated user-assigned identity. The current
target app is in `rg-hotel-agent-a365-2701`. The template grants registry
`AcrPull` only. The deployed proxy's separate project-scoped `Foundry User`
assignment must be provisioned and verified explicitly. The template disables
insecure ingress, uses managed-identity registry authentication and supported
single-revision sticky sessions, and exposes `/api/health` for startup and
liveness probes.
