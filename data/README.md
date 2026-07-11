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
