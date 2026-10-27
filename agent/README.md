# Agent 365 host parity

This directory reserves the Agent 365 host, authentication, notification, OBO, and diagnostics surface. The bootstrap contains only safe examples. Live IDs, generated CLI configuration, tokens, and tenant-specific values must remain outside source control.

The bridge deployment uses Container App `hotel-agent-bridge-a365`. Its blueprint credential is
Key Vault secret `agent365-blueprint-client-secret`; the Container App references it as
`blueprint-secret`. `applicationinsights-connection-string` is referenced as `appinsights-cs`.
Supply the target Foundry project endpoint explicitly when deploying
`infra/agent365-bridge.bicep`; it has no source-tenant default.

The bridge passes the Agent 365 exchanged user token directly to Foundry. It must not also send
`x-ms-user-identity`; that header is for service-identity delegation and requires the separate
Foundry `UserIdentityImpersonation/action` permission.

Build from this directory so Azure Container Registry uses this bridge's Dockerfile, not the
repository-root hosted-agent Dockerfile. The default package source is the approved corporate
feed; `PIP_INDEX_URL` is an overridable build argument and must never contain credentials.
The build context excludes local environment and generated configuration files.

Agent 365 notifications, observability, and runtime use the corresponding stable `1.0.0`
release, with the hosting/activity/authentication family aligned at stable `1.2.0`. The approved
feed lists the older `1.0.0.dev17` packages but returns HTTP 404 for their wheel metadata.
The stable release metadata resolves from the approved feed without changing package sources
or using the blocked public artifact host.

The image build keeps a disposable package cache across bounded installation retries to handle
HTTP 429 responses from the approved feed. It removes the cache before completing the image.
The stable Agent 365 and hosting SDK pins remain unchanged.

Conversation state is process-local. Restarting the active bridge revision clears the buffer
without deleting any Teams history. `/api/health` is a liveness check; its `initialized` field is
not proof that the downstream Foundry invocation succeeded. Verify the startup connectivity log
and a real authenticated Agent 365 turn before declaring runtime readiness.

## Initial target bridge deployment

Verified on 2026-10-27 in `cam3652701`:

- Base URL: `https://hotel-agent-bridge-a365.nicewater-f4997702.eastus2.azurecontainerapps.io`.
- Messaging URL: `https://hotel-agent-bridge-a365.nicewater-f4997702.eastus2.azurecontainerapps.io/api/messages`.
- Revision: `hotel-agent-bridge-a365--eczr79s`, active, Healthy, 100% traffic.
- Replica: Running and ready, zero restarts; minimum and maximum replica counts are both 1.
- Ingress: external, HTTPS-only, automatic transport, target port 3978.
- Image: `mcasalaina4iqs2701acr.azurecr.io/hotel-agent-bridge:2701-20261027`.
- Digest: `sha256:de757e7bd528d600a7136053083129aa5a61b60c5ff0ebda4c958e0ba6f1572c`.
- `/api/health`: HTTP 200, initialized.
- Unauthenticated `POST /api/messages`: HTTP 401.
- The initial downstream Foundry protocol request returned HTTP 404. Verify the target Hosted
  Agent deployment and route before authenticated Teams acceptance; bridge liveness is not
  downstream readiness.

The initial protocol failure above is historical. Bridge `em4` subsequently
delivered exactly one correct reservation reply to the fresh 7c email. Its trace
verified exact-message sender retrieval, the matching Fabric reservation and
property-specific Foundry IQ retrieval. Outgoing To/Cc headers remain unverified.

The current target revision is `hotel-agent-bridge-a365--0000005`, using image
`mcasalaina4iqs2701acr.azurecr.io/hotel-agent-bridge:2701-20261027-em4`.
Minimum and maximum replicas remain 1. Preserving this source does not redeploy
or restart that runtime.

Notifications run statelessly. They neither read, write nor clear saved Teams
conversation history. Teams turns continue to retain their own process-local
history. Incoming notification compatibility normalizes only the known
`productInfo` field casing before the SDK authenticates and processes the request.

Only immediately before an approved Teams acceptance test, resolve the actual
ready revision before resetting its process-local conversation buffer:

```bash
revision=$(az containerapp show \
  --subscription 8e2d733e-27bd-4df5-8be5-d6a540529106 \
  --resource-group rg-hotel-agent-a365-2701 \
  --name hotel-agent-bridge-a365 \
  --query properties.latestReadyRevisionName -o tsv)
test -n "$revision" && az containerapp revision restart \
  --subscription 8e2d733e-27bd-4df5-8be5-d6a540529106 \
  --resource-group rg-hotel-agent-a365-2701 \
  --name hotel-agent-bridge-a365 \
  --revision "$revision"
```

This command is documentation, not an instruction to restart during source
preservation. It does not delete Teams messages.
