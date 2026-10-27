# Voice frontend proxy

This aiohttp service hosts the production React build and relays authenticated browser calls to the
Foundry Hosted Agent `invocations_ws` endpoint.

The browser first sends its Entra access token to `POST /api/auth/session`. The proxy validates the
token's signature, issuer, tenant, audience, expiry, and delegated scope, then returns a bounded,
short-lived opaque handle. The handle can have only one active WebSocket connection at a time.
Foundry authentication uses `DefaultAzureCredential` and the `https://ai.azure.com/.default` scope.
No Entra or Foundry token is placed in a WebSocket URL or sent to the hosted agent.

Browser-session handles are process-local. Run one application process per replica and enable
Container Apps session affinity in single-revision HTTP ingress mode, as `infra/voice-web.bicep`
does. This keeps session creation, WebSocket upgrade and reconnect on the same replica. The
platform routing cookie is not an authentication token or the browser-session handle.
A replica restart loses its handles, so affected calls must start a fresh session. Multiple
application workers require a shared session store rather than ingress affinity alone.

## Local run

Install dependencies from the repository root:

```bash
make setup
```

Copy `.env.example` to `.env`, set the Entra and Foundry values, and run:

```bash
set -a; source web/backend/.env; set +a
make run-web
```

The proxy listens on port 8080 by default. Vite proxies `/api` and WebSocket traffic to that port.
The production container builds the frontend and serves it from the same origin.

## Endpoints

- `GET /api/config`: non-secret frontend configuration and feature flags.
- `POST /api/auth/session`: Entra bearer-token exchange for an opaque browser session.
- `GET /api/calls`: duplex PCM/JSON relay authenticated by the first WebSocket frame.
- `GET /api/health`: liveness response.

Build the container after exporting the public `VITE_ENTRA_*` values from
`web/frontend/.env.example`:

```bash
make web-docker-build
```
