# Fabric deployment automation

The deployment toolchain in this folder plans and applies the Phase 1 Fabric slice without writing committed state.

## Supported item order

1. Workspace
2. `HotelOperations` lakehouse
3. `HotelGuestServices` lakehouse + limited `ops_` shortcuts
4. All notebooks
5. `HotelOperationsModel` semantic model
6. `HotelOperationsReport` report
7. `HotelOperationsOntology` ontology
8. `HotelOperationsAgent` draft data agent

## Commands

The committed topology has no capacity ID. A new workspace requires an explicitly
selected target capacity via `--capacity-id` (or `capacityId` in private config).
An existing workspace must already be assigned. Live apply verifies that the
capacity is accessible, Active, and in the topology's declared region before its first write.
No command creates or resumes a capacity automatically.

The target demo uses **Central US** for Fabric because its approved subscription
has available CU quota there. Foundry remains in East US 2. Region selection is
per capacity/topology, not an Azure CLI or azd global default.

Use the user's requested native Fabric CLI authentication:

```powershell
fab auth login --tenant "<target-tenant-id>"
fab api capacities
fab api workspaces
.\.venv\Scripts\python.exe -m scripts.fabric.cli plan --auth-mode fab `
  --tenant-id "<target-tenant-id>" --discover-remote --capacity-id "<approved-capacity-id>" `
  --source-root "<canonical-source-root>" --state "<private-state-path>"
```

`--auth-mode fab` invokes `fab api` for the supported REST operations, checks the
effective tenant before each request, preserves HTTP errors and response headers,
and never exports a bearer token. `validate` and offline `plan` do not authenticate.
Discovery follows pagination. An HTTP `UserNotLicensed` error is a licensing
blocker, not an empty estate; activate the operator's entitlement through the
supported Fabric experience before proceeding. Fill `tenantId` and `capacityId`
in a private copy of the example config, never with a source-tenant binding.

For unattended or built-in-browser-only work, use the existing target Azure CLI
session with `--auth-mode azure-cli` (the deployment CLI's default):

```powershell
az account show --query tenantId -o tsv
.\.venv\Scripts\python.exe -m scripts.fabric.cli plan --auth-mode azure-cli `
  --discover-remote --capacity-id "<approved-capacity-id>" `
  --source-root "<canonical-source-root>" --state "<private-state-path>"
```

First verify that the displayed tenant is the requested target. Native `fab api`
can start MSAL's interactive system-browser flow when silent token renewal fails,
even if `fab auth status` reports an authenticated account; `--auth-mode fab` is
not a noninteractive guarantee. Do not run login commands or switch shared
account defaults automatically. If cached noninteractive authentication fails,
report the error and use the approved built-in browser for required user sign-in.

Validate the local definitions:

```bash
.venv/bin/python scripts/fabric/cli.py validate
```

Produce a dry-run plan with local source discovery:

```bash
.venv/bin/python scripts/fabric/cli.py plan   --source-root data/generated   --state scripts/fabric/deployment-state/fabric-state.json
```

Apply live changes only when you are ready:

```bash
.venv/bin/python scripts/fabric/cli.py apply   --config scripts/fabric/config.example.json   --execute
```

The CLI never publishes the Data Agent runtime. After a successful apply, run the
`HotelDataAgentRuntimePublish` notebook explicitly. The notebook requires independently reviewed
native-readiness evidence bound to the exact draft, then verifies existing source bindings,
governed tables, descriptions, and examples with `fabric-data-agent-sdk`. It never adds, removes,
or rewrites native sources or model-owned Prep for AI. Both SQL sources require genuine retained
Topics readback evidence from the native UI or SDK. Ontology context and model-owned Prep for AI
are optional enhancements, not prerequisites for a working Operations/Guest Services/model
Data Agent. Omit their evidence when they are not configured; if supplied, it must still pass
its artifact, hash, and native-verification checks. Never invent a receipt or claim that optional
configuration is present. After publication it compares the published
configuration with staging and calls the published Data Agent MCP endpoint directly, failing
unless every isolation fixture passes. Prepared Topics and ontology context are not acceptance
evidence.

Generic apply refuses full-definition replacement of an existing Data Agent or
semantic model before any remote writes or deployment-state save in an existing
workspace. Those replacements cannot preserve reviewed native Data Agent settings
or model-owned AI Instructions, AI Schema, and Verified Answers. Use the supported
native-preserving configuration workflow, Power BI Prep for AI for model-owned
configuration, and the readiness-gated publication notebook instead. There is no
override. New-item creation, unrelated existing items, and non-native artifact
updates retain their existing behavior. A dry-run remains a non-mutating plan,
not authorization to replace protected items.

Every `validate`, `plan`, and `apply` command runs the repository Data Agent quality gates before
remote discovery or mutation. A deployable Data Agent must provide:

- substantial source descriptions;
- a complete data dictionary in every source instruction for all selected tables and fields;
- at least ten example queries per source;
- detailed global routing for every source;
- an acronym compendium containing the artifact's required domain and organization-specific acronyms;
- deterministic business fixtures with expected answer terms; and
- direct, post-publication isolation coverage for every business fixture.

The reusable thresholds and fixture contracts are declared in the Data Agent's
`quality-gates.json`; the validator does not encode hotel-specific fixture values.

For a fresh workspace, use `apply --foundation-only` first to create the two
lakehouses and bind all notebooks without prematurely creating downstream items
or shortcuts to tables that do not exist. Upload the canonical source to
`HotelOperations/Files/data/generated` and its matching business fixtures to
`Files/data/fixtures`. Run `HotelInitialLoad` with its `source_root` set to that
Operations OneLake ABFSS path; it writes each authoritative table to the correct
lakehouse. Run aggregate refresh and validation, then apply the downstream
definitions. Governed `ops_` shortcuts are managed through the supported OneLake
shortcut API, never a Lakehouse `updateDefinition` call.

The retained legacy graph datasource in the declarative draft is not native
ontology context. Creating this draft does not prove native configuration or
publication readiness. Mount ontology context through the documented Sources
experience and retain its actual context export; do not register it as a fourth
SQL/DAX execution source.

Use `--exclude-blueprint dataAgent` when deploying the downstream model, report
and ontology while creating/configuring the Data Agent through supported native
APIs. Repeating `--exclude-blueprint` explicitly leaves those artifacts unchanged;
it does not bypass the existing-native replacement guard for requested updates.
All source quality gates still run before exclusions are applied.
Use `--artifacts-only` for that downstream phase to leave the already loaded
lakehouses and bound notebooks unchanged.

After creating the semantic model, submit its initial refresh/framing with
`fab api groups/{workspaceId}/datasets/{modelId}/refreshes -A powerbi -X post -i '{"notifyOption":"NoNotification"}'`.
Read that same endpoint with `-X get` and require a completed refresh before
checking DAX metadata or report queries. A newly created Direct Lake definition
can export every table while its query schema remains unframed; do not replace
the definition to repair this initial state. This model has 9 tables, 63 authored
columns and 21 measures; `INFO.VIEW.COLUMNS()` also includes 9 engine-generated
`RowNumber` columns, for 72 total.

Serialize native Data Agent draft writes, including schema elements, instructions,
examples, global settings and Topics. Concurrent writes can conflict on the
underlying OneLake lease (`LeaseAlreadyPresent`); retry only that specific conflict
with a bounded delay and preserve completed updates and accepted example IDs.

The demo business clock is fixed at **2026-11-08**, not the wall clock. Source
dates and linked fixtures were shifted coherently by 68 days from the previous
2026-09-01 baseline. The family stay is 2026-11-17 through 2026-11-19; strict
future/past classifications exclude records on the boundary.
