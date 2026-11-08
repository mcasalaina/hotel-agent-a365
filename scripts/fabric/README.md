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
capacity is accessible, Active, and in East US 2 before its first write.
No command creates or resumes a capacity automatically.

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
or rewrites native sources or model-owned Prep for AI. After publication it compares the published
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

The demo business clock is fixed at **2026-11-08**, not the wall clock. Source
dates and linked fixtures were shifted coherently by 68 days from the previous
2026-09-01 baseline. The family stay is 2026-11-17 through 2026-11-19; strict
future/past classifications exclude records on the boundary.
