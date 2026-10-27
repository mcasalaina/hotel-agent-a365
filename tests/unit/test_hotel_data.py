from __future__ import annotations

import csv
import json
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest
from generate_hotel_data import (
    DATE_END,
    DATE_START,
    FIXTURES_PATH,
    TEMPORAL_BOUNDARY,
    build_reservations,
    generate,
    stable_hash,
)
from validate_hotel_data import (
    REAL_BRANDS,
    RESERVATION_STATUSES,
    parse_frontmatter,
    validate_output,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "generated" / "test-unit-output"
REPEAT_OUTPUT = ROOT / "data" / "generated" / "test-unit-repeat"
DOCS = ROOT / "data" / "generated" / "test-unit-docs"
REPEAT_DOCS = ROOT / "data" / "generated" / "test-unit-repeat-docs"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


@pytest.fixture(scope="module")
def generated_manifest() -> dict[str, object]:
    for path in (OUTPUT, REPEAT_OUTPUT, DOCS, REPEAT_DOCS):
        shutil.rmtree(path, ignore_errors=True)
    manifest = generate("demo", OUTPUT, DOCS)
    yield manifest
    for path in (OUTPUT, REPEAT_OUTPUT, DOCS, REPEAT_DOCS):
        shutil.rmtree(path, ignore_errors=True)


def test_demo_generation_is_deterministic(generated_manifest: dict[str, object]) -> None:
    repeat_manifest = generate("demo", REPEAT_OUTPUT, REPEAT_DOCS)

    assert generated_manifest["hashes"] == repeat_manifest["hashes"]
    assert generated_manifest["documents"] == repeat_manifest["documents"]


def test_property_completeness_and_named_fixtures(generated_manifest: dict[str, object]) -> None:
    property_rows = rows(OUTPUT / "properties.csv")
    guest_rows = rows(OUTPUT / "guests.csv")
    scenario_data = json.loads((ROOT / "data" / "fixtures" / "business_scenarios.json").read_text())
    reservation_ids = {row["reservation_id"] for row in rows(OUTPUT / "reservations.csv")}

    assert [row["property_id"] for row in property_rows] == [
        f"HTL-{number:03d}" for number in range(1, 21)
    ]
    assert {
        scenario["reservation_id"]
        for scenario in scenario_data["scenarios"]
        if "reservation_id" in scenario and scenario["reservation_id"].startswith("RES-")
    } <= reservation_ids
    assert guest_rows[0] == {
        "guest_id": "GST-000001",
        "first_name": "Maria",
        "last_name": "Garcia",
        "email": "mariagarcia@cam3652701.onmicrosoft.com",
        "country": "United States",
        "privacy_consent": "true",
    }


def test_dates_inventory_and_statuses_are_valid(generated_manifest: dict[str, object]) -> None:
    inventory = rows(OUTPUT / "daily_inventory.csv")
    metric_dates = {row["service_date"] for row in rows(OUTPUT / "property_daily_metrics.csv")}
    inventory_dates = {row["service_date"] for row in inventory}
    expected_dates = {
        date.fromordinal(DATE_START.toordinal() + offset).isoformat()
        for offset in range((DATE_END - DATE_START).days + 1)
    }
    reservation_rows = rows(OUTPUT / "reservations.csv")
    reservation_statuses = {row["status"] for row in reservation_rows}

    assert inventory_dates == expected_dates
    assert metric_dates == expected_dates
    assert all(int(row["occupied_rooms"]) <= int(row["sellable_rooms"]) for row in inventory)
    assert all(
        DATE_START
        <= date.fromisoformat(row["check_in"])
        < date.fromisoformat(row["check_out"])
        <= DATE_END
        for row in reservation_rows
    )
    assert all(
        TEMPORAL_BOUNDARY
        not in {date.fromisoformat(row["check_in"]), date.fromisoformat(row["check_out"])}
        for row in reservation_rows
    )
    assert all(
        date.fromisoformat(row["check_in"]) > TEMPORAL_BOUNDARY
        for row in reservation_rows
        if row["status"] in {"future", "arriving"}
    )
    assert all(
        date.fromisoformat(row["check_out"]) < TEMPORAL_BOUNDARY
        for row in reservation_rows
        if row["status"] in {"completed", "departed", "no_show"}
    )
    assert all(
        date.fromisoformat(row["check_in"])
        < TEMPORAL_BOUNDARY
        < date.fromisoformat(row["check_out"])
        for row in reservation_rows
        if row["status"] == "in_house"
    )
    assert {
        "future",
        "arriving",
        "departed",
        "cancelled",
        "no_show",
        "completed",
        "in_house",
    } <= reservation_statuses


def test_every_property_has_reservations_across_all_statuses(
    generated_manifest: dict[str, object],
) -> None:
    statuses_by_property: defaultdict[str, set[str]] = defaultdict(set)
    for row in rows(OUTPUT / "reservations.csv"):
        statuses_by_property[row["property_id"]].add(row["status"])

    property_ids = {row["property_id"] for row in rows(OUTPUT / "properties.csv")}
    assert set(statuses_by_property) == property_ids
    assert all(
        statuses_by_property[property_id] >= RESERVATION_STATUSES for property_id in property_ids
    )


def test_full_scale_active_reservations_cover_every_property() -> None:
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["scenarios"]
    reservations = build_reservations("full", fixtures)
    active_by_property: defaultdict[str, int] = defaultdict(int)
    for reservation in reservations:
        check_in = date.fromisoformat(reservation["check_in"])
        if date(2026, 9, 2) <= check_in <= date(2026, 9, 8) and reservation["status"] in {
            "future",
            "arriving",
        }:
            active_by_property[reservation["property_id"]] += 1

    assert set(active_by_property) == {f"HTL-{number:03d}" for number in range(1, 21)}
    assert all(count > 0 for count in active_by_property.values())


def test_maria_garcia_has_coherent_future_acceptance_reservation(
    generated_manifest: dict[str, object],
) -> None:
    reservations = {row["reservation_id"]: row for row in rows(OUTPUT / "reservations.csv")}
    maria = reservations["RES-FAMILY-2026"]

    assert maria == {
        "reservation_id": "RES-FAMILY-2026",
        "guest_id": "GST-000001",
        "property_id": "HTL-004",
        "room_type_id": "HTL-004-RT-03",
        "check_in": "2026-09-10",
        "check_out": "2026-09-12",
        "status": "future",
        "cancellation_policy": "flexible",
        "room_count": "2",
        "rate_total": maria["rate_total"],
        "currency": "USD",
        "channel": "direct",
    }


def test_referential_integrity_folio_reconciliation_and_masked_payments(
    generated_manifest: dict[str, object],
) -> None:
    folios = rows(OUTPUT / "folios.csv")
    folio_ids = {row["folio_id"] for row in folios}
    transaction_folio_ids = {row["folio_id"] for row in rows(OUTPUT / "folio_transactions.csv")}
    payment_rows = rows(OUTPUT / "payments.csv")
    dispute_rows = rows(OUTPUT / "billing_disputes.csv")

    assert validate_output(OUTPUT, DOCS) == []
    assert transaction_folio_ids == folio_ids
    assert {row["folio_id"] for row in payment_rows} == folio_ids
    assert dispute_rows[0]["billing_dispute_id"] == "BD-MINIBAR"
    assert all(row["folio_id"] in folio_ids for row in dispute_rows)
    assert all(row["card_mask"].startswith("**** **** **** ") for row in payment_rows)
    assert all(
        "card_number" not in row and "cvv" not in row and "pan" not in row for row in payment_rows
    )


@pytest.mark.parametrize(
    ("table", "key", "value", "expected_problem"),
    [
        ("guests", "email", "stale@example.com", "identity"),
        ("reservations", "room_type_id", "HTL-004-RT-02", "reservation"),
        ("reservations", "room_count", "1", "reservation"),
    ],
)
def test_validator_rejects_stale_canonical_maria_records(
    generated_manifest: dict[str, object],
    tmp_path: Path,
    table: str,
    key: str,
    value: str,
    expected_problem: str,
) -> None:
    output = tmp_path / "generated"
    shutil.copytree(OUTPUT, output)
    path = output / f"{table}.csv"
    records = rows(path)
    id_column, record_id = (
        ("guest_id", "GST-000001") if table == "guests" else ("reservation_id", "RES-FAMILY-2026")
    )
    next(record for record in records if record[id_column] == record_id)[key] = value
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["hashes"][table] = stable_hash(path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert f"Maria Garcia acceptance-test {expected_problem} is incoherent" in validate_output(
        output, DOCS
    )


def test_foundry_iq_documents_have_temporal_metadata_and_no_real_brands(
    generated_manifest: dict[str, object],
) -> None:
    document_paths = sorted(DOCS.glob("*/*.generated.md"))
    metadata = [parse_frontmatter(path) for path in document_paths]
    dated_notices = [item for item in metadata if item["category"] == "dated_notice"]

    assert len(document_paths) == 95
    assert len([item for item in metadata if item["category"] == "property_profile"]) == 20
    assert len([item for item in metadata if item["category"] == "dining_local"]) == 20
    assert len(dated_notices) == 20
    assert all(item["valid_from"] <= item["valid_to"] for item in metadata)
    assert all(item["source_path"].startswith("foundryiq-docs/") for item in metadata)
    corpus = "\n".join(path.read_text(encoding="utf-8").lower() for path in document_paths)
    assert not any(brand in corpus for brand in REAL_BRANDS)
