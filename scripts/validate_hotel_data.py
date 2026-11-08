"""Validate deterministic fictional hotel source data and Foundry IQ documents."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from generate_hotel_data import (
    DATE_END,
    DATE_SHIFT,
    DATE_START,
    FIXTURES_PATH,
    REQUIRED_TABLES,
    TEMPORAL_BOUNDARY,
    stable_hash,
)
from realistic_hotel_data import MARIA_GARCIA_EMAIL

RESERVATION_STATUSES = {
    "future",
    "arriving",
    "departed",
    "cancelled",
    "no_show",
    "completed",
    "in_house",
}
STAY_STATUSES = {"completed", "future", "in_house"}
PAYMENT_MASK = re.compile(r"^\*{4} \*{4} \*{4} \d{4}$")
REAL_BRANDS = (
    "marriott",
    "hilton",
    "hyatt",
    "sheraton",
    "westin",
    "ritz",
    "four seasons",
    "intercontinental",
    "holiday inn",
    "accor",
    "kimpton",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def ids(rows: list[dict[str, str]], column: str) -> set[str]:
    values = [row[column] for row in rows]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {column}")
    return set(values)


def parse_frontmatter(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"{path} has no frontmatter")
    _, metadata_text, _ = content.split("---\n", 2)
    metadata: dict[str, str] = {}
    for line in metadata_text.splitlines():
        key, separator, value = line.partition(": ")
        if not separator:
            raise ValueError(f"{path} has invalid metadata line")
        metadata[key] = value
    return metadata


def validate_chronology(tables: dict[str, list[dict[str, str]]]) -> list[str]:
    problems: list[str] = []
    reservations = {row["reservation_id"]: row for row in tables["reservations"]}
    stays = {row["stay_id"]: row for row in tables["stays"]}
    folios = {row["folio_id"]: row for row in tables["folios"]}
    maintenance = {row["maintenance_request_id"]: row for row in tables["maintenance_requests"]}

    def record_date(value: str) -> date:
        return date.fromisoformat(value[:10])

    def relative_date(value: date, lifecycle: str, label: str) -> None:
        if value == TEMPORAL_BOUNDARY:
            problems.append(f"{label} falls on the temporal boundary")
        if lifecycle in {"completed", "departed", "no_show", "cancelled"}:
            if value >= TEMPORAL_BOUNDARY:
                problems.append(f"past {label} is not strictly before the temporal boundary")
        elif lifecycle in {"future", "arriving"} and value <= TEMPORAL_BOUNDARY:
            problems.append(f"future {label} is not strictly after the temporal boundary")

    for row in tables["reservations"]:
        check_in, check_out = record_date(row["check_in"]), record_date(row["check_out"])
        relative_date(check_in, row["status"], "reservation")
        relative_date(check_out, row["status"], "reservation")
        if row["status"] == "in_house" and not check_in < TEMPORAL_BOUNDARY < check_out:
            problems.append("in-house reservation does not span the temporal boundary")
    for row in tables["stays"]:
        reservation = reservations[row["reservation_id"]]
        check_in = record_date(row["actual_check_in"])
        check_out = record_date(row["actual_check_out"])
        if (check_in, check_out) != (
            record_date(reservation["check_in"]),
            record_date(reservation["check_out"]),
        ):
            problems.append("stay dates do not match reservation dates")
        if row["status"] != reservation["status"]:
            problems.append("stay status does not match reservation status")
        relative_date(check_in, row["status"], "stay")
        relative_date(check_out, row["status"], "stay")
    for row in tables["restaurant_reservations"]:
        service_date = record_date(row["reservation_at"])
        lifecycle = {"confirmed": "future", "seated": "completed"}.get(row["status"], "")
        relative_date(service_date, lifecycle, "dining reservation")
        if not DATE_START <= service_date <= DATE_END:
            problems.append("restaurant reservation date range failure")
    for row in tables["folio_transactions"]:
        reservation = reservations[folios[row["folio_id"]]["reservation_id"]]
        posted = record_date(row["posted_at"])
        relative_date(posted, reservation["status"], "folio transaction")
        if (
            not record_date(reservation["check_in"])
            <= posted
            < record_date(reservation["check_out"])
        ):
            problems.append("folio transaction is outside its reservation stay")
    for row in tables["billing_disputes"]:
        reservation = reservations[folios[row["folio_id"]]["reservation_id"]]
        opened = record_date(row["opened_at"])
        relative_date(opened, reservation["status"], "billing dispute")
        if opened < record_date(reservation["check_out"]):
            problems.append("billing dispute predates checkout")
    for row in tables["special_requests"]:
        reservation = reservations[row["reservation_id"]]
        requested = record_date(row["requested_at"])
        relative_date(requested, reservation["status"], "special request")
        if not DATE_START <= requested < record_date(reservation["check_out"]):
            problems.append("special request is outside its reservation lifecycle")
        if row["guest_id"] != reservation["guest_id"]:
            problems.append("special request guest does not match reservation")
    for row in tables["maintenance_requests"]:
        stay = stays[row["stay_id"]]
        reported = record_date(row["reported_at"])
        relative_date(reported, stay["status"], "maintenance request")
        if (
            not record_date(stay["actual_check_in"])
            <= reported
            < record_date(stay["actual_check_out"])
        ):
            problems.append("maintenance request is outside its stay")
    for row in tables["work_orders"]:
        stay = stays[maintenance[row["maintenance_request_id"]]["stay_id"]]
        relative_date(record_date(row["opened_at"]), stay["status"], "work order")
    dining_ids = {row["restaurant_reservation_id"] for row in tables["restaurant_reservations"]}
    for table, key, timestamp in (
        ("action_confirmations", "target_id", "confirmed_at"),
        ("idempotency_records", "result_id", "created_at"),
        ("audit_events", "entity_id", "occurred_at"),
    ):
        for row in tables[table]:
            if row[key] not in dining_ids:
                problems.append(f"{table} dining FK failure")
            relative_date(record_date(row[timestamp]), "completed", table)
    fixture_data = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    if fixture_data["as_of_date"] != TEMPORAL_BOUNDARY.isoformat():
        problems.append("fixture as-of date does not match the temporal boundary")
    fixture_tables = {
        "family_accessibility": ("reservations", "reservation_id"),
        "rate_change": ("reservations", "reservation_id"),
        "cancellable": ("reservations", "reservation_id"),
        "nonrefundable": ("reservations", "reservation_id"),
        "folio_dispute": ("reservations", "reservation_id"),
        "maintenance": ("reservations", "reservation_id"),
        "restaurant": ("restaurant_reservations", "restaurant_reservation_id"),
        "prearrival_request": ("special_requests", "special_request_id"),
    }
    for fixture in fixture_data["scenarios"]:
        if fixture["key"] not in fixture_tables:
            continue
        table, id_column = fixture_tables[fixture["key"]]
        record_id = fixture.get("reservation_id", fixture.get("request_id"))
        record = next((row for row in tables[table] if row[id_column] == record_id), None)
        if record is None:
            problems.append(f"canonical fixture missing: {record_id}")
            continue
        for key in (
            "guest_id",
            "property_id",
            "check_in",
            "check_out",
            "room_count",
            "status",
            "requested_at",
            "reservation_at",
        ):
            actual = record.get(key)
            if key == "property_id" and actual is None and "reservation_id" in record:
                actual = reservations[record["reservation_id"]]["property_id"]
            if key in fixture and actual != str(fixture[key]):
                problems.append(f"canonical fixture mismatch: {record_id} {key}")
    maria = next((row for row in tables["guests"] if row["guest_id"] == "GST-000001"), None)
    if maria is None or (maria["first_name"], maria["last_name"], maria["email"]) != (
        "Maria",
        "Garcia",
        MARIA_GARCIA_EMAIL,
    ):
        problems.append("Maria Garcia acceptance-test identity is incoherent")
    family = reservations.get("RES-FAMILY-2026")
    if family is None or (
        family["guest_id"],
        family["property_id"],
        family["room_type_id"],
        family["room_count"],
        family["check_in"],
        family["check_out"],
        family["status"],
    ) != (
        "GST-000001",
        "HTL-004",
        "HTL-004-RT-03",
        "2",
        (date(2026, 9, 10) + DATE_SHIFT).isoformat(),
        (date(2026, 9, 12) + DATE_SHIFT).isoformat(),
        "future",
    ):
        problems.append("Maria Garcia acceptance-test reservation is incoherent")
    return problems


def validate_output(output: Path, docs_output: Path) -> list[str]:
    problems: list[str] = []
    manifest_path = output / "manifest.json"
    if not manifest_path.exists():
        return [f"missing manifest: {manifest_path}"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("temporal_boundary") != TEMPORAL_BOUNDARY.isoformat():
        problems.append("manifest temporal boundary mismatch")
    if manifest.get("date_range") != {"start": DATE_START.isoformat(), "end": DATE_END.isoformat()}:
        problems.append("manifest date range mismatch")
    tables: dict[str, list[dict[str, str]]] = {}
    for table in REQUIRED_TABLES:
        path = output / f"{table}.csv"
        if not path.exists():
            problems.append(f"missing table: {table}")
            continue
        tables[table] = read_csv(path)
        if len(tables[table]) != manifest["counts"].get(table):
            problems.append(f"count mismatch: {table}")
        if stable_hash(path) != manifest["hashes"].get(table):
            problems.append(f"hash mismatch: {table}")
    if problems:
        return problems
    try:
        problems.extend(validate_chronology(tables))
        property_ids = ids(tables["properties"], "property_id")
        expected_properties = {f"HTL-{number:03d}" for number in range(1, 21)}
        if property_ids != expected_properties:
            problems.append("property IDs must be HTL-001 through HTL-020")
        room_type_ids = ids(tables["room_types"], "room_type_id")
        room_ids = ids(tables["rooms"], "room_id")
        guest_ids = ids(tables["guests"], "guest_id")
        reservation_ids = ids(tables["reservations"], "reservation_id")
        stay_ids = ids(tables["stays"], "stay_id")
        folio_ids = ids(tables["folios"], "folio_id")
        room_type_properties = {
            row["room_type_id"]: row["property_id"] for row in tables["room_types"]
        }
        room_properties = {row["room_id"]: row["property_id"] for row in tables["rooms"]}
        reservation_properties = {
            row["reservation_id"]: row["property_id"] for row in tables["reservations"]
        }
        reservation_statuses_by_property: defaultdict[str, set[str]] = defaultdict(set)
        for row in tables["room_types"]:
            if row["property_id"] not in property_ids:
                problems.append("room type property FK failure")
        for row in tables["rooms"]:
            if row["property_id"] not in property_ids or row["room_type_id"] not in room_type_ids:
                problems.append("room FK failure")
            elif room_type_properties[row["room_type_id"]] != row["property_id"]:
                problems.append("room and room type property mismatch")
        for row in tables["reservations"]:
            reservation_statuses_by_property[row["property_id"]].add(row["status"])
            if row["guest_id"] not in guest_ids or row["property_id"] not in property_ids:
                problems.append("reservation FK failure")
            if (
                row["room_type_id"] not in room_type_ids
                or row["status"] not in RESERVATION_STATUSES
            ):
                problems.append("reservation room type or status failure")
            elif room_type_properties[row["room_type_id"]] != row["property_id"]:
                problems.append("reservation and room type property mismatch")
            check_in = date.fromisoformat(row["check_in"])
            check_out = date.fromisoformat(row["check_out"])
            if check_in < DATE_START or check_out > DATE_END or check_out <= check_in:
                problems.append("reservation date range failure")
        for property_id in sorted(property_ids):
            missing_statuses = RESERVATION_STATUSES - reservation_statuses_by_property[property_id]
            if missing_statuses:
                problems.append(
                    f"property {property_id} missing reservation statuses: "
                    f"{sorted(missing_statuses)}"
                )
        for row in tables["stays"]:
            if (
                row["reservation_id"] not in reservation_ids
                or row["room_id"] not in room_ids
                or row["status"] not in STAY_STATUSES
            ):
                problems.append("stay FK or status failure")
            elif reservation_properties[row["reservation_id"]] != room_properties[row["room_id"]]:
                problems.append("stay reservation and room property mismatch")
        completed_stay_counts: defaultdict[str, int] = defaultdict(int)
        stay_nights: defaultdict[str, int] = defaultdict(int)
        for row in tables["stays"]:
            if row["status"] == "completed":
                completed_stay_counts[row["property_id"]] += 1
            stay_nights[row["property_id"]] += (
                date.fromisoformat(row["actual_check_out"][:10])
                - date.fromisoformat(row["actual_check_in"][:10])
            ).days
        stay_properties = {
            row["stay_id"]: reservation_properties[row["reservation_id"]]
            for row in tables["stays"]
            if row["reservation_id"] in reservation_properties
        }
        for row in tables["restaurant_reservations"]:
            if row["guest_id"] not in guest_ids or row["property_id"] not in property_ids:
                problems.append("restaurant reservation FK failure")
        for row in tables["folios"]:
            if row["stay_id"] not in stay_ids or row["reservation_id"] not in reservation_ids:
                problems.append("folio FK failure")
        transaction_totals: defaultdict[str, int] = defaultdict(int)
        for row in tables["folio_transactions"]:
            if row["folio_id"] not in folio_ids:
                problems.append("folio transaction FK failure")
            transaction_totals[row["folio_id"]] += round(float(row["amount"]) * 100)
        payment_totals: defaultdict[str, int] = defaultdict(int)
        for row in tables["payments"]:
            if row["folio_id"] not in folio_ids or not PAYMENT_MASK.fullmatch(row["card_mask"]):
                problems.append("payment FK or mask failure")
            if any(term in row for term in ("card_number", "cvv", "pan")):
                problems.append("unmasked payment field found")
            payment_totals[row["folio_id"]] += round(float(row["amount"]) * 100)
        for row in tables["billing_disputes"]:
            if row["folio_id"] not in folio_ids:
                problems.append("billing dispute FK failure")
        for row in tables["folios"]:
            charges = round(float(row["total_charges"]) * 100)
            adjustments = round(float(row["total_adjustments"]) * 100)
            payments = round(float(row["total_payments"]) * 100)
            refunds = round(float(row["total_refunds"]) * 100)
            balance = round(float(row["balance"]) * 100)
            if charges + adjustments - payments - refunds != balance:
                problems.append("folio header does not reconcile")
            if transaction_totals[row["folio_id"]] != charges + adjustments:
                problems.append("folio transactions do not reconcile")
            if payment_totals[row["folio_id"]] != payments:
                problems.append("folio payments do not reconcile")
        for row in tables["daily_inventory"]:
            physical = int(row["physical_rooms"])
            out_of_order = int(row["out_of_order_rooms"])
            sellable = int(row["sellable_rooms"])
            occupied = int(row["occupied_rooms"])
            if (
                physical < 0
                or out_of_order < 0
                or sellable != physical - out_of_order
                or occupied < 0
                or occupied > sellable
            ):
                problems.append("invalid daily inventory")
        metric_dates = {row["service_date"] for row in tables["property_daily_metrics"]}
        expected_dates = {
            (DATE_START.fromordinal(DATE_START.toordinal() + offset)).isoformat()
            for offset in range((DATE_END - DATE_START).days + 1)
        }
        if {row["service_date"] for row in tables["daily_inventory"]} != expected_dates:
            problems.append("daily inventory date coverage failure")
        if metric_dates != expected_dates:
            problems.append("daily metrics date coverage failure")
        occupied_nights: defaultdict[str, int] = defaultdict(int)
        sellable_nights: defaultdict[str, int] = defaultdict(int)
        portfolio_by_date: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
        for row in tables["property_daily_metrics"]:
            property_id = row["property_id"]
            occupied = int(row["occupied_rooms"])
            sellable = int(row["sellable_rooms"])
            occupied_nights[property_id] += occupied
            sellable_nights[property_id] += sellable
            portfolio_by_date[row["service_date"]][0] += occupied
            portfolio_by_date[row["service_date"]][1] += sellable
        if occupied_nights != stay_nights:
            problems.append("stay room nights do not reconcile to occupied room nights")
        occupancy_rates = {
            property_id: occupied_nights[property_id] / sellable_nights[property_id]
            for property_id in property_ids
        }
        if any(rate < 0.38 or rate > 0.96 for rate in occupancy_rates.values()):
            problems.append("property occupancy outside plausible bounds")
        if max(occupancy_rates.values()) - min(occupancy_rates.values()) < 0.05:
            problems.append("property occupancy lacks meaningful variation")
        if len(set(completed_stay_counts.values())) < 10:
            problems.append("completed stay counts are suspiciously uniform")
        portfolio_rates = [
            occupied / sellable
            for occupied, sellable in (
                portfolio_by_date[service_date] for service_date in sorted(portfolio_by_date)
            )
        ]
        if (
            max(
                abs(portfolio_rates[index] - portfolio_rates[index - 1])
                for index in range(1, len(portfolio_rates))
            )
            > 0.12
        ):
            problems.append("portfolio occupancy contains an implausible daily jump")
        weekly_repeats = sum(
            abs(portfolio_rates[index] - portfolio_rates[index - 7]) < 0.000001
            for index in range(7, len(portfolio_rates))
        )
        if weekly_repeats > len(portfolio_rates) // 4:
            problems.append("portfolio occupancy contains a repeated weekly pattern")
        for row in tables["special_requests"]:
            if row["reservation_id"] not in reservation_ids or row["guest_id"] not in guest_ids:
                problems.append("special request FK failure")
        open_requests = sum(row["status"] == "requested" for row in tables["special_requests"])
        if open_requests / len(tables["special_requests"]) >= 0.10:
            problems.append("service request backlog is implausibly large")
        if len({row["request_type"] for row in tables["special_requests"]}) < 6:
            problems.append("service request categories lack variety")
        maintenance_ids = ids(tables["maintenance_requests"], "maintenance_request_id")
        maintenance_properties: dict[str, str] = {}
        for row in tables["maintenance_requests"]:
            if row["stay_id"] not in stay_ids or row["room_id"] not in room_ids:
                problems.append("maintenance request FK failure")
            elif (
                row["property_id"] != stay_properties[row["stay_id"]]
                or row["property_id"] != room_properties[row["room_id"]]
            ):
                problems.append("maintenance request property mismatch")
            maintenance_properties[row["maintenance_request_id"]] = row["property_id"]
        work_order_response_minutes: defaultdict[str, list[float]] = defaultdict(list)
        maintenance_by_id = {
            row["maintenance_request_id"]: row for row in tables["maintenance_requests"]
        }
        for row in tables["work_orders"]:
            if row["maintenance_request_id"] not in maintenance_ids:
                problems.append("work order FK failure")
            elif row["property_id"] != maintenance_properties[row["maintenance_request_id"]]:
                problems.append("work order property mismatch")
            else:
                request = maintenance_by_id[row["maintenance_request_id"]]
                response_minutes = (
                    datetime.fromisoformat(row["opened_at"])
                    - datetime.fromisoformat(request["reported_at"])
                ).total_seconds() / 60
                if response_minutes <= 0:
                    problems.append("maintenance response time must be positive")
                work_order_response_minutes[row["property_id"]].append(response_minutes)
        property_response_averages = {
            property_id: sum(values) / len(values)
            for property_id, values in work_order_response_minutes.items()
        }
        if len({round(value, 1) for value in property_response_averages.values()}) < 10:
            problems.append("maintenance response times are suspiciously uniform")
        dispute_types = {row["dispute_type"] for row in tables["billing_disputes"]}
        if len(dispute_types) < 5:
            problems.append("billing dispute categories lack variety")
        if len(tables["billing_disputes"]) / sum(completed_stay_counts.values()) >= 0.03:
            problems.append("billing dispute incidence is implausibly high")
    except (KeyError, ValueError) as error:
        problems.append(str(error))
    document_paths = sorted(docs_output.glob("*/*.generated.md"))
    if len(document_paths) != manifest["documents"]["count"]:
        problems.append("document count mismatch")
    required_metadata = {
        "document_id",
        "title",
        "property_id",
        "category",
        "valid_from",
        "valid_to",
        "locale",
        "source_path",
    }
    for document in document_paths:
        try:
            metadata = parse_frontmatter(document)
            if not required_metadata <= set(metadata):
                problems.append(f"metadata missing from {document.name}")
                continue
            if date.fromisoformat(metadata["valid_from"]) > date.fromisoformat(
                metadata["valid_to"]
            ):
                problems.append(f"invalid notice window: {document.name}")
            if metadata["category"] == "dated_notice" and not (
                date.fromisoformat(metadata["valid_to"]) < TEMPORAL_BOUNDARY
                or date.fromisoformat(metadata["valid_from"]) > TEMPORAL_BOUNDARY
            ):
                problems.append(f"dated notice crosses the temporal boundary: {document.name}")
            content = document.read_text(encoding="utf-8").lower()
            if any(brand in content for brand in REAL_BRANDS):
                problems.append(f"real brand in {document.name}")
            if metadata["category"] == "dated_notice" and "dated notice" not in content:
                problems.append(f"dated notice not labelled: {document.name}")
            if metadata["category"] != "dated_notice" and "permanent" not in content:
                problems.append(f"permanent facts not labelled: {document.name}")
        except ValueError as error:
            problems.append(str(error))
    document_hashes = {
        str(path.relative_to(docs_output)): stable_hash(path) for path in document_paths
    }
    if document_hashes != manifest["documents"]["hashes"]:
        problems.append("document hash mismatch")
    return sorted(set(problems))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/generated"))
    parser.add_argument("--docs-output", type=Path, default=Path("foundryiq-docs"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    problems = validate_output(args.output, args.docs_output)
    if problems:
        print("\n".join(f"ERROR: {problem}" for problem in problems))
        return 1
    print("Hotel data and Foundry IQ documents validate successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
