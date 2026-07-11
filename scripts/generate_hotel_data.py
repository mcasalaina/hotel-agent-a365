"""Generate deterministic, fictional hotel source data and Foundry IQ documents.

The output is intentionally CSV/JSON only so it can be loaded by a later Fabric
workstream without introducing a local operational database.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from itertools import chain
from pathlib import Path

DATE_START = date(2026, 3, 1)
DATE_END = date(2027, 3, 31)
DEFAULT_SEED = 20260301
FIXTURES_PATH = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "demo_scenarios.json"
REQUIRED_TABLES = (
    "properties",
    "room_types",
    "rooms",
    "outlets",
    "amenities",
    "property_amenities",
    "guests",
    "reservations",
    "stays",
    "restaurant_reservations",
    "folios",
    "folio_transactions",
    "payments",
    "billing_disputes",
    "special_requests",
    "maintenance_requests",
    "work_orders",
    "daily_inventory",
    "daily_rates",
    "property_daily_metrics",
    "action_confirmations",
    "idempotency_records",
    "audit_events",
)
SCALE_COUNTS = {
    "demo": {
        "rooms_per_property": 8,
        "guests": 300,
        "reservations": 800,
        "stays": 420,
        "restaurant_reservations": 250,
        "billing_disputes": 15,
        "special_requests": 120,
        "maintenance_requests": 80,
    },
    "full": {
        "rooms_per_property": 200,
        "guests": 25_000,
        "reservations": 75_000,
        "stays": 45_000,
        "restaurant_reservations": 35_000,
        "billing_disputes": 3_000,
        "special_requests": 20_000,
        "maintenance_requests": 10_000,
    },
}
AMENITIES = (
    ("AMN-POOL", "Pool"),
    ("AMN-SPA", "Spa"),
    ("AMN-FITNESS", "Fitness centre"),
    ("AMN-PARKING", "Parking"),
    ("AMN-PET", "Pet welcome"),
    ("AMN-ACCESS", "Accessible rooms"),
    ("AMN-FAMILY", "Family services"),
    ("AMN-DINING", "On-site dining"),
)
POLICIES = (
    "reservation",
    "cancellation",
    "deposit",
    "no_show",
    "pet",
    "parking",
    "accessibility",
    "privacy",
    "payment",
    "folio",
    "dispute",
    "lost_and_found",
    "safety",
    "special_request",
    "maintenance",
)


@dataclass(frozen=True)
class PropertyProfile:
    property_id: str
    name: str
    region: str
    city: str
    country: str
    currency: str
    tax_rate: str
    facilities: str
    pool_hours: str
    parking: str
    transport: str


ROSTER = (
    (
        "Seattle Waterfront",
        "North America",
        "Seattle",
        "United States",
        "USD",
        "0.1025",
        "Indoor pool; harbor-view gym; coastal dining; ferry access",
        "06:00-22:00",
        "Valet parking; USD 52 nightly",
        "Ferry terminal is a five-minute walk",
    ),
    (
        "Vancouver Coal Harbour",
        "North America",
        "Vancouver",
        "Canada",
        "CAD",
        "0.1200",
        "Saltwater pool; spa; bicycle program; mountain-view lounge",
        "06:00-22:00",
        "Valet parking; CAD 48 nightly",
        "Waterfront rail station is a ten-minute walk",
    ),
    (
        "San Francisco Embarcadero",
        "North America",
        "San Francisco",
        "United States",
        "USD",
        "0.0863",
        "Rooftop terrace; fitness studio; market restaurant; no pool",
        "No pool",
        "Valet parking; USD 68 nightly",
        "Streetcar stop is adjacent to the entrance",
    ),
    (
        "Scottsdale Sonoran Resort",
        "North America",
        "Scottsdale",
        "United States",
        "USD",
        "0.0860",
        "Three pools; spa; desert garden; golf shuttle; kids club",
        "07:00-21:00",
        "Self parking included; valet USD 25 nightly",
        "Scheduled golf and local-area shuttle",
    ),
    (
        "Chicago River North",
        "North America",
        "Chicago",
        "United States",
        "USD",
        "0.1025",
        "Indoor lap pool; rooftop bar; meeting floor; river access",
        "05:30-22:00",
        "Valet parking; USD 62 nightly",
        "Metro station is a six-minute walk",
    ),
    (
        "New York Midtown",
        "North America",
        "New York",
        "United States",
        "USD",
        "0.0888",
        "24-hour fitness; executive lounge; brasserie; no pool",
        "No pool",
        "Valet parking; USD 75 nightly",
        "Major rail and subway links are nearby",
    ),
    (
        "Miami South Beach",
        "North America",
        "Miami",
        "United States",
        "USD",
        "0.0700",
        "Oceanfront pool; beach service; cabanas; Latin coastal dining",
        "07:00-20:00",
        "Valet parking; USD 55 nightly",
        "Beach boardwalk and local trolley nearby",
    ),
    (
        "Mexico City Polanco",
        "North America",
        "Mexico City",
        "Mexico",
        "MXN",
        "0.1600",
        "Rooftop pool; spa; contemporary Mexican restaurant; club lounge",
        "07:00-21:00",
        "Valet parking; MXN 420 nightly",
        "Private airport transfer available",
    ),
    (
        "London Mayfair",
        "Europe",
        "London",
        "United Kingdom",
        "GBP",
        "0.2000",
        "Afternoon-tea lounge; wellness suite; butler floor; no pool",
        "No pool",
        "Valet parking; GBP 65 nightly",
        "Underground station is an eight-minute walk",
    ),
    (
        "Paris Left Bank",
        "Europe",
        "Paris",
        "France",
        "EUR",
        "0.1000",
        "Courtyard restaurant; compact spa; family suites; no pool",
        "No pool",
        "Valet parking; EUR 48 nightly",
        "Metro station is a four-minute walk",
    ),
    (
        "Amsterdam Canal Quarter",
        "Europe",
        "Amsterdam",
        "Netherlands",
        "EUR",
        "0.0900",
        "Canal terrace; bicycle concierge; sauna; no pool",
        "No pool",
        "Limited valet parking; EUR 45 nightly",
        "Tram stop is two blocks away",
    ),
    (
        "Lisbon Baixa",
        "Europe",
        "Lisbon",
        "Portugal",
        "EUR",
        "0.2300",
        "Rooftop plunge pool; tile courtyard; Portuguese restaurant",
        "08:00-20:00",
        "Partner garage; EUR 28 nightly",
        "Airport metro connection is nearby",
    ),
    (
        "Barcelona Eixample",
        "Europe",
        "Barcelona",
        "Spain",
        "EUR",
        "0.1000",
        "Rooftop pool; tapas restaurant; fitness studio; family rooms",
        "08:00-21:00",
        "Partner garage; EUR 32 nightly",
        "Metro station is a three-minute walk",
    ),
    (
        "Rome Via Veneto",
        "Europe",
        "Rome",
        "Italy",
        "EUR",
        "0.1000",
        "Garden restaurant; wellness rooms; rooftop aperitivo; no pool",
        "No pool",
        "Valet parking; EUR 50 nightly",
        "Historic centre shuttle on request",
    ),
    (
        "Vienna Ring",
        "Europe",
        "Vienna",
        "Austria",
        "EUR",
        "0.1000",
        "Indoor pool; concert concierge; cafe; ballroom",
        "06:00-22:00",
        "Valet parking; EUR 42 nightly",
        "Ring tram stop is directly outside",
    ),
    (
        "Buenos Aires Puerto Madero",
        "South America",
        "Buenos Aires",
        "Argentina",
        "ARS",
        "0.2100",
        "Indoor pool; tango lounge; steak restaurant; river views",
        "06:00-22:00",
        "Valet parking; ARS 18000 nightly",
        "Waterfront promenade is adjacent",
    ),
    (
        "Rio Copacabana",
        "South America",
        "Rio de Janeiro",
        "Brazil",
        "BRL",
        "0.1200",
        "Rooftop infinity pool; beach service; Brazilian grill",
        "07:00-20:00",
        "Valet parking; BRL 95 nightly",
        "Beach access across the avenue",
    ),
    (
        "Sao Paulo Jardins",
        "South America",
        "Sao Paulo",
        "Brazil",
        "BRL",
        "0.1200",
        "Indoor pool; business lounge; spa; chef-led restaurant",
        "06:00-22:00",
        "Valet parking; BRL 90 nightly",
        "Scheduled business-district shuttle",
    ),
    (
        "Lima Miraflores",
        "South America",
        "Lima",
        "Peru",
        "PEN",
        "0.1800",
        "Ocean-view pool; ceviche restaurant; airport transfers",
        "07:00-21:00",
        "Valet parking; PEN 55 nightly",
        "Prebooked airport transfer available",
    ),
    (
        "Cartagena Walled City",
        "South America",
        "Cartagena",
        "Colombia",
        "USD",
        "0.1900",
        "Courtyard pool; rooftop bar; colonial-style suites",
        "08:00-20:00",
        "Valet parking; USD 30 nightly",
        "Vehicle access is coordinated with the old city",
    ),
)


def profiles() -> tuple[PropertyProfile, ...]:
    return tuple(
        PropertyProfile(
            property_id=f"HTL-{index:03d}",
            name=f"Lyrenza {entry[0]}",
            region=entry[1],
            city=entry[2],
            country=entry[3],
            currency=entry[4],
            tax_rate=entry[5],
            facilities=entry[6],
            pool_hours=entry[7],
            parking=entry[8],
            transport=entry[9],
        )
        for index, entry in enumerate(ROSTER, start=1)
    )


def dates() -> Iterator[date]:
    current = DATE_START
    while current <= DATE_END:
        yield current
        current += timedelta(days=1)


def stable_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def csv_write(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> int:
    count = 0
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def format_amount(value: int) -> str:
    return f"{value / 100:.2f}"


def seasonal_rate(day: date, property_number: int, room_type_number: int) -> int:
    high_season = 4500 if day.month in {6, 7, 8, 12} else 0
    weekend = 1800 if day.weekday() in {4, 5} else 0
    event = 2200 if day.day in {1, 15} else 0
    return 14500 + property_number * 140 + room_type_number * 900 + high_season + weekend + event


def read_fixtures() -> list[dict[str, str]]:
    fixture_data = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    scenarios = fixture_data["scenarios"]
    if not isinstance(scenarios, list):
        raise ValueError("demo_scenarios.json must contain a scenarios list")
    return [dict(item) for item in scenarios]


def build_reference(
    scale: str,
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    settings = SCALE_COUNTS[scale]
    property_rows = [asdict(profile) for profile in profiles()]
    room_types: list[dict[str, str]] = []
    rooms: list[dict[str, str]] = []
    outlets: list[dict[str, str]] = []
    property_amenities: list[dict[str, str]] = []
    for property_number, profile in enumerate(profiles(), start=1):
        for type_number, (type_name, capacity, accessible) in enumerate(
            (
                ("Classic", "2", "false"),
                ("Harbor", "2", "false"),
                ("Family", "4", "true"),
                ("Suite", "3", "true"),
            ),
            start=1,
        ):
            room_type_id = f"{profile.property_id}-RT-{type_number:02d}"
            room_types.append(
                {
                    "room_type_id": room_type_id,
                    "property_id": profile.property_id,
                    "name": type_name,
                    "capacity": capacity,
                    "accessible": accessible,
                    "base_rate": format_amount(
                        seasonal_rate(DATE_START, property_number, type_number)
                    ),
                }
            )
        for room_number in range(1, settings["rooms_per_property"] + 1):
            type_number = ((room_number - 1) % 4) + 1
            rooms.append(
                {
                    "room_id": f"{profile.property_id}-RM-{room_number:03d}",
                    "property_id": profile.property_id,
                    "room_type_id": f"{profile.property_id}-RT-{type_number:02d}",
                    "room_number": str(100 + room_number),
                    "room_status": (
                        "out_of_order"
                        if room_number == settings["rooms_per_property"]
                        else "available"
                    ),
                }
            )
        for outlet_number, (kind, name) in enumerate(
            (("restaurant", "Table"), ("lounge", "Lounge"), ("service", "In-room dining")), start=1
        ):
            outlets.append(
                {
                    "outlet_id": f"{profile.property_id}-OUT-{outlet_number:02d}",
                    "property_id": profile.property_id,
                    "name": f"{profile.city} {name}",
                    "outlet_type": kind,
                    "capacity": str(40 + outlet_number * 20),
                }
            )
        for amenity_id, _ in AMENITIES:
            property_amenities.append(
                {"property_id": profile.property_id, "amenity_id": amenity_id}
            )
    return property_rows, room_types, rooms, outlets, property_amenities


def build_guests(count: int) -> list[dict[str, str]]:
    return [
        {
            "guest_id": f"GST-{number:06d}",
            "first_name": f"Guest{number:05d}",
            "last_name": "Demo",
            "email": f"guest{number:05d}@example.test",
            "country": profiles()[(number - 1) % len(ROSTER)].country,
            "privacy_consent": "true",
        }
        for number in range(1, count + 1)
    ]


def reservation_row(
    reservation_id: str,
    guest_id: str,
    profile: PropertyProfile,
    room_type_number: int,
    check_in: date,
    nights: int,
    status: str,
    policy: str,
    room_count: int = 1,
) -> dict[str, str]:
    rate = seasonal_rate(check_in, int(profile.property_id[-3:]), room_type_number)
    return {
        "reservation_id": reservation_id,
        "guest_id": guest_id,
        "property_id": profile.property_id,
        "room_type_id": f"{profile.property_id}-RT-{room_type_number:02d}",
        "check_in": check_in.isoformat(),
        "check_out": (check_in + timedelta(days=nights)).isoformat(),
        "status": status,
        "cancellation_policy": policy,
        "room_count": str(room_count),
        "rate_total": format_amount(rate * nights * room_count),
        "currency": profile.currency,
        "channel": ("direct", "corporate", "partner")[int(reservation_id[-1], 36) % 3],
    }


def build_reservations(scale: str, fixtures: list[dict[str, str]]) -> list[dict[str, str]]:
    count = SCALE_COUNTS[scale]["reservations"]
    rows: list[dict[str, str]] = []
    profiles_by_id = {profile.property_id: profile for profile in profiles()}
    fixture_specs = {
        "family_accessibility": (
            "RES-DEMO-FAMILY",
            "GST-000001",
            date(2026, 8, 14),
            "future",
            "flexible",
            3,
            2,
        ),
        "rate_change": (
            "RES-DEMO-RATE-CHANGE",
            "GST-000002",
            date(2026, 4, 11),
            "future",
            "flexible",
            2,
            1,
        ),
        "cancellable": (
            "RES-DEMO-CANCEL-FLEX",
            "GST-000003",
            date(2026, 4, 5),
            "cancelled",
            "flexible",
            2,
            1,
        ),
        "nonrefundable": (
            "RES-DEMO-CANCEL-NRF",
            "GST-000004",
            date(2026, 4, 8),
            "cancelled",
            "nonrefundable",
            2,
            1,
        ),
        "folio_dispute": (
            "RES-DEMO-FOLIO",
            "GST-000005",
            date(2026, 3, 3),
            "completed",
            "flexible",
            2,
            1,
        ),
        "maintenance": (
            "RES-DEMO-INSTAY",
            "GST-000006",
            date(2026, 7, 9),
            "in_house",
            "flexible",
            2,
            1,
        ),
    }
    for fixture in fixtures:
        spec = fixture_specs.get(fixture["key"])
        if spec is None:
            continue
        reservation_id, guest_id, check_in, status, policy, nights, rooms = spec
        profile = profiles_by_id[fixture["property_id"]]
        rows.append(
            reservation_row(
                reservation_id, guest_id, profile, 3, check_in, nights, status, policy, rooms
            )
        )
    stay_count = SCALE_COUNTS[scale]["stays"]
    fixture_stay_count = sum(row["status"] in {"completed", "in_house"} for row in rows)
    generated_stay_limit = len(rows) + stay_count - fixture_stay_count
    for number in range(len(rows) + 1, count + 1):
        profile = profiles()[(number - 1) % len(ROSTER)]
        if number <= generated_stay_limit:
            status = "completed"
            check_in = DATE_START + timedelta(days=(number * 3) % 275)
        else:
            status = ("future", "arriving", "departed", "cancelled", "no_show")[number % 5]
            check_in = DATE_START + timedelta(days=(number * 7) % 392)
        policy = "nonrefundable" if number % 7 == 0 else "flexible"
        rows.append(
            reservation_row(
                f"RES-{number:07d}",
                f"GST-{((number - 1) % SCALE_COUNTS[scale]['guests']) + 1:06d}",
                profile,
                ((number - 1) % 4) + 1,
                check_in,
                (number % 4) + 1,
                status,
                policy,
            )
        )
    return rows


def build_stays(
    reservations: list[dict[str, str]], count: int, rooms_per_property: int
) -> list[dict[str, str]]:
    eligible = [row for row in reservations if row["status"] in {"completed", "in_house"}]
    if len(eligible) < count:
        raise ValueError("not enough completed or in-house reservations for requested stays")
    return [
        {
            "stay_id": f"STY-{number:07d}",
            "reservation_id": reservation["reservation_id"],
            "property_id": reservation["property_id"],
            "guest_id": reservation["guest_id"],
            "room_id": (
                f"{reservation['property_id']}-RM-{((number - 1) % rooms_per_property) + 1:03d}"
            ),
            "status": "in_house" if reservation["status"] == "in_house" else "completed",
            "actual_check_in": reservation["check_in"],
            "actual_check_out": reservation["check_out"],
        }
        for number, reservation in enumerate(eligible[:count], start=1)
    ]


def build_restaurant_reservations(scale: str) -> list[dict[str, str]]:
    count = SCALE_COUNTS[scale]["restaurant_reservations"]
    rows = [
        {
            "restaurant_reservation_id": "RR-DEMO-DINING",
            "guest_id": "GST-000001",
            "property_id": "HTL-004",
            "outlet_id": "HTL-004-OUT-01",
            "reservation_at": "2026-08-15T19:30:00",
            "party_size": "4",
            "status": "confirmed",
        }
    ]
    for number in range(2, count + 1):
        profile = profiles()[(number - 1) % len(ROSTER)]
        rows.append(
            {
                "restaurant_reservation_id": f"RR-{number:07d}",
                "guest_id": f"GST-{((number - 1) % SCALE_COUNTS[scale]['guests']) + 1:06d}",
                "property_id": profile.property_id,
                "outlet_id": f"{profile.property_id}-OUT-01",
                "reservation_at": (DATE_START + timedelta(days=(number * 5) % 396)).isoformat()
                + "T19:00:00",
                "party_size": str((number % 6) + 1),
                "status": ("confirmed", "seated", "cancelled")[number % 3],
            }
        )
    return rows


def build_folios(
    stays: list[dict[str, str]], reservations: list[dict[str, str]]
) -> list[dict[str, str]]:
    reservation_by_id = {row["reservation_id"]: row for row in reservations}
    rows: list[dict[str, str]] = []
    for number, stay in enumerate(stays, start=1):
        reservation = reservation_by_id[stay["reservation_id"]]
        rows.append(
            {
                "folio_id": f"FOL-{number:07d}",
                "stay_id": stay["stay_id"],
                "reservation_id": stay["reservation_id"],
                "guest_id": stay["guest_id"],
                "property_id": stay["property_id"],
                "currency": reservation["currency"],
                "total_charges": "155.00",
                "total_adjustments": "-5.00",
                "total_payments": "150.00",
                "total_refunds": "0.00",
                "balance": "0.00",
            }
        )
    return rows


def transaction_rows(folios: list[dict[str, str]]) -> Iterator[dict[str, str]]:
    items = (
        ("room_charge", "100.00"),
        ("tax", "12.00"),
        ("minibar", "15.00"),
        ("parking", "20.00"),
        ("adjustment", "-5.00"),
        ("service_charge", "8.00"),
    )
    for folio_number, folio in enumerate(folios, start=1):
        for item_number, (transaction_type, amount) in enumerate(items, start=1):
            yield {
                "folio_transaction_id": f"FTX-{folio_number:07d}-{item_number:02d}",
                "folio_id": folio["folio_id"],
                "transaction_type": transaction_type,
                "description": "Synthetic " + transaction_type.replace("_", " "),
                "amount": amount,
                "currency": folio["currency"],
                "posted_at": DATE_START.isoformat(),
            }


def payment_rows(folios: list[dict[str, str]]) -> Iterator[dict[str, str]]:
    for number, folio in enumerate(folios, start=1):
        yield {
            "payment_id": f"PAY-{number:07d}",
            "folio_id": folio["folio_id"],
            "payment_method": "card",
            "payment_token": f"tok_syn_{number:012d}",
            "card_mask": f"**** **** **** {1000 + (number % 9000):04d}",
            "amount": "150.00",
            "currency": folio["currency"],
            "payment_status": "captured",
        }


def build_billing_disputes(scale: str, folios: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = [
        {
            "billing_dispute_id": "BD-DEMO-MINIBAR",
            "folio_id": "FOL-0000001",
            "dispute_type": "minibar",
            "status": "open",
            "amount": "15.00",
            "opened_at": "2026-03-06T09:00:00",
        }
    ]
    for number in range(2, SCALE_COUNTS[scale]["billing_disputes"] + 1):
        folio = folios[(number - 1) % len(folios)]
        rows.append(
            {
                "billing_dispute_id": f"BD-{number:07d}",
                "folio_id": folio["folio_id"],
                "dispute_type": ("minibar", "parking")[number % 2],
                "status": ("open", "under_review", "resolved")[number % 3],
                "amount": ("15.00", "20.00")[number % 2],
                "opened_at": (DATE_START + timedelta(days=number % 396)).isoformat() + "T09:00:00",
            }
        )
    return rows


def build_service_records(
    scale: str, reservations: list[dict[str, str]], stays: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    special_requests: list[dict[str, str]] = [
        {
            "special_request_id": "SR-DEMO-PREARRIVAL",
            "reservation_id": "RES-DEMO-FAMILY",
            "guest_id": "GST-000001",
            "request_type": "accessibility_allergy_crib_late_arrival",
            "status": "confirmed",
            "requested_at": "2026-08-01T10:00:00",
            "details": "Step-free access, feather-free bedding, crib, arrival after 22:00.",
        }
    ]
    maintenance_requests: list[dict[str, str]] = [
        {
            "maintenance_request_id": "MR-DEMO-HVAC",
            "property_id": "HTL-004",
            "stay_id": "STY-0000002",
            "room_id": "HTL-004-RM-002",
            "request_type": "hvac",
            "status": "in_progress",
            "reported_at": "2026-07-10T21:00:00",
        }
    ]
    work_orders: list[dict[str, str]] = [
        {
            "work_order_id": "WO-DEMO-HVAC",
            "maintenance_request_id": "MR-DEMO-HVAC",
            "property_id": "HTL-004",
            "status": "assigned",
            "priority": "high",
            "opened_at": "2026-07-10T21:05:00",
        }
    ]
    for number in range(2, SCALE_COUNTS[scale]["special_requests"] + 1):
        reservation = reservations[(number - 1) % len(reservations)]
        special_requests.append(
            {
                "special_request_id": f"SR-{number:07d}",
                "reservation_id": reservation["reservation_id"],
                "guest_id": reservation["guest_id"],
                "request_type": ("late_arrival", "crib", "allergy", "accessibility")[number % 4],
                "status": ("requested", "confirmed", "fulfilled")[number % 3],
                "requested_at": (DATE_START + timedelta(days=number % 396)).isoformat()
                + "T09:00:00",
                "details": "Synthetic service request.",
            }
        )
    for number in range(2, SCALE_COUNTS[scale]["maintenance_requests"] + 1):
        stay = stays[(number - 1) % len(stays)]
        request_id = f"MR-{number:07d}"
        maintenance_requests.append(
            {
                "maintenance_request_id": request_id,
                "property_id": stay["property_id"],
                "stay_id": stay["stay_id"],
                "room_id": stay["room_id"],
                "request_type": ("hvac", "plumbing", "lighting")[number % 3],
                "status": ("open", "in_progress", "resolved")[number % 3],
                "reported_at": (DATE_START + timedelta(days=number % 396)).isoformat()
                + "T12:00:00",
            }
        )
        work_orders.append(
            {
                "work_order_id": f"WO-{number:07d}",
                "maintenance_request_id": request_id,
                "property_id": stay["property_id"],
                "status": ("assigned", "in_progress", "completed")[number % 3],
                "priority": ("normal", "high")[number % 2],
                "opened_at": (DATE_START + timedelta(days=number % 396)).isoformat() + "T12:05:00",
            }
        )
    return special_requests, maintenance_requests, work_orders


def daily_rows(
    rooms: list[dict[str, str]], room_types: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    rooms_by_type: dict[str, int] = {}
    for room in rooms:
        rooms_by_type[room["room_type_id"]] = rooms_by_type.get(room["room_type_id"], 0) + 1
    inventory: list[dict[str, str]] = []
    rates: list[dict[str, str]] = []
    metrics: list[dict[str, str]] = []
    for day_number, service_date in enumerate(dates()):
        for property_number, profile in enumerate(profiles(), start=1):
            sold = 0
            sellable_total = 0
            revenue = 0
            for type_number in range(1, 5):
                room_type_id = f"{profile.property_id}-RT-{type_number:02d}"
                physical = rooms_by_type[room_type_id]
                out_of_order = 1 if day_number % 31 == 0 and type_number == 4 else 0
                sellable = physical - out_of_order
                occupied = min(
                    sellable, (day_number + property_number + type_number) % (sellable + 1)
                )
                rate_cents = seasonal_rate(service_date, property_number, type_number)
                inventory.append(
                    {
                        "property_id": profile.property_id,
                        "room_type_id": room_type_id,
                        "service_date": service_date.isoformat(),
                        "physical_rooms": str(physical),
                        "out_of_order_rooms": str(out_of_order),
                        "sellable_rooms": str(sellable),
                        "occupied_rooms": str(occupied),
                    }
                )
                rates.append(
                    {
                        "property_id": profile.property_id,
                        "room_type_id": room_type_id,
                        "service_date": service_date.isoformat(),
                        "rate_plan": "BAR",
                        "currency": profile.currency,
                        "rate": format_amount(rate_cents),
                    }
                )
                sold += occupied
                sellable_total += sellable
                revenue += occupied * rate_cents
            metrics.append(
                {
                    "property_id": profile.property_id,
                    "service_date": service_date.isoformat(),
                    "sellable_rooms": str(sellable_total),
                    "occupied_rooms": str(sold),
                    "room_revenue": format_amount(revenue),
                    "currency": profile.currency,
                }
            )
    return inventory, rates, metrics


def build_control_records() -> tuple[
    list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]
]:
    return (
        [
            {
                "confirmation_id": "CNF-DEMO-001",
                "action_type": "restaurant_change",
                "target_id": "RR-DEMO-DINING",
                "status": "confirmed",
                "confirmed_at": "2026-08-10T10:00:00",
            }
        ],
        [
            {
                "idempotency_key": "idem-demo-restaurant-change",
                "action_type": "restaurant_change",
                "result_id": "RR-DEMO-DINING",
                "created_at": "2026-08-10T10:00:00",
            }
        ],
        [
            {
                "audit_event_id": "AUD-DEMO-001",
                "entity_type": "restaurant_reservation",
                "entity_id": "RR-DEMO-DINING",
                "action": "changed",
                "occurred_at": "2026-08-10T10:00:01",
                "actor_type": "synthetic_guest_services",
            }
        ],
    )


def clear_output(path: Path, suffixes: set[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_file() and child.suffix in suffixes:
            child.unlink()


def frontmatter(metadata: dict[str, str], body: str) -> str:
    metadata_lines = "\n".join(f"{key}: {value}" for key, value in metadata.items())
    return f"---\n{metadata_lines}\n---\n\n{body.rstrip()}\n"


def write_document(path: Path, metadata: dict[str, str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter(metadata, body), encoding="utf-8", newline="\n")


def generate_documents(docs_output: Path) -> dict[str, object]:
    if docs_output.exists():
        for category in ("properties", "policies", "dining-local", "operations"):
            category_path = docs_output / category
            if category_path.exists():
                for file in category_path.glob("*.generated.md"):
                    file.unlink()
    docs: list[Path] = []
    for profile in profiles():
        logical_path = f"foundryiq-docs/properties/{profile.property_id}.profile.generated.md"
        path = docs_output / "properties" / f"{profile.property_id}.profile.generated.md"
        write_document(
            path,
            {
                "document_id": f"DOC-PROP-{profile.property_id}",
                "title": f"{profile.name} property profile",
                "property_id": profile.property_id,
                "category": "property_profile",
                "valid_from": DATE_START.isoformat(),
                "valid_to": "2099-12-31",
                "locale": "en-US",
                "source_path": logical_path,
            },
            f"""# {profile.name}

## Permanent property facts

{profile.name} is in {profile.city}, {profile.country}, in the {profile.region} region.
Facilities: {profile.facilities}. Pool or water-facility hours: {profile.pool_hours}.
Parking: {profile.parking}. Transportation: {profile.transport}.

Accessible rooms include step-free routes and must be requested before arrival. Family
services and pet arrangements are confirmed with the reservation team.""",
        )
        docs.append(path)
        logical_path = (
            f"foundryiq-docs/dining-local/{profile.property_id}.dining-local.generated.md"
        )
        path = docs_output / "dining-local" / f"{profile.property_id}.dining-local.generated.md"
        write_document(
            path,
            {
                "document_id": f"DOC-LOCAL-{profile.property_id}",
                "title": f"{profile.name} dining and local guide",
                "property_id": profile.property_id,
                "category": "dining_local",
                "valid_from": DATE_START.isoformat(),
                "valid_to": "2099-12-31",
                "locale": "en-US",
                "source_path": logical_path,
            },
            f"""# Dining and local guide: {profile.name}

## Permanent guide

The on-site restaurant accepts reservations from 18:00 to 22:00. The lounge accepts
walk-ins when space permits. {profile.transport}. The concierge can provide current
directions, accessible routes, and family-friendly nearby recommendations.

Allergen preparation is coordinated in advance and is never guaranteed without a
confirmed special request.""",
        )
        docs.append(path)
        notice_start = date(2026, 4, 1) + timedelta(days=(int(profile.property_id[-3:]) - 1) * 9)
        notice_end = notice_start + timedelta(days=20)
        logical_path = f"foundryiq-docs/operations/{profile.property_id}.notice.generated.md"
        path = docs_output / "operations" / f"{profile.property_id}.notice.generated.md"
        write_document(
            path,
            {
                "document_id": f"DOC-NOTICE-{profile.property_id}",
                "title": f"{profile.name} dated operational notice",
                "property_id": profile.property_id,
                "category": "dated_notice",
                "valid_from": notice_start.isoformat(),
                "valid_to": notice_end.isoformat(),
                "locale": "en-US",
                "source_path": logical_path,
            },
            f"""# Dated operational notice: {profile.name}

This dated notice applies only from {notice_start.isoformat()} through
{notice_end.isoformat()}. Daytime maintenance may cause intermittent noise near one
guest corridor from 10:00 to 16:00. Services outside that corridor remain available.
Do not present this notice as a permanent property fact after its validity window.""",
        )
        docs.append(path)
        logical_path = f"foundryiq-docs/operations/{profile.property_id}.faq.generated.md"
        path = docs_output / "operations" / f"{profile.property_id}.faq.generated.md"
        write_document(
            path,
            {
                "document_id": f"DOC-FAQ-{profile.property_id}",
                "title": f"{profile.name} property FAQ",
                "property_id": profile.property_id,
                "category": "property_faq",
                "valid_from": DATE_START.isoformat(),
                "valid_to": "2099-12-31",
                "locale": "en-US",
                "source_path": logical_path,
            },
            f"""# Property FAQ: {profile.name}

## Permanent answers

Q: What are the pool or wellness hours?
A: {profile.pool_hours}.

Q: How does parking work?
A: {profile.parking}.

Q: How do guests reach the property?
A: {profile.transport}.

Refer to separately dated notices for temporary operational changes.""",
        )
        docs.append(path)
    for policy in POLICIES:
        logical_path = f"foundryiq-docs/policies/{policy}.generated.md"
        path = docs_output / "policies" / f"{policy}.generated.md"
        title = policy.replace("_", " ").title()
        write_document(
            path,
            {
                "document_id": f"DOC-POLICY-{policy.upper()}",
                "title": f"Chain-wide {title} procedure",
                "property_id": "chain-wide",
                "category": "guest_policy",
                "valid_from": DATE_START.isoformat(),
                "valid_to": "2099-12-31",
                "locale": "en-US",
                "source_path": logical_path,
            },
            f"""# Chain-wide {title} procedure

## Permanent policy

This fictional chain-wide procedure governs {policy.replace("_", " ")} requests.
Associates verify the synthetic guest record and reservation before sharing details or
making a change. Confirm the exact change, any price or penalty impact, and the policy
basis before recording an action. Payment records contain only a masked card value and
a synthetic payment token. Escalate safety, privacy, or unresolved maintenance matters
to the property duty leader.""",
        )
        docs.append(path)
    return {
        "count": len(docs),
        "hashes": {
            str(document.relative_to(docs_output)): stable_hash(document)
            for document in sorted(docs)
        },
    }


def generate(
    scale: str, output: Path, docs_output: Path, seed: int = DEFAULT_SEED
) -> dict[str, object]:
    if scale not in SCALE_COUNTS:
        raise ValueError(f"unsupported scale: {scale}")
    random.seed(seed)
    clear_output(output, {".csv", ".json"})
    fixture_rows = read_fixtures()
    property_rows, room_types, rooms, outlets, property_amenities = build_reference(scale)
    guests = build_guests(SCALE_COUNTS[scale]["guests"])
    reservations = build_reservations(scale, fixture_rows)
    stays = build_stays(
        reservations, SCALE_COUNTS[scale]["stays"], SCALE_COUNTS[scale]["rooms_per_property"]
    )
    restaurant_reservations = build_restaurant_reservations(scale)
    folios = build_folios(stays, reservations)
    billing_disputes = build_billing_disputes(scale, folios)
    special_requests, maintenance_requests, work_orders = build_service_records(
        scale, reservations, stays
    )
    daily_inventory, daily_rates, property_daily_metrics = daily_rows(rooms, room_types)
    action_confirmations, idempotency_records, audit_events = build_control_records()
    table_rows: dict[str, Iterable[dict[str, str]]] = {
        "properties": property_rows,
        "room_types": room_types,
        "rooms": rooms,
        "outlets": outlets,
        "amenities": [{"amenity_id": key, "name": value} for key, value in AMENITIES],
        "property_amenities": property_amenities,
        "guests": guests,
        "reservations": reservations,
        "stays": stays,
        "restaurant_reservations": restaurant_reservations,
        "folios": folios,
        "folio_transactions": transaction_rows(folios),
        "payments": payment_rows(folios),
        "billing_disputes": billing_disputes,
        "special_requests": special_requests,
        "maintenance_requests": maintenance_requests,
        "work_orders": work_orders,
        "daily_inventory": daily_inventory,
        "daily_rates": daily_rates,
        "property_daily_metrics": property_daily_metrics,
        "action_confirmations": action_confirmations,
        "idempotency_records": idempotency_records,
        "audit_events": audit_events,
    }
    counts: dict[str, int] = {}
    hashes: dict[str, str] = {}
    for table_name in REQUIRED_TABLES:
        table_path = output / f"{table_name}.csv"
        rows = table_rows[table_name]
        if isinstance(rows, list) and not rows:
            raise ValueError(f"{table_name} has no rows")
        if isinstance(rows, list):
            first_row = rows[0]
        else:
            iterator = iter(rows)
            first_row = next(iterator, None)
            rows = chain((first_row,), iterator) if first_row is not None else ()
        if first_row is None:
            raise ValueError(f"{table_name} has no rows")
        counts[table_name] = csv_write(table_path, list(first_row), rows)
        hashes[table_name] = stable_hash(table_path)
    docs_summary = generate_documents(docs_output)
    manifest: dict[str, object] = {
        "generator_version": 1,
        "seed": seed,
        "scale": scale,
        "date_range": {"start": DATE_START.isoformat(), "end": DATE_END.isoformat()},
        "counts": counts,
        "hashes": hashes,
        "documents": docs_summary,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", choices=tuple(SCALE_COUNTS), default="full")
    parser.add_argument("--output", type=Path, default=Path("data/generated"))
    parser.add_argument("--docs-output", type=Path, default=Path("foundryiq-docs"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = generate(args.scale, args.output, args.docs_output, args.seed)
    counts = manifest["counts"]
    documents = manifest["documents"]
    assert isinstance(counts, dict)
    assert isinstance(documents, dict)
    print(
        f"Generated {args.scale} data: "
        f"{sum(int(value) for value in counts.values())} CSV rows and "
        f"{documents['count']} documents."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
