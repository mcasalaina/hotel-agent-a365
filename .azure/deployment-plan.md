# Azure Deployment Plan

## Status

In Progress - repository and application preparation

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
- New generic Azure resource group: `rg-hotel-agent-a365`
- New or project-default generic Azure AI Search service with four indexes and one Foundry IQ knowledge base.
- New generic storage account/container for knowledge documents.
- Containerized Foundry Hosted Agent `hotel-servicing-agent`.
- Generic Agent 365 host/web resources needed by the approved publish path.
- Existing Application Insights associated with the target Foundry resource for tracing.

## Fabric scope

One Fabric workspace, `HotelAgent.Workspace`, with two authoritative lakehouses:

- `HotelOperations`: properties, rooms, room types, amenities, inventory, rates, outlets, associates, maintenance requests, and work orders.
- `HotelGuestServices`: guests, reservations, stays, dining reservations, folios, disputes, special requests, confirmations, idempotency records, and customer-facing audit events.

The Fabric data agent connects directly to both lakehouses to demonstrate cross-source unification. A Direct Lake semantic model uses limited source-controlled OneLake shortcuts from `HotelGuestServices` to required `HotelOperations` tables; no third lakehouse or Azure SQL database is created.

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
