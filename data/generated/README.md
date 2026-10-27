# Generated data

Generated deterministic CSV tables and `manifest.json` are written here and remain
uncommitted. Run `scripts/generate_hotel_data.py`; use
`scripts/validate_hotel_data.py` to validate counts, hashes, relationships, dates,
inventory, folios, masked payments, and the generated document corpus.

Use `--docs-output data/generated/documents` with both commands to keep generated
documents here without changing the maintained `foundryiq-docs/` corpus.
The snapshot boundary is 2026-09-01. The manifest records temporal semantics and
SHA-256 hashes for all 23 CSVs and 95 documents.
