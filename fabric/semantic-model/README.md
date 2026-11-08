# HotelOperationsModel

`HotelOperationsModel` is a Direct Lake TMDL semantic model over `HotelGuestServices` aggregate tables plus limited `ops_` shortcuts from `HotelOperations`.

Highlights:

- Direct Lake named expressions are templated with workspace and lakehouse IDs at deploy time.
- Technical IDs are hidden.
- Measures are limited to metrics supported by the committed CSV contract.
- `Food and Beverage Revenue` and `TRevPAR` intentionally return `BLANK()` because the contract has no supported F&B revenue fact.

Deploy this model and its report with the current Azure CLI identity:

```bash
python scripts/deploy_semantic_model_and_report.py \
  --workspace-id "$FABRIC_WORKSPACE_ID" \
  --guest-lakehouse-id "$HOTEL_GUEST_SERVICES_LAKEHOUSE_ID" \
  --ops-lakehouse-id "$HOTEL_OPERATIONS_LAKEHOUSE_ID" \
  --tenant-id "$AZURE_TENANT_ID" \
  --subscription-id "$AZURE_SUBSCRIPTION_ID" \
  --apply --output artifacts/hotel-model-report-deployment.json
```

Omit `--apply` for a read-only plan. Existing uniquely named items are updated in place,
without deleting their IDs or creating duplicates. The script does not change Azure CLI
authentication, create workspaces, or change capacities. It verifies live definitions,
all nine model tables, eight Direct Lake partitions, and the report's model binding.

Before using `--refresh`, load these Delta tables or shortcuts in `HotelGuestServices`:
`ops_properties`, `ops_outlets`, `agg_property_kpis_daily`, `agg_booking_pace_daily`,
`agg_restaurant_daily`, `agg_disputes_daily`, `agg_requests_daily`, and
`agg_maintenance_response_daily`. Refresh also calculates the Date table and runs a
read-only DAX validation. Missing connection credentials require configuration in the
service. Credential failures are not retried.
