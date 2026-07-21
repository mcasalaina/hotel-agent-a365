from __future__ import annotations

import importlib.util
from array import array
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).parents[2] / "scripts/run_voice_smoke.py"
_SPEC = importlib.util.spec_from_file_location("run_voice_smoke", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
_trim_edge_silence = _MODULE._trim_edge_silence


def test_trim_edge_silence_preserves_short_padding() -> None:
    one_second = 24_000
    samples = array(
        "h",
        [0] * one_second + [1_000] * 2_400 + [0] * one_second,
    )

    trimmed = _trim_edge_silence(samples.tobytes())

    expected_samples = 4_800 + 2_400 + 4_800
    assert len(trimmed) == expected_samples * 2


def test_trim_edge_silence_rejects_silent_recording() -> None:
    with pytest.raises(ValueError, match="no audible speech"):
        _trim_edge_silence(array("h", [0] * 24_000).tobytes())
