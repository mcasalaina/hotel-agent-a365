# Demo scenario

The completed demo will show a guest-services agent answering property and policy questions, querying structured hotel operations, and carrying out supported synthetic actions only after explicit confirmation.

Named deterministic fixtures are in `data/fixtures/demo_scenarios.json`. Generate data
with `scripts/generate_hotel_data.py --scale full` and validate it with
`scripts/validate_hotel_data.py` before a later Fabric load.

Planned scenario groups:

1. Compare properties, amenities, and current operational notices.
2. Create, change, and cancel room and restaurant reservations.
3. Retrieve folios, open billing disputes, and track resolution.
4. Add pre-arrival and in-stay requests, including maintenance.
5. Combine Foundry IQ, both Fabric lakehouses, and Work IQ in one grounded workflow.

Named fixture coverage includes a waterfront amenity discovery question, multi-room
accessible family booking, changed-rate booking, flexible and nonrefundable
cancellations, a completed-stay folio dispute, a pre-arrival allergy/crib/late-arrival
request, in-stay HVAC maintenance, and a changeable dining reservation.
