"""Tests for the Agent 365 inbound activity compatibility helpers."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "agent" / "inbound_compat.py"
spec = importlib.util.spec_from_file_location("inbound_compat", MODULE_PATH)
assert spec is not None and spec.loader is not None
inbound_compat = importlib.util.module_from_spec(spec)
sys.modules["inbound_compat"] = inbound_compat
spec.loader.exec_module(inbound_compat)


def test_product_info_entity_is_canonicalized_without_mutating_input() -> None:
    body = {
        "type": "message",
        "entities": [{"type": "productInfo", "id": "x"}, {"type": "mention"}],
    }

    result = inbound_compat.normalize_known_entity_types(body)

    assert result["entities"][0] == {"type": "ProductInfo", "id": "x"}
    assert result["entities"][1] == {"type": "mention"}
    assert body["entities"][0]["type"] == "productInfo"


def test_canonical_and_unrelated_bodies_are_returned_unchanged() -> None:
    canonical = {"entities": [{"type": "ProductInfo"}]}
    no_entities = {"type": "message"}

    assert inbound_compat.normalize_known_entity_types(canonical) is canonical
    assert inbound_compat.normalize_known_entity_types(no_entities) is no_entities
    assert inbound_compat.normalize_known_entity_types("text") == "text"


def test_wrapper_normalizes_json_and_delegates_everything_else() -> None:
    class Request:
        method = "POST"

        async def json(self) -> dict:
            return {"entities": [{"type": "productinfo"}]}

    wrapped = inbound_compat.NormalizedBodyRequest(Request())

    assert asyncio.run(wrapped.json()) == {"entities": [{"type": "ProductInfo"}]}
    assert wrapped.method == "POST"


def test_shape_summary_omits_message_content() -> None:
    summary = inbound_compat.describe_inbound_shape(
        {"type": "message", "text": "secret text", "entities": [{"type": "productInfo"}]}
    )

    assert "secret text" not in summary
    assert "entities=productInfo" in summary
