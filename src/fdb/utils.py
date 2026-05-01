"""
Shared utility helpers for the fdb package and tools.

Functions here were previously duplicated across model.py,
build_projection_cache.py, build_reference_cache.py, and
build_statcast_cache.py.  Import from here instead of redefining.
"""
import os
import re
import time


# ── Name normalisation ────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """
    Lowercase, strip punctuation, collapse whitespace.
    Used for fuzzy player-name matching across data sources.
    """
    if not name:
        return ""
    text = re.sub(r"[^\w\s]", "", str(name).lower().strip())
    return re.sub(r"\s+", " ", text)


# ── Numeric helpers ───────────────────────────────────────────────────────────

def compact(v, ndigits: int = 4) -> float:
    """
    Round a value to *ndigits* decimal places for compact JSON storage.
    Returns 0.0 for non-numeric input or NaN.
    """
    try:
        f = float(v)
        return round(f, ndigits) if f == f else 0.0   # NaN guard: NaN != NaN
    except Exception:
        return 0.0


def get_metric(row: dict, *keys, default: float = 0.0) -> float:
    """
    Return the first non-None, non-empty numeric value found in *row*
    under any of the supplied *keys*.  Falls back to *default*.
    """
    for key in keys:
        if key in row and row[key] not in (None, ""):
            try:
                return float(row[key])
            except Exception:
                pass
    return default


# ── Cache freshness ───────────────────────────────────────────────────────────

def cache_is_fresh(path: str, max_age_days: float = 1.0) -> bool:
    """
    Return True if *path* exists and was modified within *max_age_days*.
    """
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) < max_age_days * 86_400
