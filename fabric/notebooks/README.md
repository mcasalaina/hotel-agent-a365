# Notebooks

This folder now contains source-controlled notebook scaffolds for:

- initial load
- deterministic reset
- validation
- reservation action
- restaurant action
- billing dispute action
- service-request action
- aggregate refresh
- data-agent runtime publish

Each notebook is an actual `ipynb` definition that can be deployed through the Fabric REST API.
They intentionally fail loudly until the generated-schema handoff is complete. Typed parameter
contracts live in `contracts.json` and are validated by `scripts/fabric/`.
