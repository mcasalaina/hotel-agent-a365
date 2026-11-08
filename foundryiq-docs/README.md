# Foundry IQ source documents

Run `scripts/generate_hotel_data.py` to create the deterministic Markdown corpus in
the four category folders. Each generated document uses stable frontmatter for
document ID, title, property, category, validity window, locale, and source path.
Generated document filenames end in `.generated.md` and are intentionally ignored;
the later Search/Foundry IQ workstream can upload them without changing cloud
resources here.

Validate the frozen corpus against the current generator before loading it:

```powershell
python scripts\setup_foundry_iq.py --dry-run --check-canonical --retrieval-mode native
```

`native` uses semantic lexical retrieval and the existing `gpt-5.4-mini` chat
deployment, without an embedding model, vector fields, or embedding calls. The
default remains `vector` for existing vector deployments.

Set only reviewed target `AZURE_SEARCH_ENDPOINT` and `AZURE_OPENAI_ENDPOINT`
bindings, then run the same command without `--dry-run`. Do not copy a source
tenant's environment file. Regenerate the corpus from integrated branding/date
source changes before final loading. Populated indexes are refused before their
definitions are updated; `--replace-existing` requires explicit approval to
replace target content.

Run `--verify-only --check-canonical` after indexing completes to check all four
knowledge sources/base and the exact indexed IDs, content, paths, property, and
validity metadata, rather than treating index existence as acceptance. Complete
grounded property/date-specific retrieval separately under the runtime identity.

The knowledge base also exposes a native MCP endpoint:

```text
<verified-search-endpoint>/knowledgebases/hotel-foundryiq/mcp?api-version=2026-08-01-preview
```

Its `knowledge_base_retrieve` tool accepts
`{"query_variants": ["one complete natural-language question"]}`. The native MCP
schema does not expose `filterAddOn`; natural-language property/date constraints
are not a substitute for enforced filters. Keep the hosted `FoundryIQTool` direct
retrieval path for property/date boundaries confirmed from Fabric. An MCP response
can include uncited candidate references from other properties even when its answer
cites the correct source.

Acceptance must verify every cited reference against an actual canonical source,
its property and validity window, and the exact expected facts. Do not require every
retrieved candidate to be cited. Check Scottsdale and non-Scottsdale answers, an
in-window historical notice, and exclusion of that expired notice from current
retrieval. Verify archived blob bytes/hashes and source metadata for all 95 files.
