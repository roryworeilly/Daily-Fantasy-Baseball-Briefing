#!/usr/bin/env python3
"""Run the split briefing pipeline (fdbRV.py at repo root remains a full backup)."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_src = _ROOT / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from fdb.run import main  # type: ignore

if __name__ == "__main__":
    main()
