from __future__ import annotations

from pathlib import Path

from hotel_assert.config_validation import validate_repository


def test_repository_assert_configuration_is_consistent() -> None:
    root = Path(__file__).resolve().parents[3]
    assert validate_repository(root) == []
