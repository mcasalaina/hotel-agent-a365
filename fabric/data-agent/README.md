# HotelOperationsAgent

`HotelOperationsAgent` is source-controlled as a **draft** Data Agent definition under `draft/Files/Config/...`.

Deployment updates only the draft definition. Publication is intentionally separated and must be
triggered from `HotelDataAgentRuntimePublish`.

The publish notebook uses the supported `fabric-data-agent-sdk` to remove and re-add both lakehouse
sources before publication. This forces Fabric to synchronize the live SQL endpoint schemas,
selects the governed table sets, applies source-specific instructions and examples, and then
publishes the staging configuration. Do not replace this with a direct `staging/publish` call:
definition-only imports can leave handcrafted lakehouse elements in a `NotAvailable` runtime state.

Lakehouse examples run against the SQL analytics endpoint, so use T-SQL (`TOP`, `CAST(... AS date)`,
and `1`/`0` for bit comparisons) and explicit `dbo` table names, not Spark SQL syntax.

The publish notebook waits for every example to reach `Valid` before publishing. It retries only
SQL endpoint connection failures, with a bounded retry limit; invalid SQL, schema mismatches, and
validation timeouts fail publication explicitly. Publishing while validation is pending or failed
can leave stale errors in the published examples even after the draft is corrected. To repair
existing stale records, add and validate replacements before removing the old examples and
republishing; do not mark failed examples valid or remove them without replacements.
