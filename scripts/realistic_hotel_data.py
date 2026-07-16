"""Causally coherent deterministic hotel operations data.

The functions in this module preserve the committed CSV contracts while replacing
the original modulo-based fixture generator with a fixed-seed operating model.
Demand drives occupancy, occupied room nights drive completed stays, stays drive
service and maintenance workload, and folios drive billing disputes.
"""
# ruff: noqa: E501

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any


@dataclass(frozen=True)
class OperatingProfile:
    property_id: str
    room_inventory: int
    market: str
    service_tier: str
    business_mix: float
    baseline_demand: float
    average_length_of_stay: float
    operational_quality: float
    seasonal_amplitude: float
    peak_day_of_year: int
    base_adr: float
    service_request_rate: float
    maintenance_request_rate: float


# fmt: off
OPERATING_PROFILES = (
    OperatingProfile("HTL-001", 116, "urban-waterfront", "upscale", 0.58, 0.72, 2.35, 0.88, 0.09, 205, 249.0, 0.105, 0.040),
    OperatingProfile("HTL-002", 132, "urban-waterfront", "upscale", 0.52, 0.70, 2.55, 0.91, 0.10, 200, 275.0, 0.100, 0.035),
    OperatingProfile("HTL-003", 128, "gateway-city", "upper-upscale", 0.72, 0.74, 2.15, 0.86, 0.08, 260, 319.0, 0.090, 0.045),
    OperatingProfile("HTL-004", 154, "desert-resort", "resort", 0.24, 0.68, 3.45, 0.89, 0.17, 40, 289.0, 0.170, 0.042),
    OperatingProfile("HTL-005", 142, "urban-business", "upscale", 0.76, 0.71, 2.05, 0.84, 0.12, 285, 234.0, 0.085, 0.052),
    OperatingProfile("HTL-006", 168, "gateway-city", "luxury", 0.78, 0.79, 2.20, 0.92, 0.07, 275, 429.0, 0.120, 0.032),
    OperatingProfile("HTL-007", 136, "beach-resort", "resort", 0.21, 0.75, 3.70, 0.83, 0.15, 25, 379.0, 0.190, 0.057),
    OperatingProfile("HTL-008", 112, "urban-cultural", "upper-upscale", 0.62, 0.69, 2.45, 0.82, 0.08, 300, 4200.0, 0.115, 0.055),
    OperatingProfile("HTL-009", 118, "gateway-city", "luxury", 0.73, 0.80, 2.30, 0.94, 0.06, 190, 515.0, 0.135, 0.028),
    OperatingProfile("HTL-010", 92, "urban-cultural", "boutique", 0.42, 0.76, 2.85, 0.90, 0.11, 185, 365.0, 0.125, 0.036),
    OperatingProfile("HTL-011", 84, "urban-leisure", "boutique", 0.39, 0.73, 2.65, 0.87, 0.10, 175, 329.0, 0.120, 0.041),
    OperatingProfile("HTL-012", 76, "city-break", "boutique", 0.31, 0.67, 3.05, 0.85, 0.14, 210, 265.0, 0.145, 0.046),
    OperatingProfile("HTL-013", 108, "city-break", "upscale", 0.35, 0.78, 3.15, 0.88, 0.13, 205, 349.0, 0.155, 0.040),
    OperatingProfile("HTL-014", 96, "urban-cultural", "luxury", 0.37, 0.75, 2.90, 0.93, 0.12, 190, 445.0, 0.140, 0.030),
    OperatingProfile("HTL-015", 102, "urban-cultural", "upper-upscale", 0.55, 0.70, 2.40, 0.95, 0.13, 350, 315.0, 0.105, 0.025),
    OperatingProfile("HTL-016", 110, "urban-leisure", "upscale", 0.46, 0.64, 2.75, 0.78, 0.10, 25, 68000.0, 0.125, 0.066),
    OperatingProfile("HTL-017", 124, "beach-resort", "resort", 0.18, 0.77, 3.55, 0.81, 0.16, 20, 980.0, 0.185, 0.062),
    OperatingProfile("HTL-018", 146, "urban-business", "upper-upscale", 0.81, 0.68, 1.95, 0.80, 0.08, 110, 920.0, 0.080, 0.060),
    OperatingProfile("HTL-019", 88, "urban-leisure", "upscale", 0.44, 0.66, 2.60, 0.86, 0.09, 35, 610.0, 0.120, 0.044),
    OperatingProfile("HTL-020", 68, "heritage-leisure", "boutique", 0.16, 0.72, 3.25, 0.89, 0.11, 15, 285.0, 0.165, 0.038),
)
# fmt: on

PROFILE_BY_ID = {profile.property_id: profile for profile in OPERATING_PROFILES}
ROOM_TYPE_NAMES = ("Classic", "Deluxe", "Family", "Suite")
ROOM_TYPE_MULTIPLIERS = (1.00, 1.18, 1.42, 1.78)
CHANNELS = ("direct", "corporate", "ota", "wholesale")
REQUEST_TYPES = (
    "housekeeping",
    "extra_towels",
    "late_checkout",
    "airport_transfer",
    "concierge",
    "crib",
    "allergy",
    "accessibility",
    "room_service",
)
MAINTENANCE_TYPES = ("hvac", "plumbing", "electrical", "lighting", "appliance", "door_lock")
DISPUTE_TYPES = (
    "room_rate",
    "minibar",
    "parking",
    "duplicate_charge",
    "tax_or_fee",
    "service_charge",
    "cancellation_fee",
)


def profile_manifest() -> list[dict[str, Any]]:
    """Return the operating assumptions persisted in the generated manifest."""
    return [asdict(profile) for profile in OPERATING_PROFILES]


def build_realistic_tables(
    *,
    scale: str,
    property_rows: list[dict[str, str]],
    fixture_rows: list[dict[str, str]],
    start: date,
    end: date,
    seed: int,
    amenities: Sequence[tuple[str, str]],
) -> dict[str, Iterable[dict[str, str]]]:
    rng = random.Random(seed)
    room_types, rooms, outlets, property_amenities = _build_reference(
        scale, property_rows, amenities
    )
    inventory, rates, metrics = _build_daily_operations(
        property_rows, room_types, rooms, start, end, rng
    )
    guest_count = 300 if scale == "demo" else 25_000
    guests = _build_guests(property_rows, guest_count)
    reservations, stays = _build_reservations_and_stays(
        scale,
        property_rows,
        fixture_rows,
        guests,
        rooms,
        metrics,
        start,
        end,
        rng,
    )
    restaurant = _build_restaurant_reservations(
        scale, property_rows, guests, outlets, metrics, start, end, rng
    )
    folios = _build_folios(stays, reservations, rng)
    disputes = _build_disputes(folios, reservations, start, end, rng)
    special_requests, maintenance, work_orders = _build_service_records(
        reservations, stays, start, end, rng
    )
    return {
        "properties": property_rows,
        "room_types": room_types,
        "rooms": rooms,
        "outlets": outlets,
        "property_amenities": property_amenities,
        "guests": guests,
        "reservations": reservations,
        "stays": stays,
        "restaurant_reservations": restaurant,
        "folios": folios,
        "folio_transactions": _transaction_rows(folios),
        "payments": _payment_rows(folios),
        "billing_disputes": disputes,
        "special_requests": special_requests,
        "maintenance_requests": maintenance,
        "work_orders": work_orders,
        "daily_inventory": inventory,
        "daily_rates": rates,
        "property_daily_metrics": metrics,
    }


def _build_reference(
    scale: str,
    properties: list[dict[str, str]],
    amenities: Sequence[tuple[str, str]],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    room_types: list[dict[str, str]] = []
    rooms: list[dict[str, str]] = []
    outlets: list[dict[str, str]] = []
    property_amenities: list[dict[str, str]] = []
    for property_row in properties:
        property_id = property_row["property_id"]
        profile = PROFILE_BY_ID[property_id]
        inventory = 8 if scale == "demo" else profile.room_inventory
        type_counts = _allocate_counts(inventory, (0.49, 0.27, 0.15, 0.09), minimum=1)
        room_number = 1
        for type_number, (name, capacity, accessible, multiplier, count) in enumerate(
            zip(
                ROOM_TYPE_NAMES,
                (2, 2, 4, 3),
                (False, False, True, True),
                ROOM_TYPE_MULTIPLIERS,
                type_counts,
                strict=True,
            ),
            start=1,
        ):
            room_type_id = f"{property_id}-RT-{type_number:02d}"
            room_types.append(
                {
                    "room_type_id": room_type_id,
                    "property_id": property_id,
                    "name": name,
                    "capacity": str(capacity),
                    "accessible": str(accessible).lower(),
                    "base_rate": f"{profile.base_adr * multiplier:.2f}",
                }
            )
            for _ in range(count):
                rooms.append(
                    {
                        "room_id": f"{property_id}-RM-{room_number:03d}",
                        "property_id": property_id,
                        "room_type_id": room_type_id,
                        "room_number": str(100 + room_number),
                        "room_status": "available",
                    }
                )
                room_number += 1
        for outlet_number, (kind, name) in enumerate(
            (("restaurant", "Table"), ("lounge", "Lounge"), ("service", "In-room dining")),
            start=1,
        ):
            outlet_capacity = max(36, round(inventory * (0.38 + outlet_number * 0.08)))
            outlets.append(
                {
                    "outlet_id": f"{property_id}-OUT-{outlet_number:02d}",
                    "property_id": property_id,
                    "name": f"{property_row['city']} {name}",
                    "outlet_type": kind,
                    "capacity": str(outlet_capacity),
                }
            )
        amenity_probability = 0.72 + 0.18 * profile.operational_quality
        for amenity_number, (amenity_id, _) in enumerate(amenities):
            deterministic_score = ((int(property_id[-3:]) * 17 + amenity_number * 11) % 100) / 100
            if deterministic_score <= amenity_probability or amenity_id in {
                "AMN-DINING",
                "AMN-ACCESS",
            }:
                property_amenities.append({"property_id": property_id, "amenity_id": amenity_id})
    return room_types, rooms, outlets, property_amenities


def _build_daily_operations(
    properties: list[dict[str, str]],
    room_types: list[dict[str, str]],
    rooms: list[dict[str, str]],
    start: date,
    end: date,
    rng: random.Random,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    physical_by_type = Counter(room["room_type_id"] for room in rooms)
    dates = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    inventory_rows: list[dict[str, str]] = []
    rate_rows: list[dict[str, str]] = []
    metric_rows: list[dict[str, str]] = []
    correlated_noise = {property_row["property_id"]: 0.0 for property_row in properties}

    for service_date in dates:
        for property_row in properties:
            property_id = property_row["property_id"]
            profile = PROFILE_BY_ID[property_id]
            noise = 0.76 * correlated_noise[property_id] + rng.gauss(0.0, 0.012)
            correlated_noise[property_id] = noise
            occupancy = _demand_rate(profile, service_date, noise)
            type_physical = [
                physical_by_type[f"{property_id}-RT-{number:02d}"] for number in range(1, 5)
            ]
            expected_ooo = sum(type_physical) * (
                0.004 + (1.0 - profile.operational_quality) * 0.032
            )
            maintenance_pulse = (
                1 if (service_date.toordinal() + int(property_id[-3:]) * 13) % 97 == 0 else 0
            )
            total_ooo = min(
                max(0, round(expected_ooo + rng.gauss(0.0, 0.45)) + maintenance_pulse),
                max(0, sum(type_physical) - 4),
            )
            ooo_by_type = _allocate_counts(total_ooo, (0.30, 0.28, 0.22, 0.20))
            sellable_by_type = [
                max(0, physical - ooo)
                for physical, ooo in zip(type_physical, ooo_by_type, strict=True)
            ]
            total_sellable = sum(sellable_by_type)
            occupied_total = min(total_sellable, max(0, round(total_sellable * occupancy)))
            occupied_by_type = _allocate_occupied(
                occupied_total, sellable_by_type, (1.02, 1.05, 0.97, 0.92)
            )
            revenue = 0.0
            for type_number in range(1, 5):
                room_type_id = f"{property_id}-RT-{type_number:02d}"
                physical = type_physical[type_number - 1]
                out_of_order = ooo_by_type[type_number - 1]
                sellable = sellable_by_type[type_number - 1]
                occupied = occupied_by_type[type_number - 1]
                rate = _daily_rate(profile, service_date, type_number, occupied / max(sellable, 1))
                inventory_rows.append(
                    {
                        "property_id": property_id,
                        "room_type_id": room_type_id,
                        "service_date": service_date.isoformat(),
                        "physical_rooms": str(physical),
                        "out_of_order_rooms": str(out_of_order),
                        "sellable_rooms": str(sellable),
                        "occupied_rooms": str(occupied),
                    }
                )
                rate_rows.append(
                    {
                        "property_id": property_id,
                        "room_type_id": room_type_id,
                        "service_date": service_date.isoformat(),
                        "rate_plan": "BAR",
                        "currency": property_row["currency"],
                        "rate": f"{rate:.2f}",
                    }
                )
                revenue += occupied * rate
            metric_rows.append(
                {
                    "property_id": property_id,
                    "service_date": service_date.isoformat(),
                    "sellable_rooms": str(total_sellable),
                    "occupied_rooms": str(sum(occupied_by_type)),
                    "room_revenue": f"{revenue:.2f}",
                    "currency": property_row["currency"],
                }
            )
    return inventory_rows, rate_rows, metric_rows


def _demand_rate(profile: OperatingProfile, service_date: date, noise: float) -> float:
    day = service_date.timetuple().tm_yday
    seasonal = profile.seasonal_amplitude * math.cos(
        2.0 * math.pi * (day - profile.peak_day_of_year) / 365.25
    )
    is_weekend = service_date.weekday() in {4, 5}
    weekend_effect = (
        (1.0 - profile.business_mix) * 0.065 - profile.business_mix * 0.040
        if is_weekend
        else profile.business_mix * 0.012
    )
    event_center = ((int(profile.property_id[-3:]) * 41) % 330) + 18
    event_distance = min(abs(day - event_center), 365 - abs(day - event_center))
    event_effect = 0.075 * math.exp(-((event_distance / 3.2) ** 2))
    holiday_effect = 0.0
    if (service_date.month, service_date.day) in {(12, 24), (12, 25), (12, 31), (1, 1)}:
        holiday_effect = 0.075 * (1.0 - profile.business_mix) - 0.045 * profile.business_mix
    value = (
        profile.baseline_demand + seasonal + weekend_effect + event_effect + holiday_effect + noise
    )
    return min(0.955, max(0.38, value))


def _daily_rate(
    profile: OperatingProfile,
    service_date: date,
    type_number: int,
    occupancy: float,
) -> float:
    day = service_date.timetuple().tm_yday
    season = 0.10 * math.cos(2.0 * math.pi * (day - profile.peak_day_of_year) / 365.25)
    weekend = 0.045 if service_date.weekday() in {4, 5} and profile.business_mix < 0.5 else 0.0
    compression = max(0.0, occupancy - 0.76) * 0.52
    rate = (
        profile.base_adr
        * ROOM_TYPE_MULTIPLIERS[type_number - 1]
        * (1.0 + season + weekend + compression)
    )
    return max(profile.base_adr * 0.68, round(rate, 2))


def _build_guests(properties: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    named_guests = {
        1: ("Maria", "Garcia", "mariagarcia@cam3652609.onmicrosoft.com"),
        2: ("Marco", "Casalaina", "mcasalaina.local@cam3652609.onmicrosoft.com"),
    }
    rows: list[dict[str, str]] = []
    for number in range(1, count + 1):
        first_name, last_name, email = named_guests.get(
            number,
            (f"Guest{number:05d}", "Demo", f"guest{number:05d}@example.test"),
        )
        rows.append(
            {
                "guest_id": f"GST-{number:06d}",
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "country": properties[(number - 1) % len(properties)]["country"],
                "privacy_consent": "true",
            }
        )
    return rows


def _build_reservations_and_stays(
    scale: str,
    properties: list[dict[str, str]],
    fixture_rows: list[dict[str, str]],
    guests: list[dict[str, str]],
    rooms: list[dict[str, str]],
    metrics: list[dict[str, str]],
    start: date,
    end: date,
    rng: random.Random,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    properties_by_id = {row["property_id"]: row for row in properties}
    rooms_by_property_type: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for room in rooms:
        rooms_by_property_type[(room["property_id"], room["room_type_id"])].append(room["room_id"])
    metrics_by_property: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for metric in metrics:
        metrics_by_property[metric["property_id"]].append(metric)

    reservations = _fixture_reservations(fixture_rows, properties_by_id)
    stays = [
        {
            "stay_id": "STY-0000001",
            "reservation_id": "RES-DEMO-FOLIO",
            "property_id": "HTL-005",
            "guest_id": "GST-000005",
            "room_id": "HTL-005-RM-001",
            "status": "completed",
            "actual_check_in": "2026-03-03T15:00:00",
            "actual_check_out": "2026-03-05T11:00:00",
        },
        {
            "stay_id": "STY-0000002",
            "reservation_id": "RES-DEMO-INSTAY",
            "property_id": "HTL-004",
            "guest_id": "GST-000006",
            "room_id": "HTL-004-RM-002",
            "status": "in_house",
            "actual_check_in": "2026-07-09T16:00:00",
            "actual_check_out": "2026-07-11T11:00:00",
        },
    ]
    reservation_number = 1
    stay_number = 3
    guest_count = len(guests)
    fixture_completed_nights = Counter({"HTL-005": 2})

    for property_row in properties:
        property_id = property_row["property_id"]
        profile = PROFILE_BY_ID[property_id]
        property_metrics = sorted(
            metrics_by_property[property_id], key=lambda row: row["service_date"]
        )
        occupied_nights = sum(int(row["occupied_rooms"]) for row in property_metrics)
        remaining_nights = occupied_nights - fixture_completed_nights[property_id]
        target_stays = max(1, round(remaining_nights / profile.average_length_of_stay))
        lengths = _stay_lengths(remaining_nights, target_stays, profile, rng)
        stays_by_length = Counter(lengths)
        desired: list[tuple[date, int]] = []
        all_dates = [date.fromisoformat(row["service_date"]) for row in property_metrics]
        all_weights = [max(1, int(row["occupied_rooms"])) for row in property_metrics]
        for length, count in stays_by_length.items():
            valid_count = max(1, len(all_dates) - length)
            selected_dates = rng.choices(
                all_dates[:valid_count], weights=all_weights[:valid_count], k=count
            )
            desired.extend((check_in, length) for check_in in selected_dates)
        desired.sort(key=lambda item: (item[0], item[1]))
        type_weights = _room_type_weights(rooms_by_property_type, property_id)
        for check_in, nights in desired:
            check_out = check_in + timedelta(days=nights)
            room_type_number = rng.choices((1, 2, 3, 4), weights=type_weights, k=1)[0]
            room_type_id = f"{property_id}-RT-{room_type_number:02d}"
            candidate_rooms = rooms_by_property_type[(property_id, room_type_id)]
            room_id = candidate_rooms[
                (stay_number + rng.randrange(len(candidate_rooms))) % len(candidate_rooms)
            ]
            guest_id = f"GST-{((reservation_number * 37 + int(property_id[-3:]) * 101) % guest_count) + 1:06d}"
            reservation_id = f"RES-{reservation_number:07d}"
            channel = _channel(profile, rng)
            rate_total = (
                _daily_rate(profile, check_in, room_type_number, profile.baseline_demand) * nights
            )
            reservations.append(
                _reservation(
                    reservation_id,
                    guest_id,
                    property_row,
                    room_type_number,
                    check_in,
                    check_out,
                    "completed",
                    channel,
                    rate_total,
                )
            )
            stays.append(
                {
                    "stay_id": f"STY-{stay_number:07d}",
                    "reservation_id": reservation_id,
                    "property_id": property_id,
                    "guest_id": guest_id,
                    "room_id": room_id,
                    "status": "completed",
                    "actual_check_in": f"{check_in.isoformat()}T15:{rng.randrange(0, 60):02d}:00",
                    "actual_check_out": f"{check_out.isoformat()}T11:{rng.randrange(0, 30):02d}:00",
                }
            )
            reservation_number += 1
            stay_number += 1

        extra_count = max(18, round(target_stays * (0.055 if scale == "full" else 0.035)))
        required_statuses = ["future", "arriving", "departed", "cancelled", "no_show", "in_house"]
        for extra_number in range(extra_count):
            status = (
                required_statuses[extra_number]
                if extra_number < len(required_statuses)
                else rng.choices(
                    required_statuses,
                    weights=(0.38, 0.10, 0.16, 0.22, 0.08, 0.06),
                    k=1,
                )[0]
            )
            if status in {"future", "arriving", "in_house"}:
                anchor = date(2026, 7, 12) + timedelta(
                    days=(extra_number + int(property_id[-3:])) % 7
                )
                check_in = min(anchor, end - timedelta(days=4))
            else:
                check_in = start + timedelta(days=rng.randrange(max(1, (end - start).days - 6)))
            nights = rng.choices((1, 2, 3, 4, 5, 6), weights=(12, 27, 26, 18, 10, 7), k=1)[0]
            check_out = min(end, check_in + timedelta(days=nights))
            if check_out <= check_in:
                check_in = end - timedelta(days=1)
                check_out = end
            room_type_number = rng.choices((1, 2, 3, 4), weights=type_weights, k=1)[0]
            guest_id = f"GST-{rng.randrange(1, guest_count + 1):06d}"
            rate_total = (
                _daily_rate(profile, check_in, room_type_number, profile.baseline_demand)
                * (check_out - check_in).days
            )
            reservations.append(
                _reservation(
                    f"RES-{reservation_number:07d}",
                    guest_id,
                    property_row,
                    room_type_number,
                    check_in,
                    check_out,
                    status,
                    _channel(profile, rng),
                    rate_total,
                )
            )
            reservation_number += 1
    return reservations, stays


def _fixture_reservations(
    fixtures: list[dict[str, str]], properties: dict[str, dict[str, str]]
) -> list[dict[str, str]]:
    specs = {
        "family_accessibility": (
            "RES-DEMO-FAMILY",
            "GST-000001",
            date(2026, 8, 14),
            "future",
            3,
            3,
            2,
        ),
        "rate_change": ("RES-DEMO-RATE-CHANGE", "GST-000002", date(2026, 4, 11), "future", 3, 2, 1),
        "cancellable": (
            "RES-DEMO-CANCEL-FLEX",
            "GST-000003",
            date(2026, 4, 5),
            "cancelled",
            2,
            2,
            1,
        ),
        "nonrefundable": (
            "RES-DEMO-CANCEL-NRF",
            "GST-000004",
            date(2026, 4, 8),
            "cancelled",
            2,
            2,
            1,
        ),
        "folio_dispute": ("RES-DEMO-FOLIO", "GST-000005", date(2026, 3, 3), "completed", 1, 2, 1),
        "maintenance": ("RES-DEMO-INSTAY", "GST-000006", date(2026, 7, 9), "in_house", 1, 2, 1),
    }
    rows: list[dict[str, str]] = []
    for fixture in fixtures:
        if fixture["key"] not in specs:
            continue
        reservation_id, guest_id, check_in, status, room_type, nights, room_count = specs[
            fixture["key"]
        ]
        property_row = properties[fixture["property_id"]]
        profile = PROFILE_BY_ID[property_row["property_id"]]
        rate_total = (
            _daily_rate(profile, check_in, room_type, profile.baseline_demand) * nights * room_count
        )
        row = _reservation(
            reservation_id,
            guest_id,
            property_row,
            room_type,
            check_in,
            check_in + timedelta(days=nights),
            status,
            "direct",
            rate_total,
            room_count,
        )
        row["cancellation_policy"] = (
            "nonrefundable" if fixture["key"] == "nonrefundable" else "flexible"
        )
        rows.append(row)
    return rows


def _reservation(
    reservation_id: str,
    guest_id: str,
    property_row: dict[str, str],
    room_type_number: int,
    check_in: date,
    check_out: date,
    status: str,
    channel: str,
    rate_total: float,
    room_count: int = 1,
) -> dict[str, str]:
    return {
        "reservation_id": reservation_id,
        "guest_id": guest_id,
        "property_id": property_row["property_id"],
        "room_type_id": f"{property_row['property_id']}-RT-{room_type_number:02d}",
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "status": status,
        "cancellation_policy": "nonrefundable" if reservation_id[-1] in {"7", "D"} else "flexible",
        "room_count": str(room_count),
        "rate_total": f"{rate_total:.2f}",
        "currency": property_row["currency"],
        "channel": channel,
    }


def _stay_lengths(
    total_nights: int,
    target_count: int,
    profile: OperatingProfile,
    rng: random.Random,
) -> list[int]:
    center = profile.average_length_of_stay
    candidates = tuple(range(1, 9))
    weights = tuple(
        math.exp(-((length - center) ** 2) / (2 * (0.85 + center * 0.18) ** 2))
        for length in candidates
    )
    lengths = rng.choices(candidates, weights=weights, k=target_count)
    difference = total_nights - sum(lengths)
    indexes = list(range(target_count))
    while difference:
        rng.shuffle(indexes)
        changed = False
        for index in indexes:
            if difference > 0 and lengths[index] < 14:
                lengths[index] += 1
                difference -= 1
                changed = True
            elif difference < 0 and lengths[index] > 1:
                lengths[index] -= 1
                difference += 1
                changed = True
            if difference == 0:
                break
        if not changed:
            raise ValueError("Unable to reconcile completed stays to occupied room nights")
    return lengths


def _build_restaurant_reservations(
    scale: str,
    properties: list[dict[str, str]],
    guests: list[dict[str, str]],
    outlets: list[dict[str, str]],
    metrics: list[dict[str, str]],
    start: date,
    end: date,
    rng: random.Random,
) -> list[dict[str, str]]:
    count = 250 if scale == "demo" else 35_000
    occupied_by_property: Counter[str] = Counter()
    metrics_by_property: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in metrics:
        occupied_by_property[row["property_id"]] += int(row["occupied_rooms"])
        metrics_by_property[row["property_id"]].append(row)
    property_ids = [row["property_id"] for row in properties]
    property_weights = [occupied_by_property[property_id] for property_id in property_ids]
    outlet_by_property = {
        row["property_id"]: row["outlet_id"]
        for row in outlets
        if row["outlet_type"] == "restaurant"
    }
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
        property_id = rng.choices(property_ids, weights=property_weights, k=1)[0]
        property_metrics = metrics_by_property[property_id]
        service_row = rng.choices(
            property_metrics,
            weights=[max(1, int(row["occupied_rooms"])) for row in property_metrics],
            k=1,
        )[0]
        service_date = date.fromisoformat(service_row["service_date"])
        hour = rng.choices((18, 19, 20, 21), weights=(18, 36, 31, 15), k=1)[0]
        rows.append(
            {
                "restaurant_reservation_id": f"RR-{number:07d}",
                "guest_id": f"GST-{rng.randrange(1, len(guests) + 1):06d}",
                "property_id": property_id,
                "outlet_id": outlet_by_property[property_id],
                "reservation_at": f"{service_date.isoformat()}T{hour:02d}:{rng.choice((0, 15, 30, 45)):02d}:00",
                "party_size": str(
                    rng.choices(
                        (1, 2, 3, 4, 5, 6, 8),
                        weights=(4, 38, 14, 27, 7, 8, 2),
                        k=1,
                    )[0]
                ),
                "status": rng.choices(
                    ("confirmed", "seated", "cancelled"), weights=(18, 75, 7), k=1
                )[0],
            }
        )
    return rows


def _build_folios(
    stays: list[dict[str, str]],
    reservations: list[dict[str, str]],
    rng: random.Random,
) -> list[dict[str, str]]:
    reservation_by_id = {row["reservation_id"]: row for row in reservations}
    rows: list[dict[str, str]] = []
    for number, stay in enumerate(stays, start=1):
        reservation = reservation_by_id[stay["reservation_id"]]
        room_charge = round(float(reservation["rate_total"]), 2)
        extras = round(room_charge * rng.uniform(0.035, 0.19), 2)
        total_charges = round(room_charge + extras, 2)
        adjustment = (
            -round(total_charges * rng.uniform(0.015, 0.075), 2) if rng.random() < 0.055 else 0.0
        )
        refund = round(total_charges * rng.uniform(0.02, 0.08), 2) if rng.random() < 0.008 else 0.0
        payment = round(total_charges + adjustment - refund, 2)
        rows.append(
            {
                "folio_id": f"FOL-{number:07d}",
                "stay_id": stay["stay_id"],
                "reservation_id": stay["reservation_id"],
                "guest_id": stay["guest_id"],
                "property_id": stay["property_id"],
                "currency": reservation["currency"],
                "total_charges": f"{total_charges:.2f}",
                "total_adjustments": f"{adjustment:.2f}",
                "total_payments": f"{payment:.2f}",
                "total_refunds": f"{refund:.2f}",
                "balance": "0.00",
            }
        )
    return rows


def _transaction_rows(folios: list[dict[str, str]]) -> Iterator[dict[str, str]]:
    extra_types = ("minibar", "parking", "room_service", "spa", "laundry")
    for number, folio in enumerate(folios, start=1):
        charges = _cents(folio["total_charges"])
        adjustment = _cents(folio["total_adjustments"])
        room = round(charges * (0.78 + (number % 7) * 0.009))
        tax = round(charges * (0.09 + (number % 5) * 0.006))
        extra = charges - room - tax
        posted_date = date(2026, 3, 1) + timedelta(days=(number * 17) % 395)
        components = [
            ("room_charge", room),
            ("tax", tax),
            (extra_types[number % len(extra_types)], extra),
        ]
        if adjustment:
            components.append(("adjustment", adjustment))
        for item_number, (transaction_type, amount) in enumerate(components, start=1):
            yield {
                "folio_transaction_id": f"FTX-{number:07d}-{item_number:02d}",
                "folio_id": folio["folio_id"],
                "transaction_type": transaction_type,
                "description": transaction_type.replace("_", " ").title(),
                "amount": f"{amount / 100:.2f}",
                "currency": folio["currency"],
                "posted_at": f"{posted_date.isoformat()}T{12 + item_number:02d}:00:00",
            }


def _payment_rows(folios: list[dict[str, str]]) -> Iterator[dict[str, str]]:
    methods = ("card", "card", "card", "mobile_wallet", "bank_transfer")
    for number, folio in enumerate(folios, start=1):
        yield {
            "payment_id": f"PAY-{number:07d}",
            "folio_id": folio["folio_id"],
            "payment_method": methods[number % len(methods)],
            "payment_token": f"tok_syn_{number:012d}",
            "card_mask": f"**** **** **** {1000 + (number * 37) % 9000:04d}",
            "amount": folio["total_payments"],
            "currency": folio["currency"],
            "payment_status": "captured",
        }


def _build_disputes(
    folios: list[dict[str, str]],
    reservations: list[dict[str, str]],
    start: date,
    end: date,
    rng: random.Random,
) -> list[dict[str, str]]:
    reservation_by_id = {row["reservation_id"]: row for row in reservations}
    candidates: list[dict[str, str]] = []
    for folio in folios:
        reservation = reservation_by_id[folio["reservation_id"]]
        profile = PROFILE_BY_ID[folio["property_id"]]
        channel_risk = {"direct": 0.0, "corporate": -0.001, "ota": 0.0035, "wholesale": 0.002}[
            reservation["channel"]
        ]
        incidence = 0.003 + (1.0 - profile.operational_quality) * 0.032 + channel_risk
        if rng.random() < incidence:
            candidates.append(folio)
    if not candidates:
        raise ValueError("Dispute model unexpectedly produced no disputes")
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
    for number, folio in enumerate(candidates, start=2):
        if folio["folio_id"] == "FOL-0000001":
            continue
        reservation = reservation_by_id[folio["reservation_id"]]
        check_out = date.fromisoformat(reservation["check_out"])
        opened = min(end, check_out + timedelta(days=rng.randrange(0, 5)))
        age = (end - opened).days
        if age <= 10:
            status = rng.choices(("open", "under_review", "resolved"), weights=(32, 44, 24), k=1)[0]
        elif age <= 30:
            status = rng.choices(("open", "under_review", "resolved"), weights=(5, 15, 80), k=1)[0]
        else:
            status = rng.choices(("open", "under_review", "resolved"), weights=(1, 2, 97), k=1)[0]
        dispute_type = rng.choices(DISPUTE_TYPES, weights=(20, 15, 12, 18, 14, 13, 8), k=1)[0]
        amount_factor = {
            "room_rate": (0.08, 0.25),
            "minibar": (0.01, 0.035),
            "parking": (0.015, 0.05),
            "duplicate_charge": (0.15, 0.45),
            "tax_or_fee": (0.025, 0.09),
            "service_charge": (0.02, 0.08),
            "cancellation_fee": (0.08, 0.22),
        }[dispute_type]
        amount = max(
            5.0,
            round(float(folio["total_charges"]) * rng.uniform(*amount_factor), 2),
        )
        rows.append(
            {
                "billing_dispute_id": f"BD-{number:07d}",
                "folio_id": folio["folio_id"],
                "dispute_type": dispute_type,
                "status": status,
                "amount": f"{amount:.2f}",
                "opened_at": f"{opened.isoformat()}T{rng.randrange(8, 19):02d}:{rng.randrange(0, 60):02d}:00",
            }
        )
    return rows


def _build_service_records(
    reservations: list[dict[str, str]],
    stays: list[dict[str, str]],
    start: date,
    end: date,
    rng: random.Random,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    reservation_by_id = {row["reservation_id"]: row for row in reservations}
    special_requests = [
        {
            "special_request_id": "SR-DEMO-PREARRIVAL",
            "reservation_id": "RES-DEMO-FAMILY",
            "guest_id": "GST-000001",
            "request_type": "accessibility",
            "status": "confirmed",
            "requested_at": "2026-08-01T10:00:00",
            "details": "Step-free access, feather-free bedding, crib, arrival after 22:00.",
        }
    ]
    request_number = 2
    eligible_reservations = [
        row for row in reservations if row["status"] not in {"cancelled", "no_show"}
    ]
    for reservation in eligible_reservations:
        profile = PROFILE_BY_ID[reservation["property_id"]]
        request_probability = profile.service_request_rate * (
            1.18 if profile.service_tier in {"luxury", "resort"} else 1.0
        )
        request_count = 0
        if rng.random() < request_probability:
            request_count = 1
        if request_count and rng.random() < 0.09:
            request_count += 1
        for _ in range(request_count):
            check_in = date.fromisoformat(reservation["check_in"])
            check_out = date.fromisoformat(reservation["check_out"])
            prearrival = rng.random() < 0.32
            if prearrival:
                requested_date = max(start, check_in - timedelta(days=rng.randrange(1, 18)))
            else:
                span = max(1, (check_out - check_in).days)
                requested_date = min(end, check_in + timedelta(days=rng.randrange(span)))
            age = (end - requested_date).days
            if age <= 4:
                status = rng.choices(
                    ("requested", "confirmed", "fulfilled"), weights=(16, 31, 53), k=1
                )[0]
            elif age <= 14:
                status = rng.choices(
                    ("requested", "confirmed", "fulfilled"), weights=(4, 13, 83), k=1
                )[0]
            else:
                status = rng.choices(
                    ("requested", "confirmed", "fulfilled"), weights=(0.4, 2.6, 97), k=1
                )[0]
            request_type = rng.choices(
                REQUEST_TYPES,
                weights=(17, 14, 13, 8, 11, 7, 8, 6, 16),
                k=1,
            )[0]
            special_requests.append(
                {
                    "special_request_id": f"SR-{request_number:07d}",
                    "reservation_id": reservation["reservation_id"],
                    "guest_id": reservation["guest_id"],
                    "request_type": request_type,
                    "status": status,
                    "requested_at": f"{requested_date.isoformat()}T{rng.randrange(7, 23):02d}:{rng.randrange(0, 60):02d}:00",
                    "details": f"Guest requested {request_type.replace('_', ' ')} assistance.",
                }
            )
            request_number += 1

    maintenance_requests = [
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
    work_orders = [
        {
            "work_order_id": "WO-DEMO-HVAC",
            "maintenance_request_id": "MR-DEMO-HVAC",
            "property_id": "HTL-004",
            "status": "assigned",
            "priority": "high",
            "opened_at": "2026-07-10T21:18:00",
        }
    ]
    maintenance_number = 2
    for stay in stays:
        if stay["stay_id"] == "STY-0000002":
            continue
        profile = PROFILE_BY_ID[stay["property_id"]]
        if rng.random() >= profile.maintenance_request_rate:
            continue
        reservation = reservation_by_id[stay["reservation_id"]]
        check_in = date.fromisoformat(reservation["check_in"])
        check_out = date.fromisoformat(reservation["check_out"])
        span = max(1, (check_out - check_in).days)
        reported_date = min(end, check_in + timedelta(days=rng.randrange(span)))
        reported_hour = rng.randrange(0, 24)
        reported = datetime.combine(reported_date, time(reported_hour, rng.randrange(0, 60)))
        request_type = rng.choices(MAINTENANCE_TYPES, weights=(24, 22, 13, 15, 14, 12), k=1)[0]
        priority = rng.choices(
            ("low", "normal", "high", "emergency"), weights=(14, 58, 24, 4), k=1
        )[0]
        base_hours = {"low": 3.1, "normal": 1.35, "high": 0.48, "emergency": 0.16}[priority]
        staffing_factor = 1.0 + (1.0 - profile.operational_quality) * 2.2
        night_factor = 1.55 if reported_hour < 7 or reported_hour >= 22 else 1.0
        response_hours = base_hours * staffing_factor * night_factor * rng.lognormvariate(0.0, 0.42)
        if rng.random() < 0.012:
            response_hours *= rng.uniform(3.5, 8.0)
        response_minutes = max(6, min(round(response_hours * 60), 36 * 60))
        opened = reported + timedelta(minutes=response_minutes)
        age = (datetime.combine(end, time(23, 59)) - reported).days
        if age <= 3:
            request_status = rng.choices(
                ("open", "in_progress", "resolved"), weights=(18, 35, 47), k=1
            )[0]
        elif age <= 14:
            request_status = rng.choices(
                ("open", "in_progress", "resolved"), weights=(3, 10, 87), k=1
            )[0]
        else:
            request_status = rng.choices(
                ("open", "in_progress", "resolved"), weights=(0.3, 1.2, 98.5), k=1
            )[0]
        work_status = {"open": "assigned", "in_progress": "in_progress", "resolved": "completed"}[
            request_status
        ]
        request_id = f"MR-{maintenance_number:07d}"
        maintenance_requests.append(
            {
                "maintenance_request_id": request_id,
                "property_id": stay["property_id"],
                "stay_id": stay["stay_id"],
                "room_id": stay["room_id"],
                "request_type": request_type,
                "status": request_status,
                "reported_at": reported.isoformat(timespec="seconds"),
            }
        )
        work_orders.append(
            {
                "work_order_id": f"WO-{maintenance_number:07d}",
                "maintenance_request_id": request_id,
                "property_id": stay["property_id"],
                "status": work_status,
                "priority": priority,
                "opened_at": opened.isoformat(timespec="seconds"),
            }
        )
        maintenance_number += 1
    return special_requests, maintenance_requests, work_orders


def _allocate_counts(
    total: int,
    weights: Sequence[float],
    *,
    minimum: int = 0,
) -> list[int]:
    if total < minimum * len(weights):
        raise ValueError("Total is too small for the requested minimum allocation")
    remaining = total - minimum * len(weights)
    normalized = [weight / sum(weights) for weight in weights]
    raw = [remaining * weight for weight in normalized]
    result = [minimum + math.floor(value) for value in raw]
    for index in sorted(
        range(len(weights)), key=lambda item: raw[item] - math.floor(raw[item]), reverse=True
    )[: total - sum(result)]:
        result[index] += 1
    return result


def _allocate_occupied(
    occupied_total: int,
    sellable_by_type: Sequence[int],
    preference: Sequence[float],
) -> list[int]:
    weighted_capacity = [
        sellable * weight for sellable, weight in zip(sellable_by_type, preference, strict=True)
    ]
    result = _allocate_counts(occupied_total, weighted_capacity)
    overflow = 0
    for index, capacity in enumerate(sellable_by_type):
        if result[index] > capacity:
            overflow += result[index] - capacity
            result[index] = capacity
    while overflow:
        for index, capacity in enumerate(sellable_by_type):
            if result[index] < capacity:
                result[index] += 1
                overflow -= 1
                if not overflow:
                    break
    return result


def _room_type_weights(
    rooms_by_property_type: dict[tuple[str, str], list[str]],
    property_id: str,
) -> list[int]:
    return [
        len(rooms_by_property_type[(property_id, f"{property_id}-RT-{number:02d}")])
        for number in range(1, 5)
    ]


def _channel(profile: OperatingProfile, rng: random.Random) -> str:
    weights = (
        34 + round((1.0 - profile.business_mix) * 18),
        10 + round(profile.business_mix * 42),
        34 - round(profile.business_mix * 12),
        12,
    )
    return rng.choices(CHANNELS, weights=weights, k=1)[0]


def _cents(value: str) -> int:
    return round(float(value) * 100)
