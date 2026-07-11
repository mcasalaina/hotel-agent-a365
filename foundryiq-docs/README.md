# Foundry IQ source documents

Run `scripts/generate_hotel_data.py` to create the deterministic Markdown corpus in
the four category folders. Each generated document uses stable frontmatter for
document ID, title, property, category, validity window, locale, and source path.
Generated document filenames end in `.generated.md` and are intentionally ignored;
the later Search/Foundry IQ workstream can upload them without changing cloud
resources here.
