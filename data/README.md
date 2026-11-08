# Synthetic data

All business data is fictional. Generate the default Fabric-scale source data and
Foundry IQ corpus with:

```bash
.venv/bin/python scripts/generate_hotel_data.py --scale full
.venv/bin/python scripts/validate_hotel_data.py
```

Use `--scale demo` for quick local validation. CSV and manifest output remains
ignored under `data/generated/`; small canonical fixtures and schemas are tracked in
`data/fixtures/`.

The fixed business reference date is **November 8, 2026**; generation never reads
the wall clock. The reviewed September 1 chronology is shifted by 68 days, including
every linked date and timestamp. Future/arriving reservations start strictly after
the reference date; completed/departed/no-show/cancelled records end strictly before
it, and in-house stays span it. The modeled data window is May 8, 2026–June 7, 2027.
`RES-FAMILY-2026` retains guest `GST-000001`, Scottsdale `HTL-004`, and two rooms,
with the stay now November 17–19 and dining November 18.

Named mailbox values are preserved, not remapped to a target tenant. Live demos
require actual provisioned target accounts; a tenant ID alone does not establish
mailbox addresses.

For private preparation, pass `--output <bundle>\data\generated` and
`--docs-output <bundle>\foundryiq-docs`; preserve the sibling
`<bundle>\data\fixtures\business_scenarios.json` and `hotel_data_schema.json`.
The OneLake staging layout is `HotelGuestServices/Files/data/generated/` for all
23 CSV files plus `manifest.json`, and `HotelGuestServices/Files/data/fixtures/`
for the fixture JSON. `HotelInitialLoad` routes operations-owned tables into
`HotelOperations`; `ops_*` entries in guest services are shortcuts, not duplicate
CSV uploads. The current uploader requires 25 files; the schema JSON is an
additional recommended metadata file.
