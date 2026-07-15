#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation" / "assert" / "src"))

if __name__ == "__main__":
    from hotel_assert.cli import main

    main()
