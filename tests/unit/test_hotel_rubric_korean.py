from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_korean_rubric_preserves_english_structure_and_scoring() -> None:
    english = json.loads((ROOT / "evaluation/hotel-servicing-rubric.json").read_text())
    korean = json.loads((ROOT / "evaluation/hotel-servicing-rubric-korean.json").read_text())
    assert korean["name"] == "hotel-agent-rubric-korean"
    assert korean["display_name"] == "Hotel Servicing Rubric Korean"
    assert korean.keys() == english.keys()
    assert korean["categories"] == english["categories"]
    assert korean["metadata"].keys() == english["metadata"].keys()
    for key in ("local_rubric_version", "rubric_api"):
        assert korean["metadata"][key] == english["metadata"][key]
    assert korean["definition"].keys() == english["definition"].keys()
    assert korean["definition"]["type"] == english["definition"]["type"]
    assert korean["definition"]["pass_threshold"] == english["definition"]["pass_threshold"]
    assert len(korean["definition"]["dimensions"]) == 20
    for original, translated in zip(
        english["definition"]["dimensions"], korean["definition"]["dimensions"], strict=True
    ):
        assert translated.keys() == original.keys()
        assert {key: value for key, value in translated.items() if key != "description"} == {
            key: value for key, value in original.items() if key != "description"
        }
        description = translated["description"]
        assert re.search(r"[\uac00-\ud7a3]", description)
        assert "5점" in description and "1점" in description
        assert description.startswith("항상 적용됩니다.") == original["always_applicable"]
        assert ("필수 통과 조건:" in description) == ("Hard gate:" in original["description"])
        assert ("3점" in description) == ("3 for" in original["description"])
        assert not re.search(r"[\u4e00-\u9fff]", description)
    assert re.search(r"[\uac00-\ud7a3]", korean["description"])
    assert re.search(r"[\uac00-\ud7a3]", korean["metadata"]["jurisdiction"])


def test_korean_translation_retains_regulatory_references_and_operational_contracts() -> None:
    rubric = json.loads((ROOT / "evaluation/hotel-servicing-rubric-korean.json").read_text())
    dimensions = {
        dimension["id"]: dimension["description"]
        for dimension in rubric["definition"]["dimensions"]
    }
    references = {
        "privacy_and_data_safety": [
            "GDPR", "제5조", "제6조", "제12~22조", "제32조", "CCPA/CPRA", "1798.100",
        ],
        "payment_card_and_financial_data_protection": [
            "PCI DSS v4.0.1", "법률이 아닙니다", "CVV/CVC", "PIN",
        ],
        "transparent_lodging_prices_and_fees": [
            "FTC", "16 CFR Part 464", "2025년 5월 12일",
        ],
        "accessible_and_nondiscriminatory_service": [
            "ADA Title III", "28 CFR Part 36", "36.302(e)", "36.302(c)",
            "Civil Rights Act Title II", "42 USC 2000a",
        ],
        "cancellation_refund_and_consumer_rights": ["24시간", "현지 시간대"],
        "mail_recipient_integrity": ["To", "Cc", "Bcc", "Internet Message ID"],
        "servicing_authority_and_action_integrity": ["멱등성", "읽기 전용"],
        "reservation_date_and_status_semantics": ["7일", "같은 값은 어느 그룹에도 포함하지"],
        "chain_wide_completeness": ["20개 호텔 전체"],
        "language_continuity": ["사용자가 명확히 확립한 언어로 응답"],
    }
    for dimension_id, required in references.items():
        assert all(term in dimensions[dimension_id] for term in required)
