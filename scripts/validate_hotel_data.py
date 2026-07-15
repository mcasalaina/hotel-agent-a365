"""Validate deterministic fictional hotel source data and Foundry IQ documents."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from generate_hotel_data import DATE_END, DATE_START, REQUIRED_TABLES, stable_hash

RESERVATION_STATUSES = {
    "future",
    "arriving",
    "departed",
    "cancelled",
    "no_show",
    "completed",
    "in_house",
}
STAY_STATUSES = {"completed", "in_house"}
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


def validate_output(output: Path, docs_output: Path) -> list[str]:
    problems: list[str] = []
    manifest_path = output / "manifest.json"
    if not manifest_path.exists():
        return [f"missing manifest: {manifest_path}"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
            if int(row["sellable_rooms"]) < 0 or int(row["occupied_rooms"]) > int(
                row["sellable_rooms"]
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
        for row in tables["special_requests"]:
            if row["reservation_id"] not in reservation_ids or row["guest_id"] not in guest_ids:
                problems.append("special request FK failure")
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
        for row in tables["work_orders"]:
            if row["maintenance_request_id"] not in maintenance_ids:
                problems.append("work order FK failure")
            elif row["property_id"] != maintenance_properties[row["maintenance_request_id"]]:
                problems.append("work order property mismatch")
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
