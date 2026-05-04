"""
Build / refresh statcast_cache.json  (Phase 2 — Analytics Roadmap)
──────────────────────────────────────────────────────────────────
Run from the FB directory with the project venv:

    .venv/bin/python tools/build_statcast_cache.py

Options:
    --force       Rebuild even if cache is fresh (< 7 days old)
    --season N    Override target season (default: current year - 1)

What this fetches from Baseball Savant (via pybaseball):
  Batters
    • Expected stats    : xBA, xSLG, xwOBA + gap vs actual (regression signal)
    • Exit velo/barrels : avg EV, EV90, barrel%, hard-hit%
    • Sprint speed      : ft/s (speed tier + stolen-base predictor)
  Pitchers
    • Expected stats    : xERA, xwOBA-against (buy-low / sell-high signal)
    • Exit velo/barrels : barrel%-against, hard-hit%-against (contact quality)

Token-optimization design:
  • TTL = 7 days — Statcast data is updated weekly, no need to re-fetch daily
  • Roster-aware: cache covers all MLB players (needed for FA scouting)
    but stores only ~15 numeric fields per player (not full DataFrames)
  • MLBAM ID is the primary key — no fragile name-matching across sources
  • Compact JSON: no whitespace, floats rounded to 4 decimal places
  • Built-at timestamp lets the briefing show data freshness without refetching

Cache location: FB/statcast_cache.json
"""

import os
import sys
import json
import time
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH  = os.path.join(SCRIPT_DIR, "statcast_cache.json")
YEAR        = int(os.environ.get("YEAR", str(datetime.now().year)))
SEASON      = YEAR - 1
CACHE_TTL_DAYS = 7

# ── Helpers ───────────────────────────────────────────────────────────────────

import sys, os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', 'src'))
from fdb.utils import compact as _c, cache_is_fresh as _cache_is_fresh

def _str_id(row, *keys):
    """Extract a string ID from a dict row, trying multiple key names."""
    for k in keys:
        v = row.get(k)
        if v is not None:
            try:
                i = int(float(v))
                if i > 0:
                    return str(i)
            except Exception:
                pass
    return ""

def _player_name(row) -> str:
    """
    Extract player full name from a Baseball Savant / pybaseball CSV row.

    Baseball Savant returns names in several formats depending on the endpoint:
      • 'player_name'  → "Last, First"  (most leaderboards)
      • 'first_name' + 'last_name'  → separate columns (some endpoints)
      • 'name'        → "First Last"  (some endpoints)

    Returns: "First Last" string, or "" if nothing useful found.
    """
    def _clean(raw) -> str:
        text = str(raw or "").strip()
        if not text or text.lower() in {"nan", "none"}:
            return ""
        return " ".join(text.split())

    def _from_last_first(raw) -> str:
        raw = _clean(raw)
        if not raw:
            return ""
        if "," in raw:
            last, first = raw.split(",", 1)
            return _clean(f"{first} {last}")
        return raw

    # 1) Separate first/last columns (some endpoints include these)
    first = _clean(
        row.get("first_name")
        or row.get("first name")
        or row.get("player_first_name")
    )
    last = _clean(
        row.get("last_name")
        or row.get("last name")
        or row.get("player_last_name")
    )
    if first or last:
        return f"{first} {last}".strip()

    # 2) Single-column display names from Baseball Savant / pybaseball
    for key in (
        "player_name",
        "player name",
        "name_display_first_last",
        "full_name",
        "full name",
        "name",
    ):
        name = _from_last_first(row.get(key))
        if name:
            return name

    # 3) Some CSV exports use a combined "Last, First" column label
    for key in (
        "last_name, first_name",
        "last name, first name",
        "lastname, firstname",
    ):
        name = _from_last_first(row.get(key))
        if name:
            return name

    return ""

def _gap(actual, expected):
    """Return expected - actual gap (positive = underperformer / buy-low)."""
    a, e = _c(actual), _c(expected)
    if a == 0.0 or e == 0.0:
        return 0.0
    return _c(e - a)

# ── pybaseball imports ────────────────────────────────────────────────────────

try:
    from pybaseball import (
        statcast_batter_expected_stats,
        statcast_batter_exitvelo_barrels,
        statcast_sprint_speed,
        statcast_pitcher_expected_stats,
        statcast_pitcher_exitvelo_barrels,
    )
except ImportError:
    sys.exit("ERROR: pybaseball not installed.  Run:  pip install pybaseball")

# ── Loaders ───────────────────────────────────────────────────────────────────

def load_batter_data(season):
    """Merge expected stats + exit velo/barrels + sprint speed into one dict keyed by MLBAM ID."""
    print(f"  Fetching batter expected stats ({season})...")
    try:
        xdf = statcast_batter_expected_stats(season, minPA=25).to_dict(orient="records")
        print(f"    → {len(xdf)} rows")
    except Exception as e:
        print(f"    WARNING: expected stats failed: {e}")
        xdf = []

    print(f"  Fetching batter exit velo / barrels ({season})...")
    try:
        evdf = statcast_batter_exitvelo_barrels(season, minBBE=25).to_dict(orient="records")
        print(f"    → {len(evdf)} rows")
    except Exception as e:
        print(f"    WARNING: exit velo failed: {e}")
        evdf = []

    print(f"  Fetching sprint speed ({season})...")
    try:
        spdf = statcast_sprint_speed(season, min_opp=5).to_dict(orient="records")
        print(f"    → {len(spdf)} rows")
    except Exception as e:
        print(f"    WARNING: sprint speed failed: {e}")
        spdf = []

    batters = {}

    # ── Expected stats layer ──────────────────────────────────────────────────
    for row in xdf:
        mlbam = _str_id(row, "player_id", "mlbam_id", "batter")
        if not mlbam:
            continue
        name = _player_name(row)
        actual_woba = _c(row.get("woba", row.get("wobacon", 0)))
        est_woba    = _c(row.get("est_woba", row.get("xwoba", 0)))
        actual_ba   = _c(row.get("ba", row.get("batting_avg", 0)))
        est_ba      = _c(row.get("est_ba", row.get("xba", 0)))
        actual_slg  = _c(row.get("slg", 0))
        est_slg     = _c(row.get("est_slg", row.get("xslg", 0)))

        batters[mlbam] = {
            "name":       name,
            # Actual vs expected — the core regression/breakout signal
            "wOBA":       actual_woba,
            "xwOBA":      est_woba,
            "xwOBA_gap":  _gap(actual_woba, est_woba),  # positive = buy-low
            "BA":         actual_ba,
            "xBA":        est_ba,
            "xBA_gap":    _gap(actual_ba,   est_ba),
            "SLG":        actual_slg,
            "xSLG":       est_slg,
            "xSLG_gap":   _gap(actual_slg,  est_slg),
            # Exit velo / barrels (filled in next layer)
            "EV":         0.0,
            "EV90":       0.0,
            "Brlp":       0.0,
            "HHp":        0.0,
            # Sprint speed (filled in next layer)
            "Spd":        0.0,
        }

    # ── Exit velo / barrel layer ──────────────────────────────────────────────
    for row in evdf:
        mlbam = _str_id(row, "player_id", "mlbam_id", "batter")
        if not mlbam:
            continue
        entry = batters.setdefault(mlbam, {
            "name": _player_name(row),
            "wOBA": 0.0, "xwOBA": 0.0, "xwOBA_gap": 0.0,
            "BA": 0.0,   "xBA": 0.0,   "xBA_gap": 0.0,
            "SLG": 0.0,  "xSLG": 0.0,  "xSLG_gap": 0.0,
            "Spd": 0.0,
        })
        entry["EV"]   = _c(row.get("avg_hit_speed",   row.get("exit_velocity_avg", 0)))
        entry["EV90"] = _c(row.get("ev90",            row.get("exit_velocity_90th", 0)))
        entry["Brlp"] = _c(row.get("brl_percent",     row.get("barrel_batted_rate", 0)))
        # Baseball Savant uses several column names for hard-hit rate across different
        # leaderboard endpoints.  Try them all; the statcast leaderboard (/leaderboard/statcast)
        # sometimes omits it while the custom leaderboard uses "hard_hit_percent".
        # If the column exists as a raw percentage (e.g. 49.0) convert to decimal (0.490)
        # to match FanGraphs Hardp format used as the fallback in model.py.
        _hhp_raw = (row.get("hard_hit_percent") or row.get("hard_hit_rate") or
                    row.get("p_hard_hit_percent") or row.get("hh_percent") or 0)
        _hhp = _c(_hhp_raw)
        # Values > 1 are raw percentages (e.g. 49.0 → 0.490); normalize to decimal.
        entry["HHp"] = round(_hhp / 100, 4) if _hhp > 1 else _hhp

    # ── Sprint speed layer ────────────────────────────────────────────────────
    # pybaseball sprint_speed uses 'player_id' and 'hp_to_1b' or 'sprint_speed'
    for row in spdf:
        mlbam = _str_id(row, "player_id", "mlbam_id")
        if not mlbam or mlbam not in batters:
            continue
        batters[mlbam]["Spd"] = _c(
            row.get("sprint_speed", row.get("hp_to_1b", 0))
        )

    return batters


def load_pitcher_data(season):
    """Merge pitcher expected stats + exit velo/barrels into one dict keyed by MLBAM ID."""
    print(f"  Fetching pitcher expected stats ({season})...")
    try:
        xdf = statcast_pitcher_expected_stats(season, minPA=25).to_dict(orient="records")
        print(f"    → {len(xdf)} rows")
    except Exception as e:
        print(f"    WARNING: pitcher expected stats failed: {e}")
        xdf = []

    print(f"  Fetching pitcher exit velo / barrels ({season})...")
    try:
        evdf = statcast_pitcher_exitvelo_barrels(season, minBBE=25).to_dict(orient="records")
        print(f"    → {len(evdf)} rows")
    except Exception as e:
        print(f"    WARNING: pitcher exit velo failed: {e}")
        evdf = []

    pitchers = {}

    # ── Expected stats layer ──────────────────────────────────────────────────
    for row in xdf:
        mlbam = _str_id(row, "player_id", "mlbam_id", "pitcher")
        if not mlbam:
            continue
        name = _player_name(row)
        actual_woba = _c(row.get("woba", 0))
        est_woba    = _c(row.get("est_woba", row.get("xwoba", 0)))
        actual_era  = _c(row.get("era", 0))
        est_era     = _c(row.get("est_era", row.get("xera", 0)))

        pitchers[mlbam] = {
            "name":      name,
            # xwOBA against: pitcher's contact quality allowed
            "wOBA_a":    actual_woba,
            "xwOBA_a":   est_woba,
            "xwOBA_gap": _gap(actual_woba, est_woba),  # positive = pitcher doing better than results
            # xERA: best expected ERA — ERA vs xERA gap is the buy/sell signal
            "ERA":       actual_era if actual_era > 0 else 0.0,
            "xERA":      est_era    if est_era    > 0 else 0.0,
            "xERA_gap":  _gap(actual_era, est_era) if actual_era > 0 and est_era > 0 else 0.0,
            # Barrels / hard hit (filled next layer)
            "Brlp_a":    0.0,
            "HHp_a":     0.0,
            "EV_a":      0.0,
        }

    # ── Exit velo / barrel layer ──────────────────────────────────────────────
    for row in evdf:
        mlbam = _str_id(row, "player_id", "mlbam_id", "pitcher")
        if not mlbam:
            continue
        entry = pitchers.setdefault(mlbam, {
            "name": _player_name(row),
            "wOBA_a": 0.0, "xwOBA_a": 0.0, "xwOBA_gap": 0.0,
            "ERA": 0.0,    "xERA": 0.0,    "xERA_gap": 0.0,
        })
        entry["EV_a"]   = _c(row.get("avg_hit_speed",    row.get("exit_velocity_avg", 0)))
        entry["Brlp_a"] = _c(row.get("brl_percent",      row.get("barrel_batted_rate", 0)))
        _hhp_a_raw = (row.get("hard_hit_percent") or row.get("hard_hit_rate") or
                      row.get("p_hard_hit_percent") or row.get("hh_percent") or 0)
        _hhp_a = _c(_hhp_a_raw)
        entry["HHp_a"] = round(_hhp_a / 100, 4) if _hhp_a > 1 else _hhp_a

    return pitchers

# ── Regression / breakout signal helpers ──────────────────────────────────────

XWOBA_THRESHOLD = 0.030   # |xwOBA - wOBA| beyond this = meaningful signal
XERA_THRESHOLD  = 1.00    # |xERA - ERA| beyond this = buy/sell signal

def classify_batter(entry):
    """Return a Statcast signal string for the morning briefing."""
    gap = entry.get("xwOBA_gap", 0.0)  # positive = xwOBA > wOBA = underperforming = buy-low
    if gap > XWOBA_THRESHOLD:
        return "BREAKOUT_CANDIDATE"
    if gap < -XWOBA_THRESHOLD:
        return "REGRESSION_RISK"
    return "NEUTRAL"

def classify_pitcher(entry):
    """Return a Statcast signal string for the morning briefing."""
    gap = entry.get("xERA_gap", 0.0)  # positive = xERA > ERA = pitcher overperforming = sell-high
    if gap > XERA_THRESHOLD:
        return "SELL_HIGH"     # ERA better than xERA — likely to regress up
    if gap < -XERA_THRESHOLD:
        return "BUY_LOW"       # ERA worse than xERA — likely to improve
    return "NEUTRAL"

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    force   = "--force" in sys.argv
    season_override = next(
        (int(sys.argv[i + 1]) for i, a in enumerate(sys.argv)
         if a == "--season" and i + 1 < len(sys.argv)),
        None,
    )
    season = season_override or SEASON

    print(f"\nBuilding Statcast cache for {season} season")
    print(f"Output: {CACHE_PATH}\n")

    # ── Token-optimization: skip rebuild if cache is fresh ────────────────────
    if not force and _cache_is_fresh(CACHE_PATH, CACHE_TTL_DAYS):
        age_hours = (time.time() - os.path.getmtime(CACHE_PATH)) / 3600
        print(f"  Cache is fresh ({age_hours:.1f}h old, TTL={CACHE_TTL_DAYS}d). Skipping rebuild.")
        print(f"  Use --force to rebuild anyway.\n")
        return

    print("Loading batter Statcast data...")
    batters = load_batter_data(season)

    print("\nLoading pitcher Statcast data...")
    pitchers = load_pitcher_data(season)

    if not batters and not pitchers:
        print("\n  ✗ All Statcast fetches failed — cache not updated.\n")
        return

    named_entries = sum(1 for e in batters.values() if e.get("name")) + \
                    sum(1 for e in pitchers.values() if e.get("name"))
    if named_entries == 0:
        print("\n  ✗ Statcast data contained no player names — cache not updated.\n")
        return

    # Attach signal classifications
    for entry in batters.values():
        entry["signal"] = classify_batter(entry)
    for entry in pitchers.values():
        entry["signal"] = classify_pitcher(entry)

    data = {
        "season":   season,
        "built_at": datetime.utcnow().isoformat() + "Z",
        "batters":  batters,
        "pitchers": pitchers,
    }

    with open(CACHE_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))  # compact — no extra whitespace

    size_kb = os.path.getsize(CACHE_PATH) / 1024
    b_breaks = sum(1 for e in batters.values()  if e.get("signal") == "BREAKOUT_CANDIDATE")
    b_regs   = sum(1 for e in batters.values()  if e.get("signal") == "REGRESSION_RISK")
    p_buys   = sum(1 for e in pitchers.values() if e.get("signal") == "BUY_LOW")
    p_sells  = sum(1 for e in pitchers.values() if e.get("signal") == "SELL_HIGH")

    print(f"\nSUCCESS")
    print(f"  {len(batters)} batters  |  {len(pitchers)} pitchers")
    print(f"  Batter signals  : {b_breaks} breakout candidates, {b_regs} regression risks")
    print(f"  Pitcher signals : {p_buys} buy-low, {p_sells} sell-high")
    print(f"  Cache size: {size_kb:.1f} KB")
    print(f"  Saved to: {CACHE_PATH}")
    print(f"  Next rebuild due: in {CACHE_TTL_DAYS} days (or use --force)\n")


if __name__ == "__main__":
    main()
