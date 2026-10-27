# Hotel source data

Generate the full operational corpus and validate it locally:

```bash
.venv/bin/python scripts/generate_hotel_data.py --scale full --docs-output data/generated/documents
.venv/bin/python scripts/validate_hotel_data.py --docs-output data/generated/documents
```

Use `--scale demo` for quick local validation. CSVs, the manifest, and the
document output above remain ignored under `data/generated/`. This command does
not modify `foundryiq-docs/`. The explicit document directory can instead point to
that corpus when an update is intended.

The authoritative temporal boundary is 2026-09-01 at 00:00. Completed, departed,
and no-show reservations end strictly before it. Future reservations start
strictly after it, including arriving reservations. Records on the boundary
belong to neither past nor future. In-house reservations span it with an empty
actual checkout. Transaction and service dates must remain consistent with
their reservation's dates and temporal classification.

Daily inventory and rates cover 2026-03-01 through 2027-03-31 inclusive.
The final service night can check out on 2027-04-01. Occupancy before the boundary
is actual occupancy, including accrued in-house nights. Later occupancy is
confirmed on-books room nights, not completed stays. Recognized room revenue is
zero on and after the boundary. Historical inventory, actual stays, reservation
room nights, daily revenue, rates, and folio room charges reconcile exactly.
Physical rooms never have overlapping actual stays. Folio balances use charges
plus adjustments minus captured payments plus refunds.

Fixed seeds reproduce CSV and document hashes. Property-specific demand, seasons,
weekday mix, room counts, length of stay, rates, service quality, and risk produce
different property outcomes. Workload and disputes follow the actual stays and
folios rather than independent row counts.

`data/fixtures/business_scenarios.json` defines the canonical service scenarios.
Maria Garcia is `GST-000001`, with email
`mariagarcia@cam3652701.onmicrosoft.com` and one future reservation,
`RES-FAMILY-2026`, at Lyrenza Scottsdale Sonoran Resort (`HTL-004`) from
2026-09-10 through 2026-09-12.
It books two Family rooms and has a confirmed prearrival accessibility request.
The source validator checks this exact identity, room type, room count, dates,
and status, even when CSV counts and manifest hashes are otherwise coherent.
`HotelValidation` independently reads the live guest/reservation join and
returns the canonical record with its validation results.
The in-house maintenance scenario is `RES-INSTAY`, spanning 2026-08-30 through
2026-09-03. Stable financial references remain `STY-0000001`,
`STY-0000002`, and `FOL-0000001`.
