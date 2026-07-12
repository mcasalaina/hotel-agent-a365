# Fabric questions

This file will hold the canonical natural-language benchmark for the two Fabric lakehouses, semantic model, ontology, and published data agent.

## Chain-wide reservation arrivals

Question: `How many reservations are arriving across all properties from 2026-07-12 through 2026-07-18?`

Expected behavior:

- Interpret the window as inclusive `check_in` dates with status `future` or `arriving`.
- State the interpretation and date range.
- Return the overall total.
- Query the complete `HotelOperations` property roster and show all 20 official property names and
  IDs, including properties with zero matching reservations.
- Do not describe these as reservations newly created or booked during the period because the current
  reservation source has no booking-created timestamp.

Question sets will cover:

- Single-source hotel operations and guest-services queries
- Cross-lakehouse reservation, inventory, maintenance, and folio questions
- Governed analytical measures through the semantic model
- Relationship traversal through the ontology
- Mutation previews, confirmations, idempotency, conflicts, and rereads

The deterministic source-data fixtures now provide stable IDs for the future question
set: `RES-DEMO-FAMILY`, `RES-DEMO-RATE-CHANGE`, `RES-DEMO-CANCEL-FLEX`,
`RES-DEMO-CANCEL-NRF`, `RES-DEMO-FOLIO`, `SR-DEMO-PREARRIVAL`,
`MR-DEMO-HVAC`, and `RR-DEMO-DINING`. Fabric definitions and query benchmarks remain
out of scope for this workstream.
