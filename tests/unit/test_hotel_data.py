from __future__ import annotations

import csv
import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from generate_hotel_data import DATE_END, DATE_START, generate
from validate_hotel_data import REAL_BRANDS, parse_frontmatter, validate_output

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
    scenario_data = json.loads((ROOT / "data" / "fixtures" / "demo_scenarios.json").read_text())
    reservation_ids = {row["reservation_id"] for row in rows(OUTPUT / "reservations.csv")}

    assert [row["property_id"] for row in property_rows] == [
        f"HTL-{number:03d}" for number in range(1, 21)
    ]
    assert {
        scenario["reservation_id"]
        for scenario in scenario_data["scenarios"]
        if "reservation_id" in scenario and scenario["reservation_id"].startswith("RES-")
    } <= reservation_ids


def test_dates_inventory_and_statuses_are_valid(generated_manifest: dict[str, object]) -> None:
    inventory = rows(OUTPUT / "daily_inventory.csv")
    metric_dates = {row["service_date"] for row in rows(OUTPUT / "property_daily_metrics.csv")}
    inventory_dates = {row["service_date"] for row in inventory}
    expected_dates = {
        date.fromordinal(DATE_START.toordinal() + offset).isoformat()
        for offset in range((DATE_END - DATE_START).days + 1)
    }
    reservation_statuses = {row["status"] for row in rows(OUTPUT / "reservations.csv")}

    assert inventory_dates == expected_dates
    assert metric_dates == expected_dates
    assert all(int(row["occupied_rooms"]) <= int(row["sellable_rooms"]) for row in inventory)
    assert all(
        DATE_START
        <= date.fromisoformat(row["check_in"])
        < date.fromisoformat(row["check_out"])
        <= DATE_END
        for row in rows(OUTPUT / "reservations.csv")
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
    assert dispute_rows[0]["billing_dispute_id"] == "BD-DEMO-MINIBAR"
    assert all(row["folio_id"] in folio_ids for row in dispute_rows)
    assert all(row["card_mask"].startswith("**** **** **** ") for row in payment_rows)
    assert all(
        "card_number" not in row and "cvv" not in row and "pan" not in row for row in payment_rows
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
