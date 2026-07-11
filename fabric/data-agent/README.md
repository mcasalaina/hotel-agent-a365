# HotelOperationsAgent

`HotelOperationsAgent` is source-controlled as a **draft** Data Agent definition under `draft/Files/Config/...`.

Deployment updates only the draft definition. Publication is intentionally separated and must be
triggered from `HotelDataAgentRuntimePublish`.

The publish notebook uses the supported `fabric-data-agent-sdk` to remove and re-add both lakehouse
sources before publication. This forces Fabric to synchronize the live SQL endpoint schemas,
selects the governed table sets, applies source-specific instructions and examples, and then
publishes the staging configuration. Do not replace this with a direct `staging/publish` call:
definition-only imports can leave handcrafted lakehouse elements in a `NotAvailable` runtime state.
