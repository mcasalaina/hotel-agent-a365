# Lyrenza Hotels Contact Center — Web Frontend

A React 19 + TypeScript + Vite single-page app that simulates a live hotel contact-center agent
desk for the fictional **Lyrenza Hotels** brand. Every guest, reservation, and folio detail shown
in this app is **synthetic** demo data; it is not connected to a real hotel chain or real customer
records.

This app is the browser client for Phase 3 of the project. It never talks to Foundry directly. It
connects only to the Python proxy in `web/backend`, which is deployed with the production frontend.

## Requirements

- Node.js 20+ and npm
- A Microsoft Entra app registration (public client / SPA) for sign-in, and a backend proxy that
  implements the endpoints described below

## Getting started

```bash
cd web/frontend
npm install
cp .env.example .env.local   # fill in your Entra + backend values
npm run dev
```

The dev server prints a local URL (default `http://localhost:5173`). Sign-in requires the Entra
redirect URI in `.env.local` to exactly match the one registered on the app registration.

## Environment configuration

All configuration is supplied at build/dev time via Vite environment variables — see
[`.env.example`](./.env.example) for the full list and description of each variable:

| Variable                    | Purpose                                                              |
| ---------------------------- | --------------------------------------------------------------------- |
| `VITE_ENTRA_CLIENT_ID`       | Public client (SPA) application ID registered in Entra                |
| `VITE_ENTRA_AUTHORITY`       | Entra authority URL (tenant-specific or `common`)                     |
| `VITE_ENTRA_REDIRECT_URI`    | Redirect URI registered for this SPA                                  |
| `VITE_ENTRA_API_SCOPE`       | Delegated scope(s) requested for the backend API                      |
| `VITE_BACKEND_BASE_URL`      | Origin of the private backend proxy; leave empty for same-origin/relative paths |

No secrets are ever read from these variables — only public client identifiers and URLs. Never
commit a filled-in `.env` or `.env.local` file; both are already covered by the repository
`.gitignore`.

## Authentication

Sign-in uses [`@azure/msal-browser`](https://www.npmjs.com/package/@azure/msal-browser) with the
Authorization Code + PKCE flow (the only interactive flow msal-browser implements for SPAs).
Tokens are kept **in memory only**:

- MSAL's `cacheLocation` is set to `"memoryStorage"` (see `src/auth/msalConfig.ts`), so MSAL never
  writes tokens or account state to `localStorage`, `sessionStorage`, or cookies.
- No application code in this project persists the Entra access token, ID token, or the opaque
  call-session handle to any Web Storage or cookie. Both live only in React/JS memory for the
  lifetime of the tab.
- Reloading the page requires a fresh sign-in (interactive or silent-iframe); this is an
  intentional trade-off of the "tokens in memory only" requirement.

Sign-in is required before any text or voice call session can start — there is no anonymous mode
(`src/App.tsx`'s `AuthGate` enforces this).

## What the app does

The main screen simulates a live contact-center call:

- Signed-in user summary and sign-out control
- Connection/call state badge (idle, connecting, active, reconnecting, ended) with a reconnect
  indicator and elapsed-call timer
- Voice mode: microphone capture with mute control; Text mode: a typed message input
- Prerecorded mode: upload an uncompressed 16-bit PCM WAV prompt for repeatable live testing
- A live, screen-reader-friendly transcript of the caller's and agent's turns
- A friendly activity timeline of progress/tool/data-source events (no raw backend errors or
  internal details are ever shown)
- Confirmation cards for actions the agent wants to take, with Approve/Decline controls
- Reservation/folio/request result cards summarizing outcomes
- A final call disposition banner
- A "Run headless demo" mode that plays a fully scripted, synthetic call — including a generated
  silent PCM audio frame and typed text turns — entirely offline, without microphone permission or
  any network connection. Useful for demos, screenshots, and exercising the UI without a live
  backend.

## Audio pipeline

Microphone audio is captured with the Web Audio API via an `AudioWorkletProcessor`
(`public/audio/pcm-capture-processor.js`), then resampled on the main thread to the wire format:
**raw signed 16-bit little-endian PCM, mono, 24 kHz**, with no header or envelope
(`src/lib/pcm.ts`). Browsers are not required to honor a requested `AudioContext` sample rate, so
capture happens at whatever rate the browser grants and is resampled afterward. Agent audio frames
received from the backend are decoded and scheduled back-to-back for gapless playback
(`src/lib/audioPlayback.ts`).

Uploaded WAV prompts may be mono or stereo and use any sample rate. The browser validates 16-bit PCM,
downmixes stereo, resamples to 24 kHz, sends deterministic binary chunks, and finishes with an
`audio_commit` control frame.

## Backend protocol

The Python backend implements this contract. See the header comment in
[`src/types/protocol.ts`](./src/types/protocol.ts) for the full authoritative type-level contract.

- **`GET /api/config`** — unauthenticated. Returns non-secret runtime configuration: environment
  label, hotel brand name, synthetic-data notice text, feature flags (voice/text/headless demo
  enabled), the prerecorded-audio flag, the WebSocket path prefix, and reconnect tuning values.
- **`POST /api/auth/session`** — requires an `Authorization: Bearer <Entra access token>` header.
  Exchanges the signed-in user's Entra token for a short-lived **opaque session handle**. The
  Entra token is never sent anywhere else, and never placed in a URL or query string.
- **`WebSocket /api/calls`** - uses a fixed URL so the opaque handle does not enter access logs.
  Because a browser `WebSocket` cannot set custom headers, the very first frame the client sends
  after the socket opens is a JSON auth frame
  (`{"type":"auth","opaqueHandle": "...", "mode": "voice" | "text" | "headless"}`) that restates
  the handle. The backend treats the connection as unauthenticated until that frame is received and
  validated.
- All other JSON message shapes exchanged on the socket (server call-state updates, transcript
  partials/finals, timeline/tool events, confirmation requests, result cards, disposition, and the
  client's text turns, mic-state, confirmation responses, cancel-output/barge-in, and end-call
  messages) are fully typed in `src/types/protocol.ts`.
- Binary WebSocket frames carry raw PCM16 24 kHz mono audio in both directions; JSON text frames
  carry every other event.
- The barge-in / "Interrupt agent" control sends a `cancel_output` frame. It only stops further
  agent audio/text output on the client and asks the backend to stop sending more — it does not
  claim to roll back any business action the agent has already committed.

## Accessibility

- All interactive controls are keyboard-operable native `<button>`/`<input>` elements with visible
  focus outlines (see `:focus-visible` rules in `src/index.css`).
- The transcript and activity timeline are `aria-live="polite"` regions so new turns/events are
  announced without interrupting the user.
- Connection-problem messages use `role="alert"` / `aria-live="assertive"` (`ErrorBanner`).
- Layout is responsive: a two-column desktop/tablet layout collapses to a single column at
  narrower viewports (see `src/App.module.css`).

## Theming

All colors are sourced exclusively from the `--cp-*` CSS custom properties defined in
`src/index.css` (light and `html[data-theme="dark"]` variants) — no component stylesheet hardcodes
a color. The theme is selected by a small inline script at the very top of `index.html`, before any
other JavaScript runs, based on a `scoutTheme` URL parameter or the user's OS color-scheme
preference. The primary typeface is the `"Segoe UI", Aptos, Calibri, -apple-system,
BlinkMacSystemFont, sans-serif` stack.

## npm scripts

| Script              | Description                                            |
| ------------------- | -------------------------------------------------------- |
| `npm run dev`        | Start the Vite dev server with HMR                       |
| `npm run build`      | Type-check (`tsc -b`) then produce a production build    |
| `npm run preview`    | Preview the production build locally                     |
| `npm run lint`       | Run `oxlint` over the project                             |
| `npm run typecheck`  | Run the TypeScript compiler in project-reference mode (no emit) |
| `npm run test`       | Run the Vitest test suite once                            |
| `npm run test:watch` | Run Vitest in watch mode                                  |

## Project structure

```
src/
  auth/        Entra sign-in (MSAL config, AuthProvider context)
  components/  Presentational React components (CSS Modules, --cp-* colors only)
  config/      Vite environment variable loading/validation
  hooks/       Call-session state machine (reducer + orchestrator hook), elapsed-time ticker
  lib/         Backend HTTP client, WebSocket client, PCM audio helpers, capture/playback, demo data
  types/       Documented wire-protocol types and env var typings
public/audio/  AudioWorkletProcessor script for microphone capture
```
