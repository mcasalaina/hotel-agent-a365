# Deployment

The live development deployment uses the existing Foundry project, Search service, model
deployments, and storage account. Repository commands remain operator-invoked and do not deploy
implicitly.

## Foundry binding configuration

The azd project binds to the existing project through its active environment. The environment must
provide:

- `FOUNDRY_PROJECT_ENDPOINT`
- `AZURE_AI_PROJECT_ENDPOINT`
- `AZURE_AI_PROJECT_ID`
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`

Start from `config/azd.env.example`. The expected model deployment is `gpt-5.4-mini`. The project ARM ID is required by `azd ai agent init --project-id` or the active azd environment, but it is not treated as a secret.

Do not run `azd init -t` in this non-empty repository. The Hosted Agent service uses Foundry
direct-code deployment (`python_3_13`, remote dependency resolution); it does not require a local
Docker daemon.

## Predeployment checks

```bash
make check
```

The naming check is mandatory before every deployment. It scans technical configuration fields and fails when the fictional customer brand is used in Azure, Foundry, Fabric, Agent 365, package, environment, identity, URL, or item names. Customer-facing Markdown and generated business data are intentionally outside that technical scan.

## Foundry IQ setup and verification

These commands operate on the approved endpoints configured in the local environment. They do not
deploy the Hosted Agent.

```bash
make setup
.venv/bin/python scripts/setup_foundry_iq.py --dry-run
.venv/bin/python scripts/setup_foundry_iq.py
.venv/bin/python scripts/verify_deployment.py --property-id HTL-001 --as-of 2026-04-10
make check
```

`setup_foundry_iq.py` uses `DefaultAzureCredential` for Azure OpenAI embeddings and Search RBAC.
Set `AZURE_SEARCH_ADMIN_KEY` only when local key authentication is explicitly approved; it is never
logged. `AZURE_OPENAI_API_KEY` is an optional fallback for Search vectorization and answer synthesis
when the Search managed identity path is unavailable. Search stores this value encrypted and GET
responses redact it. To archive source Markdown in addition to indexing it, set both
`FOUNDRY_IQ_BLOB_CONTAINER` and `AZURE_STORAGE_ACCOUNT_URL`. Blob archival is optional.

Before running setup against provisioned resources, assign the Search service managed identity
**Cognitive Services OpenAI User** for vectorization and **Cognitive Services User** for
knowledge-base query planning on the Foundry account. The local setup identity needs permission to
manage Search indexes,
knowledge sources, and knowledge bases, and to upload index documents. The Hosted Agent/project
managed identity needs **Search Index Data Reader** on the Search service for retrieval. Assign the
equivalent reader role to any separate project or agent identity that performs retrieval. Validate
these assignments in the target subscription; this repository does not assert that any resource or
role assignment exists.

## Hosted Agent contract

- Service name: `hotel-servicing-agent`
- Current protocol: `responses` version `2.0.0`
- Container resources: 1 CPU and 2 GiB memory
- Deployment: Python 3.13 source ZIP with remote dependency resolution
- Local/container startup command: `./startup.sh`
- Model deployment: configured through `AZURE_AI_MODEL_DEPLOYMENT_NAME`
- Project endpoint: injected by Foundry in the hosted container
- Search endpoint and knowledge-base name: injected from azd environment values

Phase 3 adds `invocations_ws` version `1.0.0` to both `azure.yaml` and `src/hotel-servicing-agent/agent.manifest.yaml`, then adds the WebSocket adapter without replacing the shared orchestration.

## Live development deployment

- Search indexes: `hotel-properties-index`, `hotel-policies-index`,
  `hotel-dining-local-index`, and `hotel-operations-index`
- Knowledge sources: one `hotel-*-ks` source per index
- Knowledge base: `hotel-foundryiq`
- Source archive: 95 Markdown blobs in `hotel-docs`
- Hosted Agent: `hotel-servicing-agent`, active version 4
- Agent Search access: **Search Index Data Reader**

The live verification covers direct Search counts, answer synthesis with citations, dated notices,
chain policy grounding, dining guidance, unsupported-fact handling, and property isolation.
