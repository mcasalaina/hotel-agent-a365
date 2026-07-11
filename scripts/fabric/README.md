# Fabric deployment automation

This package contains the source-controlled deployment planner for the Microsoft Fabric slice
owned by this session:

- `fabric/topology.json` is the repository source of truth for the Fabric workspace,
  authoritative lakehouses, shortcut set, notebook inventory, and blocked future-artifact
  blueprints.
- `fabric/notebooks/*.ipynb` are deployable notebook definitions with typed parameter contracts
  in `fabric/notebooks/contracts.json`.
- `scripts/fabric/cli.py` validates the topology, optionally discovers remote IDs, writes an
  uncommitted deployment-state file, and can create-or-update the foundational lakehouse and
  notebook artifacts through Fabric REST APIs.

## Typical usage

Local validation only:

```bash
python3 scripts/fabric/cli.py validate
```

Dry-run plan with source discovery:

```bash
python3 scripts/fabric/cli.py plan \
  --source-root data/generated \
  --state scripts/fabric/deployment-state/fabric-state.json
```

Remote plan that also discovers current workspace and item IDs:

```bash
python3 scripts/fabric/cli.py plan \
  --config scripts/fabric/config.example.json \
  --discover-remote
```

Apply when the generated-schema handoff is complete:

```bash
python3 scripts/fabric/cli.py apply \
  --config scripts/fabric/config.example.json \
  --execute
```

Without `--execute`, the `apply` command performs remote discovery and writes a dry-run plan
without creating or updating Fabric resources.

The CLI never writes committed state. Remote discovery and apply results go to the
gitignored `scripts/fabric/deployment-state/` folder.
