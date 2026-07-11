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

The CLI never publishes the Data Agent runtime. After a successful apply, run the `HotelDataAgentRuntimePublish` notebook explicitly.
