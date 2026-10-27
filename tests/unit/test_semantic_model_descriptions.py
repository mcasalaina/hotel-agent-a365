"""Local-only regression coverage for the approved ordinary TOM descriptions.

The metadata digest pins the accepted 72-string manifest, independently of source.
Protected digests pin the activation-base templates with only the new table/column
description blocks omitted. They retain existing measure descriptions and all code.
Update these baselines deliberately when an intentional model change is approved.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from deploy_semantic_model_and_report import ROOT, TEMPLATE, build_definition

MODEL = ROOT / "fabric/semantic-model"
APPROVED_METADATA_SHA256 = "34e34c7d07fa7b5653f88350e0ba408fa21228a38fd602096f53aab8567b8099"
PROTECTED_TABLE_SHA256 = {
    "Booking Pace Daily": "dc1621c6d36cd62bb4d29afc6eab56b5d007cbb9f4b12222b709cc2e483d3be4",
    "Date": "15349b07c809a2490627cf73644fc26a645ccbd31db9a82472a611f704aa8a4e",
    "Disputes Daily": "3f5aa949ecf61519a7995341ac2b9602388f5b155bb28a1b694be9edf539d6d9",
    "Maintenance Response Daily": (
        "ca13da7abe2b5e852dbf4b3b0aa6957db7384fcc1be370625d7c8f153bcca776"
    ),
    "Outlet": "f7aca98f0cdd708da321e8083b2c324c37c8314388efa8844ff2d2a5c34d1d60",
    "Property KPI Daily": "6a10ac01aebaba5cfa2710539531d870f41eb69a6af225f59a2b499429240f60",
    "Property": "160883a5c5bc7d3193ec36c4f4b66af613fa43fca9f9e959465a4e9cb2300e37",
    "Requests Daily": "05f8ee1a346d07582b681f63b049323e6fcf61b690130cdf3995a52951020c90",
    "Restaurant Daily": "0d8e1034c82bbb4a7915b47aca5c44fc71d7a7eafaeef22b73ba3ab0e6dde0ba",
}
DECLARATION = re.compile(r"^(?P<indent>\t?)(?P<kind>table|column) (?P<name>.+)$")


def _metadata(parts: dict[str, str]) -> dict:
    """Extract this model's single-line descriptions without touching measure text."""
    metadata = {}
    for path, text in parts.items():
        if not path.startswith("definition/tables/") or not path.endswith(".tmdl"):
            continue
        spec = {"description": "", "columns": {}}
        table_name = Path(path).stem
        lines = text.splitlines()
        for index, line in enumerate(lines):
            match = DECLARATION.fullmatch(line)
            if not match:
                continue
            name = match["name"]
            if name.startswith("'"):
                assert name.endswith("'")
                name = name[1:-1].replace("''", "'")
            prefix = match["indent"] + "/// "
            assert index > 0 and lines[index - 1].startswith(prefix), (path, name)
            description = lines[index - 1][len(prefix) :]
            assert 0 < len(description) <= 200
            if match["kind"] == "table":
                assert name == table_name
                assert not spec["description"]
                spec["description"] = description
            else:
                assert name not in spec["columns"]
                spec["columns"][name] = description
        assert spec["description"]
        metadata[table_name] = spec
    return metadata


def _assert_approved_metadata(parts: dict[str, str]) -> None:
    metadata = _metadata(parts)
    assert len(metadata) == 9
    assert sum(len(table["columns"]) for table in metadata.values()) == 63
    serialized = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(serialized.encode()).hexdigest() == APPROVED_METADATA_SHA256


def test_source_retains_all_72_approved_descriptions() -> None:
    _assert_approved_metadata(
        {
            path.relative_to(MODEL).as_posix(): path.read_bytes().decode()
            for path in (MODEL / "definition/tables").glob("*.tmdl")
        }
    )


@pytest.mark.parametrize("table", sorted(PROTECTED_TABLE_SHA256))
def test_description_sync_preserves_all_other_table_content(table: str) -> None:
    source = (MODEL / "definition/tables" / f"{table}.tmdl").read_bytes().decode()
    # Remove only the new single-line descriptions immediately above table/column.
    # Existing measure descriptions, whitespace, expressions and partitions remain.
    protected = re.sub(r"(?m)^([ \t]*)///[^\n]*\n(?=\1(?:table|column) )", "", source)
    assert hashlib.sha256(protected.encode()).hexdigest() == PROTECTED_TABLE_SHA256[table]


@pytest.mark.parametrize("environment", ["dev", "test", "prod"])
def test_builder_preserves_descriptions_and_environment_substitutions(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A template build must not authenticate, deploy or call any external CLI.
    command = Mock(side_effect=AssertionError("Template builds must remain local"))
    monkeypatch.setattr(subprocess, "run", command)
    values = {
        "WORKSPACE_ID": f"{environment}-workspace",
        "HOTEL_GUEST_SERVICES_LAKEHOUSE_ID": f"{environment}-guest",
        "HOTEL_OPERATIONS_LAKEHOUSE_ID": f"{environment}-operations",
        "SEMANTICMODEL_ID": f"{environment}-model",
    }
    definition = build_definition(MODEL, values)
    parts = {
        part["path"]: base64.b64decode(part["payload"]).decode() for part in definition["parts"]
    }
    _assert_approved_metadata(parts)
    substituted = set()
    for path, actual in parts.items():
        source = (MODEL / path).read_bytes().decode()
        substituted.update(TEMPLATE.findall(source))
        assert actual == TEMPLATE.sub(lambda match: values[match[1]], source)
        assert not TEMPLATE.search(actual)
    assert substituted == {
        "WORKSPACE_ID",
        "HOTEL_GUEST_SERVICES_LAKEHOUSE_ID",
        "HOTEL_OPERATIONS_LAKEHOUSE_ID",
    }
    model = parts["definition/model.tmdl"]
    assert f"{environment}-workspace/{environment}-guest" in model
    assert f"{environment}-workspace/{environment}-operations" in model
    command.assert_not_called()
