# Deployment

No cloud resources are created or modified by the repository bootstrap.

## Existing Foundry binding

The azd project connects to the existing Microsoft Foundry project through `services.ai-project.endpoint` in `azure.yaml`. The active azd environment must provide:

- `AZURE_AI_PROJECT_ENDPOINT`
- `AZURE_AI_PROJECT_ID`
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`

Start from `config/azd.env.example`. The expected model deployment is `gpt-5.4-mini`. The project ARM ID is required by `azd ai agent init --project-id` or the active azd environment, but it is not treated as a secret.

Do not run `azd init -t` in this non-empty repository. Do not run `azd provision`, `azd deploy`, or `azd up` until implementation is complete, `.azure/deployment-plan.md` is marked `Ready for Validation`, and the `azure-validate` workflow passes.

## Predeployment checks

```bash
make check
```

The naming check is mandatory before every deployment. It scans technical configuration fields and fails when the fictional customer brand is used in Azure, Foundry, Fabric, Agent 365, package, environment, identity, URL, or item names. Customer-facing Markdown and generated business data are intentionally outside that technical scan.

## Hosted Agent contract

- Service name: `hotel-servicing-agent`
- Current protocol: `responses` version `2.0.0`
- Container resources: 1 CPU and 2 GiB memory
- Startup command: `./startup.sh`
- Model deployment: configured through `AZURE_AI_MODEL_DEPLOYMENT_NAME`
- Project endpoint: injected by Foundry in the hosted container

Phase 3 adds `invocations_ws` version `1.0.0` to both `azure.yaml` and `src/hotel-servicing-agent/agent.manifest.yaml`, then adds the WebSocket adapter without replacing the shared orchestration.
