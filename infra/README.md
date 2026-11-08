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

## Dedicated native Foundry IQ

`foundry-iq.bicep` is a narrower resource-group-scope migration/demo deployment.
It references an explicitly supplied existing Foundry account/project and never
creates a model, hosted agent, toolbox, or Fabric resource. It provisions one
Standard S1 Search service, a private Standard_LRS `hotel-docs` archive, and an AAD
`hotel-search-connection` using the shared project-connection module.

The project receives only Search Index Data Reader. The Search identity receives
Cognitive Services User on the existing account for chat query planning, not
an embedding/vectorization role. The setup principal receives Search Service
Contributor and Search Index Data Contributor on Search, and Storage Blob Data
Contributor scoped to the archive container. A separately created hosted identity
must receive its own approved Search Index Data Reader grant.

Supply verified target account/project/principal parameters, review deployment
validation and what-if, and obtain cost/RBAC approval before deploying. Select
`--retrieval-mode native --check-canonical` in the document setup helper after
integrating final source branding/date changes; use `--verify-only` to compare
indexed IDs, content and source metadata with the frozen corpus.
`searchLocation` can override only Search's region if regional capacity is
unavailable; the archive's `location` and existing Foundry resources stay unchanged.
Set `deployArchive=false` when the archive already exists, including a retry after
partial deployment, to preserve its network/security properties and existing grants.

An enforced tenant governance policy can force storage public network access off,
preventing archive uploads when no private access path exists. Prefer a compliant
private path. For a demo with an explicitly authorized, verified policy exception,
`demoArchivePolicyException=true` opts **only the archive account** into
`SecurityControl=Ignore`. The default is false; do not apply the tag to a resource
group, root policy, Search, Key Vault, or unrelated resources.

Before opting in, read the actual enforced policy and initiative to confirm the
exception tag/value. Merge the tag into an existing account with `az tag update
--operation Merge`, never replace its tags. Retain the account's existing tags in
`archiveTags` for any account redeployment. Authenticated public network access
does not enable anonymous blobs or shared keys: those remain disabled, the
`hotel-docs` container stays private, and uploads use Entra/RBAC. Read back the
effective tag/network/authentication state after policy processing and verify
actual archive content rather than assuming the exception succeeded.

## Voice web application

`voice-web.bicep` is the active deployment template for the browser frontend and authenticated proxy.
It deploys an East US 2 consumption-based Container Apps environment, a scale-to-zero Container App,
and a dedicated user-assigned identity in `rg-hotel-agent-a365`. The identity receives only
`AcrPull` on the existing registry and `Azure AI Developer` on the existing Foundry project. The
template disables insecure ingress and environment log forwarding, uses managed-identity registry
authentication, and exposes `/api/health` for startup and liveness probes.
