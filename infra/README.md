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

## Voice web application

`voice-web.bicep` is the active deployment template for the browser frontend and authenticated proxy.
It deploys an East US 2 consumption-based Container Apps environment, a scale-to-zero Container App,
and a dedicated user-assigned identity in `rg-hotel-agent-a365`. The identity receives only
`AcrPull` on the existing registry and `Azure AI Developer` on the existing Foundry project. The
template disables insecure ingress and environment log forwarding, uses managed-identity registry
authentication, and exposes `/api/health` for startup and liveness probes.
