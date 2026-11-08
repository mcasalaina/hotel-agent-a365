from __future__ import annotations

import ast
import csv
import json
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest
from generate_hotel_data import (
    DATE_END,
    DATE_SHIFT,
    DATE_START,
    FIXTURES_PATH,
    ROSTER,
    TEMPORAL_BOUNDARY,
    build_reservations,
    generate,
    shift_dated_rows,
    stable_hash,
)
from hotel_servicing_agent.property_catalog import PROPERTY_NAMES, official_property_name
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
    scenario_data = json.loads(FIXTURES_PATH.read_text())
    reservation_ids = {row["reservation_id"] for row in rows(OUTPUT / "reservations.csv")}

    assert [row["property_id"] for row in property_rows] == [
        f"HTL-{number:03d}" for number in range(1, 21)
    ]
    expected_names = {
        f"HTL-{number:03d}": f"Hotel {entry[0]}" for number, entry in enumerate(ROSTER, start=1)
    }
    assert expected_names == PROPERTY_NAMES
    assert {row["property_id"]: row["name"] for row in property_rows} == expected_names
    assert official_property_name("HTL-004") == "Hotel Scottsdale Sonoran Resort"
    assert official_property_name("HTL-010") == "Hotel Paris Left Bank"
    assert {
        scenario["reservation_id"]
        for scenario in scenario_data["scenarios"]
        if "reservation_id" in scenario and scenario["reservation_id"].startswith("RES-")
    } <= reservation_ids
    assert guest_rows[0] == {
        "guest_id": "GST-000001",
        "first_name": "Maria",
        "last_name": "Garcia",
        "email": "mariagarcia@cam3652609.onmicrosoft.com",
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
        if date(2026, 11, 9) <= check_in <= date(2026, 11, 15) and reservation["status"] in {
            "future",
            "arriving",
        }:
            active_by_property[reservation["property_id"]] += 1

    assert set(active_by_property) == {f"HTL-{number:03d}" for number in range(1, 21)}
    assert all(count > 0 for count in active_by_property.values())


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


def test_fixed_reference_date_and_canonical_family(generated_manifest: dict[str, object]) -> None:
    assert date(2026, 11, 8) == TEMPORAL_BOUNDARY
    assert DATE_SHIFT.days == 68
    assert generated_manifest["temporal_boundary"] == "2026-11-08"
    assert generated_manifest["date_range"] == {"start": "2026-05-08", "end": "2027-06-07"}
    reservation = next(
        row
        for row in rows(OUTPUT / "reservations.csv")
        if row["reservation_id"] == "RES-FAMILY-2026"
    )
    assert {
        key: reservation[key]
        for key in (
            "guest_id",
            "property_id",
            "room_type_id",
            "check_in",
            "check_out",
            "room_count",
            "status",
        )
    } == {
        "guest_id": "GST-000001",
        "property_id": "HTL-004",
        "room_type_id": "HTL-004-RT-03",
        "check_in": "2026-11-17",
        "check_out": "2026-11-19",
        "room_count": "2",
        "status": "future",
    }
    assert (
        next(
            row
            for row in rows(OUTPUT / "restaurant_reservations.csv")
            if row["restaurant_reservation_id"] == "RR-DINING"
        )["reservation_at"]
        == "2026-11-18T19:30:00"
    )
    assert (
        next(
            row
            for row in rows(OUTPUT / "special_requests.csv")
            if row["special_request_id"] == "SR-PREARRIVAL"
        )["requested_at"]
        == "2026-11-14T10:00:00"
    )
    assert rows(OUTPUT / "audit_events.csv")[0]["occurred_at"] == "2026-10-17T10:00:01"


def test_reservation_builders_respect_strict_lifecycle_dates(
    generated_manifest: dict[str, object],
) -> None:
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["scenarios"]
    for reservations in (rows(OUTPUT / "reservations.csv"), build_reservations("demo", fixtures)):
        for reservation in reservations:
            check_in = date.fromisoformat(reservation["check_in"])
            check_out = date.fromisoformat(reservation["check_out"])
            assert TEMPORAL_BOUNDARY not in {check_in, check_out}
            if reservation["status"] in {"future", "arriving"}:
                assert check_in > TEMPORAL_BOUNDARY
            elif reservation["status"] == "in_house":
                assert check_in < TEMPORAL_BOUNDARY < check_out
            else:
                assert check_out < TEMPORAL_BOUNDARY


def test_date_shift_preserves_all_linked_timestamps_and_non_date_fields() -> None:
    original = {
        "check_in": "2026-09-10",
        "actual_check_out": "2026-09-12T11:00:00",
        "posted_at": "2026-03-04T13:00:00",
        "reservation_id": "RES-FAMILY-2026",
        "actual_check_in": "",
        "details": "Do not shift arbitrary free text 2026-09-10",
    }
    shifted = next(shift_dated_rows([original]))
    assert shifted == {
        **original,
        "check_in": "2026-11-17",
        "actual_check_out": "2026-11-19T11:00:00",
        "posted_at": "2026-05-11T13:00:00",
    }
    assert original["check_in"] == "2026-09-10"


def test_generated_csv_headers_and_keys_match_initial_load_notebook(
    generated_manifest: dict[str, object],
) -> None:
    path = ROOT / "fabric" / "notebooks" / "initial_load.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    source = "\n".join(
        "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"
    )
    tree = ast.parse(source)
    spec = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "SOURCE_TABLE_SPECS"
    )
    assert isinstance(spec, ast.Dict)
    assert {ast.literal_eval(key) for key in spec.keys} == set(generated_manifest["counts"])
    for key, value in zip(spec.keys, spec.values, strict=True):
        table = ast.literal_eval(key)
        assert isinstance(value, ast.Dict)
        fields = {
            ast.literal_eval(name): entry
            for name, entry in zip(value.keys, value.values, strict=True)
        }
        schema = fields["schema"]
        assert isinstance(schema, ast.Call)
        assert isinstance(schema.args[0], ast.List)
        columns = [ast.literal_eval(field.args[0]) for field in schema.args[0].elts]
        records = rows(OUTPUT / f"{table}.csv")
        assert list(records[0]) == columns, table
        primary_key = ast.literal_eval(fields["primary_key"])
        keys = [tuple(record[column] for column in primary_key) for record in records]
        assert len(keys) == len(set(keys)), table
    dates = {
        node.targets[0].id: ast.literal_eval(ast.Tuple(elts=node.value.args))
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"DATE_START", "DATE_END"}
    }
    assert date(*dates["DATE_START"]) == DATE_START
    assert date(*dates["DATE_END"]) == DATE_END


@pytest.mark.parametrize(
    ("table", "id_column", "record_id", "key", "value", "expected"),
    [
        ("guests", "guest_id", "GST-000001", "email", "stale@example.test", "identity"),
        ("reservations", "reservation_id", "RES-FAMILY-2026", "room_count", "1", "reservation"),
        (
            "reservations",
            "reservation_id",
            "RES-FAMILY-2026",
            "check_in",
            "2026-11-08",
            "future reservation is not strictly after",
        ),
        (
            "stays",
            "stay_id",
            "STY-0000001",
            "actual_check_in",
            "2026-03-03T15:00:00",
            "stay dates do not match",
        ),
        (
            "folio_transactions",
            "folio_transaction_id",
            "FTX-0000001-01",
            "posted_at",
            "2026-11-09T13:00:00",
            "past folio transaction",
        ),
        (
            "restaurant_reservations",
            "restaurant_reservation_id",
            "RR-DINING",
            "reservation_at",
            "2026-11-08T19:30:00",
            "future dining reservation",
        ),
        (
            "special_requests",
            "special_request_id",
            "SR-PREARRIVAL",
            "requested_at",
            "2026-11-08T10:00:00",
            "future special request",
        ),
        (
            "maintenance_requests",
            "maintenance_request_id",
            "MR-HVAC",
            "reported_at",
            "2026-07-10T21:00:00",
            "maintenance request is outside",
        ),
        (
            "work_orders",
            "work_order_id",
            "WO-HVAC",
            "opened_at",
            "2026-11-08T21:18:00",
            "work order falls on",
        ),
        (
            "audit_events",
            "audit_event_id",
            "AUD-001",
            "occurred_at",
            "2026-11-09T10:00:01",
            "past audit_events",
        ),
    ],
)
def test_validator_rejects_stale_identity_and_unshifted_linked_dates(
    generated_manifest: dict[str, object],
    table: str,
    id_column: str,
    record_id: str,
    key: str,
    value: str,
    expected: str,
) -> None:
    output = ROOT / "data" / "generated" / "test-unit-corrupt"
    shutil.rmtree(output, ignore_errors=True)
    try:
        shutil.copytree(OUTPUT, output)
        path = output / f"{table}.csv"
        records = rows(path)
        next(record for record in records if record[id_column] == record_id)[key] = value
        with path.open("w", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        manifest_path = output / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["hashes"][table] = stable_hash(path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        assert any(expected in problem for problem in validate_output(output, DOCS))
    finally:
        shutil.rmtree(output, ignore_errors=True)


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
    property_names = {row["property_id"]: row["name"] for row in rows(OUTPUT / "properties.csv")}
    for path, item in zip(document_paths, metadata, strict=True):
        if item["property_id"] == "chain-wide":
            continue
        name = property_names[item["property_id"]]
        assert item["title"].startswith(name)
        assert name in path.read_text(encoding="utf-8")


def test_checked_in_foundry_iq_documents_match_generator(
    generated_manifest: dict[str, object],
) -> None:
    expected = {
        path.relative_to(DOCS): path.read_text(encoding="utf-8")
        for path in DOCS.glob("*/*.generated.md")
    }
    checked_in_docs = ROOT / "foundryiq-docs"
    actual = {
        path.relative_to(checked_in_docs): path.read_text(encoding="utf-8")
        for path in checked_in_docs.glob("*/*.generated.md")
    }

    assert actual == expected
