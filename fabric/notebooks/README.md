# Fabric notebooks

Notebook execution order for a fresh Phase 1 deployment:

1. `HotelInitialLoad`
2. `HotelValidation`
3. `HotelAggregateRefresh`
4. `HotelValidation` (optional post-aggregate recheck)
5. Mutation notebooks as needed
6. `HotelDataAgentRuntimePublish` only after the Data Agent draft definition has been deployed; it
   requires independently reviewed native-readiness evidence, verifies existing native source
   configuration without rewriting it, publishes, and directly tests the published Data Agent MCP
   endpoint in isolation

All notebooks use a tagged **parameters** cell so Fabric notebook jobs can inject runtime values. The deployer binds every notebook to `HotelGuestServices`; cross-lakehouse reads and writes are parameterized with workspace and lakehouse IDs instead of hardcoding tenant values.
