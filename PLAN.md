# Hotel Guest Services Agent (A365) - Implementation Plan

## 1. Goal and confirmed decisions

Build a new hospitality demo, structurally parallel to `../bank-agent-a365`, for the fictional Lyrenza Hotels chain. The solution will use:

- One Microsoft Foundry Hosted Agent in the existing project:
  `https://4iq-foundry-project-resource.services.ai.azure.com/api/projects/4iq-foundry-project`
- One Foundry IQ knowledge base backed by multiple indexes on one Azure AI Search service.
- One Fabric workspace containing two authoritative lakehouses, a Direct Lake semantic model, a Power BI report, an ontology, notebooks, and a published Fabric data agent.
- Work IQ for mailbox, Teams, files, and other Microsoft 365 context.
- Agent 365 identity, blueprint, agent user, licensing, permissions, publishing, and Teams testing.
- Voice Live and a simulated contact-center web experience in Phase 3.

Confirmed architecture decisions:

1. Fabric is the only persistent structured business-data store. Do not add Azure SQL or another operational database.
2. Use two lakehouses to demonstrate the Fabric data agent unifying disparate sources:
   - `HotelOperations` owns properties, rooms, inventory, outlets, associates, and maintenance/work-order data.
   - `HotelGuestServices` owns guests, reservations, stays, dining reservations, folios, disputes, special requests, and customer-service action data.
3. Reservation, restaurant, billing-dispute, special-request, and maintenance mutations persist to Delta tables in their authoritative lakehouse.
4. The agent can execute every supported synthetic/demo action after showing the exact change and receiving explicit user confirmation.
5. Phase 3 extends the same Hosted Agent with `responses` and `invocations_ws`; it does not create a second voice agent.
6. No actual hotel brand may be mentioned. The only brand in content is the fictional Lyrenza Hotels.
7. `Lyrenza` may appear in synthetic business data, property documents, prompts, report labels, and customer-facing text. It must not appear in Azure resource names, Foundry technical object names, Fabric workspace/item names, Agent 365 identity/blueprint technical names, URLs, environment names, or code package names.
8. All customer, employee, payment, reservation, and communication data is synthetic. Store no full payment-card data; use masked values and synthetic payment tokens only.

## 2. Naming policy

Use generic technical names, with a short uniqueness suffix only where Azure requires global uniqueness.

| Element | Planned name |
|---|---|
| Repository/project | `hotel-agent-a365` |
| Resource group | `rg-hotel-agent-a365` |
| Foundry Hosted Agent | `hotel-servicing-agent` |
| Foundry IQ knowledge base | `hotel-foundryiq` |
| Search connection | `hotel-search` |
| Search service | `hotel-search-<suffix>` unless the project's default Search service is reused |
| Search indexes | `hotel-properties-index`, `hotel-policies-index`, `hotel-dining-local-index`, `hotel-operations-index` |
| Blob container | `hotel-docs` |
| Fabric workspace | `HotelAgent.Workspace` |
| Fabric lakehouses | `HotelOperations`, `HotelGuestServices` |
| Semantic model | `HotelOperationsModel` |
| Report | `HotelOperationsReport` |
| Ontology | `HotelOperationsOntology` |
| Fabric data agent | `HotelOperationsAgent` |
| Hosted web app | `hotel-agent-webapp` |
| Agent 365 identity/blueprint | `hotel-agent Identity` / `hotel-agent Blueprint` |
| Agent user | Generic hotel guest-services display name and UPN |

Before every deployment, run a naming-policy check over IaC, manifests, azd environment values, and Fabric definitions. It must fail if `Lyrenza` occurs in a technical resource-name field.

## 3. Fictional property roster

Create 20 properties with stable IDs (`HTL-001` through `HTL-020`). Each profile will include room counts and layouts, accessibility, services, dining, transportation, parking, family and pet policies, pool/spa/fitness hours, seasonal operations, dated construction notices, nearby attractions, and property-specific escalation contacts. Exact details will be generated consistently across documents and structured data.

| ID | Customer-facing property | Region | Signature facilities |
|---|---|---|---|
| HTL-001 | Lyrenza Seattle Waterfront | North America | Indoor pool, harbor-view gym, seafood restaurant, ferry access |
| HTL-002 | Lyrenza Vancouver Coal Harbour | North America | Saltwater pool, spa, bicycle program, mountain-view lounge |
| HTL-003 | Lyrenza San Francisco Embarcadero | North America | Rooftop terrace, fitness studio, market restaurant, no pool |
| HTL-004 | Lyrenza Scottsdale Sonoran Resort | North America | Three pools, spa, desert garden, golf shuttle, kids club |
| HTL-005 | Lyrenza Chicago River North | North America | Indoor lap pool, rooftop bar, meeting floor, river access |
| HTL-006 | Lyrenza New York Midtown | North America | 24-hour fitness, executive lounge, brasserie, no pool |
| HTL-007 | Lyrenza Miami South Beach | North America | Oceanfront pool, beach service, cabanas, Latin coastal dining |
| HTL-008 | Lyrenza Mexico City Polanco | North America | Rooftop pool, spa, contemporary Mexican restaurant, club lounge |
| HTL-009 | Lyrenza London Mayfair | Europe | Afternoon-tea lounge, wellness suite, butler floor, no pool |
| HTL-010 | Lyrenza Paris Left Bank | Europe | Courtyard restaurant, compact spa, family suites, no pool |
| HTL-011 | Lyrenza Amsterdam Canal Quarter | Europe | Canal terrace, bicycle concierge, sauna, no pool |
| HTL-012 | Lyrenza Lisbon Baixa | Europe | Rooftop plunge pool, tile courtyard, Portuguese restaurant |
| HTL-013 | Lyrenza Barcelona Eixample | Europe | Rooftop pool, tapas restaurant, fitness studio, family rooms |
| HTL-014 | Lyrenza Rome Via Veneto | Europe | Garden restaurant, wellness rooms, rooftop aperitivo, no pool |
| HTL-015 | Lyrenza Vienna Ring | Europe | Indoor pool, concert concierge, cafe, ballroom |
| HTL-016 | Lyrenza Buenos Aires Puerto Madero | South America | Indoor pool, tango lounge, steak restaurant, river views |
| HTL-017 | Lyrenza Rio Copacabana | South America | Rooftop infinity pool, beach service, Brazilian grill |
| HTL-018 | Lyrenza Sao Paulo Jardins | South America | Indoor pool, business lounge, spa, chef-led restaurant |
| HTL-019 | Lyrenza Lima Miraflores | South America | Ocean-view pool, ceviche restaurant, airport transfers |
| HTL-020 | Lyrenza Cartagena Walled City | South America | Courtyard pool, rooftop bar, colonial-style suites |

Property documents must clearly distinguish permanent facts from dated operational notices. Retrieval tests will include past, current, and future construction windows so the agent does not present stale notices as current.

## 4. Repository shape

Mirror the useful surfaces of `bank-agent-a365`, while replacing its prompt-agent assumptions with a Hosted Agent and completing artifacts that were only partially automated there.

```text
hotel-agent-a365/
|-- PLAN.md
|-- README.md
|-- DEPLOYMENT.md
|-- DEMO_SCENARIO.md
|-- FABRIC_QUESTIONS.md
|-- agent-instructions.md
|-- azure.yaml
|-- Dockerfile
|-- run.sh
|-- startup.sh
|-- infra/
|   `-- supporting Azure resources and role assignments
|-- src/hotel-servicing-agent/
|   |-- main.py
|   |-- orchestration/
|   |-- tools/
|   |-- state/
|   |-- requirements.txt
|   |-- agent.manifest.yaml
|   `-- .foundry/
|-- agent/
|   |-- Agent 365 host/configuration parity files
|   |-- ToolingManifest.json
|   |-- a365.config.example.json
|   `-- auth and token helpers
|-- manifest/
|   |-- manifest.json
|   |-- agenticUserTemplateManifest.json
|   |-- color.png
|   `-- outline.png
|-- foundryiq-docs/
|   |-- properties/
|   |-- policies/
|   |-- dining-local/
|   `-- operations/
|-- fabric/
|   |-- lakehouse/
|   |-- notebooks/
|   |-- semantic-model/
|   |-- report/
|   |-- ontology/
|   `-- data-agent/
|-- data/
|   |-- generated/
|   `-- fixtures/
|-- scripts/
|   |-- generate_hotel_data.py
|   |-- validate_hotel_data.py
|   |-- upload_onelake_files.py
|   |-- load_tables.py
|   |-- deploy_semantic_model_and_report.py
|   |-- deploy_ontology.py
|   |-- create_data_agent.py
|   |-- publish_data_agent.py
|   |-- setup_foundry_iq.py
|   |-- invoke_agent.py
|   |-- verify_deployment.py
|   `-- migrate_to_tenant.sh
|-- eval.yaml
|-- tests/
`-- dashboard/
    |-- backend/
    `-- frontend/
```

Secrets, generated agent configuration, tokens, deployment packages, large generated data, and `manifest.zip` remain uncommitted.

## 5. Phase 1 - Data, knowledge, Fabric, and Hosted Agent

Phase 1 is not complete until every component passes its isolated tests and the canonical end-to-end scenarios pass.

### 5.1 Bootstrap and configuration

1. Initialize the repository and Python/TypeScript projects.
2. Bind azd to the existing Foundry project by its resolved ARM ID:
   `/subscriptions/27b0139a-16b4-42bf-9ec9-c6db3768245e/resourceGroups/rg-aycabas-3iqs/providers/Microsoft.CognitiveServices/accounts/4iq-foundry-project-resource/projects/4iq-foundry-project`.
3. Use the existing `gpt-5.4-mini` deployment for orchestration and `text-embedding-3-small` for indexing unless a live capability check requires another supported deployment.
4. Build the Hosted Agent for container deployment from the start because Phase 3 requires `invocations_ws`.
5. Add Application Insights tracing from the existing project and propagate correlation IDs across agent, Fabric, Search, and Work IQ calls.
6. Define environment-neutral configuration and discover remote IDs; do not copy resource IDs from `bank-agent-a365`.

### 5.2 Synthetic business data

Generate deterministic, internally consistent data covering 2026-03-01 through 2027-03-31 inclusive. Include seasonality, weekends, holidays, city events, lead-time curves, channel mix, cancellations, no-shows, overbooking, out-of-order rooms, construction periods, and regional currency/tax behavior.

Target scale:

| Domain | Target |
|---|---:|
| Properties | 20 |
| Room types | 80-100 |
| Physical rooms | 4,000-5,000 |
| Outlets/restaurants | 45-60 |
| Synthetic guests | 25,000+ |
| Room reservations | 75,000+ |
| Stay records | 45,000+ |
| Restaurant reservations | 35,000+ |
| Folio transactions/payments/adjustments | 300,000+ |
| Special requests | 20,000+ |
| Maintenance requests/work orders | 10,000+ |
| Billing disputes/service cases | 3,000+ |
| Daily property facts | 7,920 rows minimum |
| Daily room-type inventory/rates | One row per property, room type, and service date |

Core Delta tables:

- Reference: `properties`, `room_types`, `rooms`, `outlets`, `associates`, `rate_plans`, `amenities`, `property_amenities`, `date`.
- Guest and stay: `guests`, `guest_preferences`, `reservations`, `reservation_guests`, `stays`, `room_assignments`.
- Dining: `restaurant_reservations`, `restaurant_checks`.
- Billing: `folios`, `folio_transactions`, `payments`, `adjustments`, `billing_disputes`, `folio_document_requests`.
- Service: `special_requests`, `maintenance_requests`, `work_orders`, `service_cases`, `service_recovery`.
- Commercial/operations: `daily_inventory`, `daily_rates`, `property_daily_metrics`, `channel_daily_metrics`, `outlet_daily_metrics`.
- Mutation control: `action_confirmations`, `idempotency_records`, `audit_events`.

Seed named fixtures for repeatable demos, including:

- Property discovery and amenity questions.
- A multi-room family booking with accessibility needs.
- A date/rate change with a changed cancellation policy.
- A cancellable and a nonrefundable reservation.
- A completed stay with a disputed minibar or parking charge and a reproducible folio.
- A pre-arrival allergy/crib/late-arrival request.
- An in-stay HVAC or plumbing maintenance request.
- A restaurant reservation that can be created and changed.

Validation gates:

- Primary/foreign-key integrity and uniqueness.
- Exact date coverage and a mix of past, in-house, arriving, departed, cancelled, no-show, and future records.
- No room-type inventory below zero or occupied rooms above sellable inventory.
- Reservation and stay status transitions are valid.
- Folio headers reconcile to transactions, payments, refunds, taxes, and adjustments.
- Currency and tax rules match the property's country.
- Canonical fixtures reproduce byte-for-byte from a fixed random seed.

### 5.3 One Fabric workspace and two lakehouses

1. Create `HotelAgent.Workspace` on the active East US 2 F16 capacity `cap3iqs5ea837a6` (`24f6590d-413b-4d9f-9c2b-601d753eda94`) with:
   - `HotelOperations` for properties, room types, rooms, outlets, associates, amenities, physical/sellable inventory, rates, maintenance requests, and work orders.
   - `HotelGuestServices` for guests, preferences, reservations, stays, room assignments, restaurant reservations/checks, folios, payments, adjustments, disputes, special requests, service cases, confirmations, idempotency, and customer-facing audit events.
2. Upload generated source files to the appropriate OneLake location and materialize every serving table as Delta.
3. Keep all persistent business records in these two lakehouses. Do not create Azure SQL, another operational database, or a third domain lakehouse.
4. Configure the Fabric data agent against both lakehouses as distinct sources. Do not point it only at shortcut aliases; cross-lakehouse source selection and synthesis are a primary demo objective.
5. Create source-controlled OneLake shortcuts in `HotelGuestServices` for the limited `HotelOperations` dimensions/facts required by the Direct Lake semantic model. Prefix shortcut tables with `ops_`, avoid data duplication, and validate that shortcuts resolve before model deployment.
6. Create parameterized Fabric notebooks:
   - initial load and deterministic reset;
   - validation;
   - `reservation_action`;
   - `restaurant_action`;
   - `billing_dispute_action`;
   - `service_request_action`;
   - aggregate refresh;
   - data-agent runtime publish.
7. Hosted Agent mutation tools invoke notebook jobs with typed parameters, idempotency keys, expected record versions, and confirmation IDs. Notebooks use Delta `MERGE` and append immutable audit events.
8. A stale record version produces a conflict, not a silent overwrite. The agent rereads the record, explains the change, and asks for a new confirmation.
9. A repeated idempotency key returns the original result without duplicating the action.
10. Cross-lakehouse actions use a saga recorded in `HotelGuestServices.action_confirmations` and `audit_events`. Each lakehouse step is idempotent; partial failure is visible as `pending_reconciliation` and a reconciliation notebook completes or compensates it. Never imply a distributed ACID transaction across lakehouses.
11. Each lakehouse SQL endpoint and the Fabric data agent provide read/query paths. Notebook jobs provide controlled write paths.

### 5.4 Semantic model and report

Deploy a Direct Lake semantic model from source-controlled TMDL over `HotelGuestServices` plus its validated `ops_` OneLake shortcuts to `HotelOperations`, with:

- Conformed Date, Property, Room Type, Guest, Channel, Rate Plan, Outlet, and Request dimensions.
- Reservation, Stay, Room Revenue, Folio, Inventory, Restaurant, Request, Maintenance, and Dispute facts.
- Relationships, display folders, descriptions, format strings, hidden technical columns, and role-safe customer detail.
- Measures for OCC, ADR, RevPAR, TRevPAR, GOPPAR, NRevPAR, ALOS/LOS, CPOR, booking pace, pickup, cancellation/no-show rate, channel mix, room and F&B revenue, service-recovery cost, dispute rate, maintenance response time, and guest spend.

Deploy a real PBIR report, not only a pointer, with pages:

1. Executive and property performance.
2. Booking pace, demand, and channel mix.
3. Guest value and spend.
4. Front-desk and stay operations.
5. Dining and HoReCa performance.
6. Requests, maintenance, disputes, and service recovery.

Verify model metadata, execute DAX assertions for canonical measures, validate PBIR structure, and open/query the deployed report against live data.

### 5.5 Ontology

Create a true `Ontology` item named `HotelOperationsOntology`, not a bare `GraphModel`.

Entity types include Property, Room, Room Type, Guest, Reservation, Stay, Outlet, Folio, Folio Transaction, Special Request, Maintenance Request, Work Order, and Associate. Relationships support paths such as:

`Guest -> Reservation -> Stay -> Room -> Property`

`Stay -> Folio -> Folio Transaction -> Billing Dispute`

`Stay -> Special Request`

`Room -> Maintenance Request -> Work Order -> Associate`

Rules inherited from the reference deployment:

- Ontology display names use only letters, numbers, and underscores.
- Use supported value types (`String`, `Boolean`, `DateTime`, `Object`, `BigInt`, `Double`).
- Create with the full definition; do not create an empty Ontology.
- Wait for auto-created backing graph/lakehouse artifacts.
- Trigger and verify graph data load. If the portal Save action is still required, document and perform it; Phase 1 does not pass until a GQL traversal returns expected rows without `GraphIsNotLoaded`.

### 5.6 Fabric data agent

Create and publish `HotelOperationsAgent` with four sources:

1. `HotelOperations` lakehouse for property, room, inventory, rate, outlet, associate, maintenance, and work-order SQL.
2. `HotelGuestServices` lakehouse for guest, reservation, stay, dining, folio, dispute, request, and service-case SQL.
3. `HotelOperationsModel` for governed cross-domain analytical DAX.
4. `HotelOperationsOntology` for relationship/path questions spanning both domains.

Version-control the draft data-agent configuration, source descriptions, selected schema, instructions, publishing description, and few-shot queries. Do not edit the published folder directly.

Data-source descriptions must state authority and boundaries precisely. Each lakehouse is authoritative for its listed domain and mutations; the semantic model is authoritative for governed cross-domain measures; the ontology is for relationship traversal. Instructions must explicitly tell the data agent when a question requires both lakehouses, such as combining room availability or maintenance status with a guest's reservation, stay, or service case.

Data-agent instructions define chain and industry terminology, including:

- Chain terms: LGR (Lyrenza Guest Record), LSR (Lyrenza Service Request), LCR (Lyrenza Care Recovery), SIR (Stay Incident Record), GPF (Guest Preference Flag).
- HoReCa and hotel terms: HoReCa/HORECA, PMS, CRS, RMS, POS, F&B, MICE, OTA, GDS, BAR, FIT, OCC, ADR, RevPAR, TRevPAR, GOPPAR, NRevPAR, LOS, ALOS, CPOR, OOO, OOS, DND, ETA, ETD, VIP, comp, folio, room block, pickup, wash, stayover, due-in, and due-out.
- Date, status, currency, tax, privacy, and source-routing rules.

Supply validated few-shot SQL for lakehouse questions and measure-oriented examples for semantic-model use. Publish through the real data-agent management deploy path; `updateDefinition` alone is not proof that the runtime is queryable.

### 5.7 Foundry IQ

1. The target project currently has a project-managed-identity Search connection to `3iqs-search-aycabas`, but that service is in East US while the Foundry project is in East US 2. Do not reuse it for this solution.
2. Create one generic Azure AI Search resource in East US 2, connect it to the project as `hotel-search`, and keep every hotel index and knowledge base there. Preserve unrelated existing indexes and connections.
3. Create four indexes and knowledge sources on that one service:
   - property profiles;
   - guest policies and service procedures;
   - dining and local-area guides;
   - operational notices and property FAQs.
4. Store source Markdown in Blob Storage under category/property prefixes, index it with consistent chunking and `text-embedding-3-small`, and retain title, property ID, category, validity dates, locale, source path, and citation metadata.
5. Create `hotel-foundryiq` with answer synthesis over all four co-located sources and attach it to the Hosted Agent.

The corpus includes at least:

- 20 detailed property profiles.
- 20 dining/local guides.
- Chain-wide reservation, cancellation, deposit, no-show, pet, parking, accessibility, privacy, payment, folio, dispute, lost-and-found, safety, special-request, and maintenance procedures.
- Property-specific transport, parking, amenity-hour, seasonal, and dated construction notices.

Tests assert nonzero chunk counts in every index, source membership in the knowledge base, citation correctness, property isolation, temporal-notice handling, and no mention of real hotel brands.

### 5.8 Hosted Agent

Deploy `hotel-servicing-agent` as a Python Hosted Agent in the target project. Phase 1 exposes the `responses` protocol; the container and shared orchestration are structured so Phase 3 can add `invocations_ws` without creating another agent.

Capabilities:

- Property and amenity questions through Foundry IQ.
- Structured guest, reservation, stay, dining, folio, request, maintenance, and analytics questions through the Fabric data agent.
- Reservation and restaurant create/change/cancel through confirmed notebook-backed mutation tools.
- Folio copies rendered from lakehouse data and returned as a downloadable artifact.
- Billing disputes opened, updated, and resolved in the demo after confirmation.
- Pre-arrival and in-stay special requests.
- In-stay maintenance requests and status updates.
- Work IQ for relevant email, Teams, calendar, files, and drafting/sending when permissions and policy allow.
- Web IQ parity with the bank agent for current public facts such as transport disruptions, weather impacts, and local closures; never use it instead of property knowledge or structured hotel data.

Behavior:

- Identify the guest/reservation with synthetic verification fields before exposing or changing customer-specific details.
- Show the exact proposed mutation, price/penalty impact, and policy basis before requesting confirmation.
- Execute all supported demo actions after confirmation.
- Never claim a write succeeded until the mutation notebook returns and the record is reread.
- Stream concise, truthful intermediate events such as "Checking room availability" or "Updating the reservation." Do not expose chain-of-thought.
- Retry one transient tool failure with a narrower request; surface persistent failures clearly.
- Preserve only ephemeral orchestration state in the Hosted Agent session. The two lakehouses remain authoritative for business state.

### 5.9 Phase 1 testing and exit gate

Isolated test suites:

| Component | Required proof |
|---|---|
| Data generator | Deterministic scale, integrity, date coverage, reconciliation, and fixture assertions |
| Lakehouses | All Delta tables queryable in their authoritative source with expected counts, schemas, shortcuts, and no unintended duplication |
| Mutation notebooks | Create/change/cancel/dispute/request flows, idempotency, conflict, audit, and rollback tests |
| Semantic model | DAX assertions for named measures and Direct Lake connectivity |
| Report | PBIR validation and live visuals backed by the deployed model |
| Ontology | GQL paths return canonical guest/reservation/stay/request rows |
| Fabric data agent | Benchmark single-source and cross-lakehouse NL2SQL/NL2DAX/path questions return grounded expected facts with correct source selection |
| Search/Foundry IQ | Index counts, retrieval, citations, temporal filters, and brand-exclusion tests |
| Work IQ | Current-user read/search and draft tests; mutation test only with explicit test recipient and policy enabled |
| Hosted Agent | Local tests, deployed session, streaming events, file result, tool routing, and error behavior |

Combined acceptance scenarios:

1. Compare properties by amenities and current construction notices.
2. Find availability and create a reservation after confirmation.
3. Change dates/room type and explain the new total and policy.
4. Cancel a refundable and a nonrefundable booking with correct impact.
5. Create/change/cancel a restaurant reservation.
6. Retrieve a completed-stay folio and provide a copy.
7. Open and resolve a synthetic billing dispute.
8. Add pre-arrival accessibility, allergy, crib, and late-arrival requests.
9. Open an in-stay maintenance request and retrieve its status.
10. Answer a cross-source question that combines room/inventory or maintenance data from `HotelOperations`, guest/reservation/folio data from `HotelGuestServices`, and policy/property knowledge from Foundry IQ.
11. Use Work IQ to locate a synthetic guest email and draft the response.

Run a source-controlled Foundry evaluation suite with smoke, regression, coverage, tool-routing, groundedness, citation, action-confirmation, and sensitive-data evaluators. Phase 1 passes only when no required check is skipped.

## 6. Phase 2 - Agent 365 deployment

Phase 2 starts only after the Phase 1 gate passes.

### 6.1 Identity, blueprint, host, and manifest

1. Reuse the live Hosted Agent's Foundry-managed blueprint reference as the canonical blueprint; do not create a competing duplicate blueprint.
2. Keep the Agent 365 host/configuration parity files from the bank repository for notifications, OBO, MCP tooling, and diagnostics.
3. Build the four-file manifest package with IDs discovered from the live agent/blueprint. Validate both ID-linkage invariants before packaging.
4. Publish to Microsoft 365 Admin Center, configure the blueprint as API Based in Teams Developer Portal, and set the notification URL to the Hosted Agent's `activityprotocol` endpoint or the documented A365 messaging endpoint selected by the live publish flow.
5. Create and approve the agent instance, create the generic agent user, assign manager, usage location, Teams/Agent 365/Microsoft 365 licenses, and a writable Exchange mailbox when mail mutation is part of the demo.

### 6.2 Permission matrix and known fixes

Automate discovery and verification, but retain explicit admin/manual gates where the bank deployment proved automation unreliable.

- Blueprint editing:
  - Human operator is an owner of the blueprint app registration.
  - Human operator has Agent ID Developer and Agent ID Administrator directory roles.
- Agentic user on Foundry:
  - Azure AI/Foundry data-plane role at both account and project scopes.
  - Cognitive Services User and Cognitive Services OpenAI User at account scope when required by the live API.
- Hosted Agent/project identities:
  - Search Index Data Reader on the Search service.
  - Storage Blob Data Reader for knowledge documents.
  - Required Foundry project and model access.
- Fabric:
  - Add the agent identity/user as Contributor or Member to `HotelAgent.Workspace`.
  - Verify with an actual data-agent query under the agent identity; a successful REST role call alone is insufficient.
- Blueprint delegated/admin-consent grants:
  - Microsoft Graph mail/Teams/files/sites scopes.
  - Power Platform connectivity.
  - Messaging Bot `AgentData.ReadWrite`.
  - Agent 365 observability write.
  - Agent 365 Tools and current Mail/Teams MCP scopes.
  - Cognitive Services and Azure Machine Learning `user_impersonation`.
  - Work IQ `WorkIQAgent.Ask`.
  - Discover live service principals and scope IDs; do not blindly copy bank-tenant object IDs.
- Work IQ:
  - Use current V2 Mail and Teams MCP audiences with `Tools.ListInvoke.All`, not the legacy V1 audience.
  - Ensure the agent has a writable Exchange-bearing license.
  - Tenant admin enables Work IQ MCP write/mutation actions in Admin Center. The default policy denies writes.
  - Allow the documented propagation window, then restart/redeploy the host to clear stale tokens.

### 6.3 Troubleshooting runbook carried forward

Document symptom, diagnostic, fix, propagation interval, and verification for:

- Blueprint visible but not editable: app ownership plus Agent ID roles.
- Agent available but not instantiable: Frontier/tenant enablement and Developer Portal configuration.
- Teams silence with zero Foundry telemetry: agentic-user Foundry RBAC.
- "Waiting for foundry login": missing blueprint OBO admin-consent grants.
- `a365 publish` hanging: build the flat four-file package from live IDs if the CLI app is not enrolled.
- Fabric `User is not authorized`: manually add the agent identity to workspace access and retest as that identity.
- Data agent new source unavailable: wait for SQL endpoint schema, delete/re-add zero-table source, select tables, and call management deploy.
- Work IQ reads succeed but send fails: V2 MCP audience, Exchange license, admin consent, tenant mutation policy, propagation, restart.
- App Service import/start failure: include all A365/Agents dependencies and compatible OpenTelemetry pins.
- Stateless Responses 400: persist assistant text/history, not raw SDK response objects.
- Hosted Agent cold start or `session_not_ready`: inspect session logs, model name, identity permissions, and allocate at least 1 CPU/2 GiB.

### 6.4 Phase 2 tests and exit gate

- Manifest schema and ID-linkage validation.
- Blueprint permissions and eight-category consent matrix validation.
- Teams agent discovery, request, approval, and user creation.
- Real Teams DM, multi-turn conversation, and action confirmation.
- Foundry telemetry span for the Teams channel.
- Fabric lookup and a confirmed reservation mutation under the agent identity.
- Work IQ mailbox read, draft, and send to a designated synthetic/test recipient.
- Agent 365 Activity/observability entries.
- License, mailbox, and permission checks recorded without secrets.

Do not use Azure Bot Web Chat or Direct Line as the authoritative OBO test; use a real Teams DM.

## 7. Phase 3 - Voice Live simulated contact center

Phase 3 upgrades the same `hotel-servicing-agent` version and preserves all Phase 1 and Phase 2 behavior.

### 7.1 Dual-protocol Hosted Agent

1. Add `invocations_ws` alongside `responses` in `azure.yaml` and `agent.manifest.yaml`.
2. Compose both protocol adapters over the same orchestration, tool registry, confirmation logic, lakehouse actions, and instructions.
3. Use a container with at least 1 CPU/2 GiB and validate the Foundry preview feature flag and region support.
4. Use the Voice Live Responses integration where useful, while preserving the explicit duplex WebSocket endpoint required by the contact-center browser flow.
5. Confirm Voice Live model availability in the target resource/region before deployment; deploy or select a supported realtime model only after a capacity check.

### 7.2 Foreground/background experience

Adapt the two Microsoft samples supplied for this project:

- The responses/Voice Live sample's background worker and periodic filler/status generation.
- The `duplex-live-agent` sample's foreground router, background task manager, PCM framing, browser events, interruption handling, and hosted `invocations_ws` deployment.

The main hotel operation runs in an `asyncio` task. A foreground voice router remains responsive and emits short, truthful filler based on real task status. The client does not need to distinguish a filler utterance from the final response to keep playback flowing, but structured events label status versus final text for the visual timeline.

Requirements:

- No invented progress or chain-of-thought.
- Filler is short, varied, and derived from the active operation, for example "I'm checking the room inventory now."
- Barge-in stops queued audio and lets the user ask a clarification or cancel.
- The business operation continues safely unless the user explicitly cancels before commit.
- Once a confirmed mutation begins its atomic Delta commit, cancellation reports the eventual committed result rather than claiming rollback.
- Reconnect with the same `agent_session_id` restores session-visible task status; business state is reread from the lakehouse.

### 7.3 Simulated-call web application

Build a React/TypeScript frontend and Python backend proxy:

- Browser captures PCM16 24-kHz mono audio and receives audio/transcript/events.
- The backend obtains the Entra token and opens the Foundry WebSocket because browser WebSocket APIs cannot set the Authorization header.
- The page shows call state, live user/agent transcripts, elapsed time, friendly tool/data-source events, confirmation cards, reservation/folio/request result cards, and final disposition.
- The UI explicitly labels generated synthetic data and the fictional hotel chain.
- Do not display hidden prompts, credentials, raw tokens, chain-of-thought, or unnecessary customer fields.
- Provide a text-input mode and prerecorded/headless test mode so the demo can be validated without a microphone.

### 7.4 Phase 3 tests and exit gate

- Local duplex headless test: session start, text turn, audio bytes, transcript, progress events, and completion.
- Microphone/browser test with server VAD, echo cancellation, noise reduction, barge-in, and reconnect.
- Hosted WebSocket authentication and preview-flag tests.
- Long-running property lookup and reservation mutation with multiple status utterances followed by one final result.
- Confirmation over voice and on-screen UI before a mutation.
- Browser proxy security and token non-disclosure.
- Playwright tests for timeline, transcript, confirmations, reconnect, errors, and accessibility.
- Regression of all Phase 1 Responses tests and Phase 2 Teams/A365 tests against the new Hosted Agent version.

## 8. Cross-phase engineering rules

- Deploy and test in dependency order; do not mark portal/manual steps as skipped.
- Prefer least privilege and managed identity; never commit secrets.
- Discover IDs and endpoints dynamically.
- Use the Responses API for the Hosted Agent; do not port the bank repository's old Assistants API verifier.
- Stream progress summaries, not internal reasoning.
- Every mutation requires a confirmation record, idempotency key, reread, and audit event.
- All tests use synthetic identities and designated test mailboxes.
- Keep setup and verification scripts rerunnable and fail loudly on partial deployment.
- Update `DEPLOYMENT.md` with actual resource IDs, versions, known propagation states, and verification evidence as each phase completes.

## 9. Phase dependency and completion order

1. Repository/configuration and naming guard.
2. Property corpus and deterministic data generator.
3. Fabric workspace, both lakehouses, Delta tables, cross-lakehouse shortcuts, and mutation notebooks.
4. Semantic model, report, ontology, and Fabric data agent.
5. Search indexes and Foundry IQ.
6. Hosted Agent local tests, deployment, evaluation, and combined Phase 1 gate.
7. Agent 365 identity, consent, permissions, manifest, publish, Teams, and Phase 2 gate.
8. Voice Live dual protocol, simulated-call web app, and Phase 3 regression gate.

No later phase begins while a required earlier-phase check is failed or skipped.
