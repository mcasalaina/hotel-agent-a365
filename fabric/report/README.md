# HotelOperationsReport

`HotelOperationsReport` is a PBIR project bound by `semanticmodelid={{SEMANTICMODEL_ID}}` at deploy time.

`definition/version.json` must declare report format version `2.0.0`. This is
separate from its JSON schema version (`1.0.0`); declaring report format `1.0.0`
selects the legacy renderer, which loads this enhanced PBIR definition with no pages.
The deployment validator rejects a missing or incorrect format version.

Numeric booking and restaurant columns use explicit SUM aggregations in chart
value roles and summary tables. Bare column bindings group by individual values
instead of producing the intended totals and leave chart value axes empty.
All table value projections, including measures, must be active to appear.

The report ships two 1800 x 1200 dashboard pages, with all 19 existing visuals
arranged in non-overlapping grids:

1. **Performance & bookings** (`page_exec`, 9 visuals): occupancy, room revenue,
   length of stay, RevPAR, future bookings, cancellation rate, booked revenue,
   channel totals, and the existing food-and-beverage revenue availability card.
2. **Operations & service** (`page_service`, 10 visuals): property occupancy,
   completed stays, guest requests, dining reservations and covers, restaurant
   status totals, disputes, and maintenance response.

The four former page definitions are removed, not hidden. Deployment replaces
the report definition so the service also exposes exactly two tabs. The existing
`page_exec` and `page_service` identifiers and all visual names and data bindings
are retained. Food-and-beverage revenue remains blank because the source does
not provide that metric.
