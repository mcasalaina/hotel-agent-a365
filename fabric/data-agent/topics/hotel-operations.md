## Property identity and facilities

Use `properties` for the complete official hotel roster, official names, city,
region, currency, parking, transportation and pool hours. `property_id` is an
internal join key, not the property's display name.

Resolve a named hotel to its actual property record before querying its rooms,
outlets, rates or maintenance. Do not infer identity or location from a similar
name or the order in which properties were returned.

Use `amenities` and `property_amenities` for the recorded amenity associations.
Use `outlets` for actual dining outlet names, types and capacity. Do not turn
an amenity or outlet description into an unrecorded availability promise.

## Physical rooms and accessible room categories

`room_types` describes property-specific categories, capacity, accessibility and
base rates. `rooms` describes physical rooms. Join on the documented property
and room-type keys. A room category, a reservation for two rooms and a physical
room assignment are different things.

Use the recorded accessibility attribute for the requested property and room
type. Guest accessibility requests and their fulfillment status are in
HotelGuestServices, not an implied consequence of the room-type attribute.

## Daily inventory and room rates

Use `daily_inventory` for the requested property, room type and service date.
Distinguish physical rooms, sellable rooms, occupied rooms and out-of-order rooms.
Do not treat the physical-room total as the sellable-room denominator.

Use `daily_rates` and `rate_plans` for the actual date, room category and plan.
Do not substitute a room-type base rate for a date-specific reservation quote.
Preserve the property's currency and the plan's recorded terms.

Occupancy before 2026-09-01 is historical actual occupancy. Later occupancy
represents confirmed on-books nights, not completed stays. Keep boundary-day
activity separate when a question explicitly asks for past or future records.

## Operational performance and recognized revenue

`property_daily_metrics` contains operating inputs, including occupied rooms,
sellable rooms and recognized room revenue. Recognized room revenue is zero on
and after 2026-09-01. Booked revenue is a different concept.

Route certified OCC, ADR, RevPAR, ALOS and other governed KPI questions to
HotelOperationsModel. Do not invent food-and-beverage revenue or total-revenue
measures when the corresponding underlying amounts are unavailable.

Amounts retain source-currency semantics. A chain-wide raw sum across different
currencies is not a normalized monetary total.

## Maintenance issues and work orders

Use `maintenance_requests` for the original operational issue and `work_orders`
for its associated work. Join using the documented maintenance-request key.
Preserve recorded property, room, priority, status and timestamps.

A reported or open issue is not resolved work. Do not claim a work order was
created, escalated or completed without the corresponding recorded outcome.
Use guest-service stay records separately when the question needs guest or
reservation context.

## Complete chain-wide results

Start with all rows in `properties` when a question requires the whole estate.
Return the official property names and preserve properties with zero matching
activity. A fact table containing only nonzero groups is not the complete roster.

When guest-service facts are needed, query their authoritative source separately
and combine results using documented stable keys. Do not invent a cross-source
SQL join or treat the GuestServices `ops_` shortcuts as a replacement for the
HotelOperations authority boundary.
