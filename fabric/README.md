# Microsoft Fabric artifacts

This directory now contains the source-controlled Phase 1 foundation for Microsoft Fabric:

- `topology.json` is the canonical workspace, lakehouse, shortcut, and notebook inventory.
- `notebooks/` contains deployable notebook definitions plus typed parameter contracts.
- `semantic-model/`, `report/`, `ontology/`, and `data-agent/` contain schema-safe blueprints for
  later artifacts that depend on the generated-schema handoff.

Deployment automation lives in `scripts/fabric/` and uses Fabric REST APIs plus item-definition
payloads. The planner supports local validation, remote discovery, dry-run planning, idempotent
create-or-update behavior, LRO polling, and gitignored deployment-state output.
