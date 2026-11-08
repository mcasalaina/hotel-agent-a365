# Generated data

Generated deterministic CSV tables and `manifest.json` are written here and remain
uncommitted. Run `scripts/generate_hotel_data.py`; use
`scripts/validate_hotel_data.py` to validate counts, hashes, relationships, dates,
inventory, folios, masked payments, and the generated document corpus.

The canonical manifest records the fixed **2026-11-08** business reference date,
the **68-day** shift from the reviewed September baseline, and the complete
May 8, 2026–June 7, 2027 date window. `full` is the causal operating model, not a
promise that reservation/stay counts equal the legacy `SCALE_COUNTS` constants.
Fixtures are source-controlled in `data/fixtures/business_scenarios.json`.
