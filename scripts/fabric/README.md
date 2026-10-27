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
