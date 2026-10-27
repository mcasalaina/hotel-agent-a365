# Foundry IQ source documents

Run `scripts/generate_hotel_data.py` to create the deterministic Markdown corpus in
the four category folders. Each generated document uses stable frontmatter for
document ID, title, property, category, validity window, locale, and source path.
Generated document filenames end in `.generated.md`. The 95 authoritative documents
are routed into four Hotel-only Search indexes: 20 property profiles, 15 chain-wide
policies, 20 dining/local guides, and 40 operational documents.

## Deploy and verify

Set `AZURE_SEARCH_ENDPOINT` and `AZURE_OPENAI_ENDPOINT` to the intended existing
services. For source archival, also set `FOUNDRY_IQ_BLOB_CONTAINER` and
`AZURE_STORAGE_ACCOUNT_URL`. The archive uses Entra authentication; public access
and storage account keys are not required.
Use `--corpus-dir <approved-corpus-directory>` when reusing an existing corpus
without regenerating it. Dry-run and deployment reject source documents carrying
runtime-prohibited environment labels before making Azure calls.

```bash
.venv/bin/python scripts/setup_foundry_iq.py --dry-run
.venv/bin/python scripts/setup_foundry_iq.py --lexical-only --tenant-id <tenant-id>
.venv/bin/python scripts/setup_foundry_iq.py --verify-only --tenant-id <tenant-id>
.venv/bin/python scripts/verify_deployment.py --tenant-id <tenant-id>
```

`--tenant-id` selects the signed-in Azure CLI identity for Search, the existing
model endpoint, and the archive, preventing a fallback to another credential.
Without that flag, the existing credential selection remains available.

The cam3652701 deployment deliberately uses semantic lexical retrieval with
`gpt-5.4-mini` for query planning and grounded answer synthesis. It does not create
or require an embedding deployment. Omit `--lexical-only` to retain the default
vector configuration when `text-embedding-3-small` already exists. Neither mode
provisions models or Foundry projects.

Each source retains its property, validity window, and source path. Retrieval must
filter by the requested property (plus chain-wide policies) and inclusive validity
dates; expired operational notices are not current property facts.

`verify_deployment.py` reads each live Hotel index schema and reports its actual
retrieval mode. Every index must pass semantic retrieval. Each index with vector
fields must additionally pass an integrated vector query; empty results and
vectorizer failures remain validation failures. Lexical-only indexes do not issue
vector queries. Verification also checks property isolation, knowledge-source
membership, cited answer synthesis, and reference validity.
