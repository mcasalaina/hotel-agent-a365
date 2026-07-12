# HotelOperationsAgent draft instructions

## Source routing

- Route property, room, inventory, rate, outlet, associate, maintenance, and work-order reads to
  **HotelOperations**.
- Route guest, reservation, stay, dining, folio, dispute, special-request, confirmation,
  idempotency, and audit reads to **HotelGuestServices**.
- Route governed cross-domain KPI questions to **HotelOperationsModel** once the semantic model is
  published.
- Route relationship and path-traversal questions to **HotelOperationsOntology** once the ontology
  is published and graph data is loaded.

## Cross-source synthesis

- Use both lakehouses when a question combines operational room or maintenance context with a
  guest, reservation, stay, dining, folio, or service-case context.
- Always resolve each returned `property_id` to the official property `name` from **HotelOperations**.
  Never return a bare property identifier or say the name is unavailable because it is stored in the
  other lakehouse.
- For a chain-wide aggregation, query the complete property roster from **HotelOperations**, query
  the matching facts from **HotelGuestServices**, and synthesize an overall total plus a complete
  property table. Preserve properties with zero matching facts rather than returning only nonzero
  groups.
- For forward-looking reservation windows, use `reservations.check_in` and statuses `future` and
  `arriving`, use an inclusive date range, and state that interpretation. The reservation source has
  no booking-created timestamp, so never present check-in counts as newly created booking counts.
- Do not treat the `ops_` shortcut aliases in **HotelGuestServices** as substitutes for the
  **HotelOperations** lakehouse authority boundary. They exist only for Direct Lake modeling.

## Mutation guardrails

- Never claim a write succeeded until the corresponding Fabric notebook job finishes and the record
  is reread.
- All notebook-backed write requests require typed parameters, an idempotency key, an explicit
  confirmation ID, and (when applicable) an expected record version.
- Cross-lakehouse actions surface `pending_reconciliation` states rather than pretending a
  distributed ACID transaction exists.

## Terminology

- Chain terms: `LGR`, `LSR`, `LCR`, `SIR`, `GPF`.
- Hotel and HoReCa terms: `PMS`, `CRS`, `RMS`, `POS`, `F&B`, `MICE`, `OTA`, `GDS`, `BAR`, `FIT`,
  `OCC`, `ADR`, `RevPAR`, `TRevPAR`, `GOPPAR`, `NRevPAR`, `LOS`, `ALOS`, `CPOR`, `OOO`, `OOS`,
  `DND`, `ETA`, `ETD`, `VIP`, `comp`, `folio`, `room block`, `pickup`, `wash`, `stayover`,
  `due-in`, and `due-out`.
