from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_chinese_rubric_preserves_english_structure_and_scoring() -> None:
    english = json.loads((ROOT / "evaluation/hotel-servicing-rubric.json").read_text())
    chinese = json.loads((ROOT / "evaluation/hotel-servicing-rubric-chinese.json").read_text())
    assert chinese["name"] == "hotel-agent-rubric-chinese"
    assert chinese["display_name"] == "Hotel Servicing Rubric Chinese"
    assert chinese.keys() == english.keys()
    assert chinese["categories"] == english["categories"]
    assert chinese["metadata"].keys() == english["metadata"].keys()
    for key in ("local_rubric_version", "rubric_api"):
        assert chinese["metadata"][key] == english["metadata"][key]
    assert chinese["definition"].keys() == english["definition"].keys()
    assert chinese["definition"]["type"] == english["definition"]["type"]
    assert chinese["definition"]["pass_threshold"] == english["definition"]["pass_threshold"]
    assert len(chinese["definition"]["dimensions"]) == 20
    for original, translated in zip(
        english["definition"]["dimensions"], chinese["definition"]["dimensions"], strict=True
    ):
        assert translated.keys() == original.keys()
        assert {key: value for key, value in translated.items() if key != "description"} == {
            key: value for key, value in original.items() if key != "description"
        }
        description = translated["description"]
        assert re.search(r"[\u4e00-\u9fff]", description)
        assert len(description) >= 170
        assert "得 5 分" in description and "得 1 分" in description
        assert description.startswith("始终适用。") == original["always_applicable"]
        assert ("硬性门槛" in description) == ("Hard gate:" in original["description"])
        if original["weight"] == 3 or original["id"] in {
            "property_attribution_date_and_citations", "exact_record_full_history_lookup",
        }:
            assert "得 3 分" in description
    assert re.search(r"[\u4e00-\u9fff]", chinese["description"])


def test_chinese_translation_retains_regulatory_references_and_operational_contracts() -> None:
    rubric = json.loads((ROOT / "evaluation/hotel-servicing-rubric-chinese.json").read_text())
    dimensions = {
        dimension["id"]: dimension["description"]
        for dimension in rubric["definition"]["dimensions"]
    }
    references = {
        "privacy_and_data_safety": [
            "GDPR", "5、6、12 至 22 及 32", "CCPA/CPRA", "1798.100",
        ],
        "payment_card_and_financial_data_protection": [
            "PCI DSS v4.0.1", "不是法律法规", "CVV/CVC", "PIN",
        ],
        "transparent_lodging_prices_and_fees": [
            "FTC", "16 CFR Part 464", "2025 年 5 月 12 日",
        ],
        "accessible_and_nondiscriminatory_service": [
            "ADA", "28 CFR Part 36", "36.302(e)", "36.302(c)", "42 USC 2000a",
        ],
        "cancellation_refund_and_consumer_rights": ["24 小时", "当地时区"],
        "mail_recipient_integrity": ["To", "Cc", "Bcc", "Internet Message ID"],
        "servicing_authority_and_action_integrity": ["幂等性", "只读"],
        "reservation_date_and_status_semantics": ["七天", "相等值不属于其中任何一组"],
        "chain_wide_completeness": ["全部 20 家酒店"],
        "language_continuity": ["使用用户已明确确立的语言回复"],
    }
    for dimension_id, required in references.items():
        assert all(term in dimensions[dimension_id] for term in required)
