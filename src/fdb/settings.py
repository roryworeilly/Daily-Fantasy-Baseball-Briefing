"""
Machine-generated from fdbRV.py — see .build/generate_fdb_package.py.
"""
import os
import sys
import json
import html
from datetime import datetime

# ── Cache redirect ────────────────────────────────────────────────────────────
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_ROOT = os.path.dirname(_PACKAGE_DIR)
SCRIPT_DIR = os.path.dirname(_SRC_ROOT)
os.environ["HOME"] = SCRIPT_DIR

try:
    import requests_cache
    from datetime import timedelta
    requests_cache.install_cache(
        os.path.join(SCRIPT_DIR, "espn_cache"),
        backend="sqlite",
        # ESPN Fantasy API data changes any time a waiver claim, trade, or
        # roster move is processed.  A 10-minute TTL is effectively "always
        # fresh" for a daily morning briefing while still preventing duplicate
        # requests within a single run.  MLB stats endpoints (statsapi.mlb.com)
        # are also covered by this same TTL — their data is stable enough that
        # a 10-minute cache is no concern.
        expire_after=timedelta(minutes=10),
    )
    # Purge any permanent (never-expiring) entries that may have been written
    # before the TTL was established — these would otherwise serve stale roster
    # data indefinitely (e.g. after a waiver pickup or FA drop).
    try:
        import sqlite3, time as _time
        _cache_db = os.path.join(SCRIPT_DIR, "espn_cache.sqlite")
        if os.path.exists(_cache_db):
            _conn = sqlite3.connect(_cache_db)
            _conn.execute("DELETE FROM responses WHERE expires IS NULL")
            _conn.execute("DELETE FROM responses WHERE expires IS NOT NULL AND expires < ?",
                          (_time.time(),))
            _conn.commit()
            _conn.close()
    except Exception:
        pass
except ImportError:
    pass

from espn_api.baseball import League

try:
    from pybaseball import (
        batting_stats, pitching_stats,           # FanGraphs (primary — JSON API)
        batting_stats_bref, pitching_stats_bref, # Baseball Reference (fallback)
        bwar_bat, bwar_pitch,
    )
    PYBASEBALL_AVAILABLE = True
except ImportError:
    PYBASEBALL_AVAILABLE = False

# ── Credentials (loaded from .env — never hard-code here) ─────────────────────
# To update: double-click "Update ESPN Credentials.command" in the FB folder,
# or open .env in any text editor and paste fresh SWID / ESPN_S2 values.
# Grab fresh values from browser DevTools → Application → Cookies → fantasy.espn.com.

def _load_env_file(path):
    """Minimal .env parser — no external dependencies required."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _val = _line.partition("=")
            _key = _key.strip()
            _val = _val.strip()
            if _key and _key not in os.environ:  # don't override shell env vars
                os.environ[_key] = _val

_load_env_file(os.path.join(SCRIPT_DIR, ".env"))

LEAGUE_ID    = int(os.environ.get("LEAGUE_ID",    "1457877076"))
YEAR         = int(os.environ.get("YEAR",          "2026"))
SWID         = os.environ.get("ESPN_SWID",         "")
ESPN_S2      = os.environ.get("ESPN_S2",           "")
MY_TEAM_NAME = os.environ.get("MY_TEAM_NAME",      "The Undisputed")
N_TEAMS      = int(os.environ.get("N_TEAMS",       "14"))

# ── Scoring rules ─────────────────────────────────────────────────────────────
BATTING_SCORING = {
    "R": 1, "HR": 1, "TB": 1, "RBI": 1, "BB": 1,
    "SB": 1, "K": -1, "E": -1, "GWRBI": 2, "GSHR": 4, "CYC": 15,
}
PITCHING_SCORING = {
    "IP": 3, "H": -1, "ER": -2, "HR": -1, "BB": -1,
    "K": 1, "QS": 2, "CG": 5, "SO": 9, "NH": 10, "PG": 35,
    "W": 2, "L": -2, "SV": 6, "BS": -3, "HD": 5, "SVHD": 2,
}

# ── Starting slots per team (used for replacement-level calculation) ──────────
SLOTS_PER_TEAM = {
    "C":    1,
    "1B":   1,
    "2B":   1,
    "3B":   1,
    "SS":   1,
    "OF":   3,
    "UTIL": 1,
    "SP":   4,
    "RP":   3,
    "P":    7,
}

REPLACEMENT_BUFFER = 3

# Weekly IP cap — leagues with no limit can set this to 999
WEEKLY_IP_LIMIT = int(os.environ.get("WEEKLY_IP_LIMIT", "50"))

# ── Season Intelligence settings ─────────────────────────────────────────────
STASH_SCORE_THRESHOLD     = 50.0   # min healthy base score to flag as stash target
SEASON_INTEL_FA_THRESHOLD = 60.0   # min healthy base score for long-season FA watch
SEASON_TREND_MIN_GAMES    = 5      # minimum games in lookback window to compute trend
SEASON_TREND_LOOKBACK     = 45     # days to look back for current-season trend

# ── Market context (populated by build_market_context) ───────────────────────
MARKET = {
    "replacement_levels": {},
    "pool_above_repl":    {},
    # Role-split pitcher replacement levels (fix for mixed-pool drag on RPs)
    "sp_repl":            0.0,   # starters-only repl level  (GS ≥ 15 prior season)
    "rp_repl":            0.0,   # relievers-only repl level (GS <  10 prior season)
    "hold_depth":         0,     # # of RPs projecting above RP-repl × 1.15 threshold
    # Fallback repl: min non-zero positional level — used when a player's eligible
    # slots don't match any specific MARKET key (prevents "Replacement Lvl: 0.0")
    "fallback_repl":      0.0,
    "ready":              False,
}

# ── Weekly probable-start counts (populated by fetch_weekly_probable_starts) ──
WEEKLY_STARTS = {
    "starts":     {},   # mlbam_id (str) → probable-start count for the current week
    "loaded":     False,
    "week_start": None,
    "week_end":   None,
}

# ── Score scaling (populated by build_score_scaling) ─────────────────────────
SCALING = {
    # Pitcher sub-scale (pitchers scored against pitchers only)
    "p_base_min": 0.0, "p_base_max": 1.0,
    "p_fit_min":  0.0, "p_fit_max":  1.0,
    # Hitter sub-scale (hitters scored against hitters only)
    "h_base_min": 0.0, "h_base_max": 1.0,
    "h_fit_min":  0.0, "h_fit_max":  1.0,
    # Legacy unified scale (kept for backward compat)
    "base_min": 0.0, "base_max": 1.0,
    "fit_min":  0.0, "fit_max":  1.0,
    "ready":    False,
}

# ── Player reference database (populated by load_reference_db) ───────────────
REFERENCE_DB_PATH = os.path.join(SCRIPT_DIR, "player_reference_cache.json")
REFERENCE_DB = {"season": None, "hitters": {}, "pitchers": {}, "loaded": False, "source": "none"}

# ── Phase 3: Steamer/ZiPS consensus projection cache ─────────────────────────
# Built by tools/build_projection_cache.py — TTL 7 days.
# Keyed by normalized player name; contains consensus_pts (Steamer+ZiPS average)
# and key counting stats for display.  Falls back gracefully if cache not built.
PROJECTION_DB_PATH = os.path.join(SCRIPT_DIR, "projection_cache.json")
PROJECTION_DB = {
    "season":   None,
    "built_at": None,
    "hitters":  {},   # norm_name → {consensus_pts, steamer_pts, zips_pts, ...}
    "pitchers": {},   # norm_name → {consensus_pts, steamer_pts, zips_pts, ...}
    "loaded":   False,
}

# ── Phase 2: Statcast cache (populated by load_statcast_db) ──────────────────
# Built by tools/build_statcast_cache.py — TTL 7 days, keyed by MLBAM ID.
# Contains xwOBA, xBA, xSLG, xERA, exit velocity, barrel%, sprint speed.
# Regression/breakout signal pre-classified as BREAKOUT_CANDIDATE / REGRESSION_RISK / NEUTRAL
STATCAST_DB_PATH = os.path.join(SCRIPT_DIR, "statcast_cache.json")
STATCAST_DB = {
    "season":   None,
    "built_at": None,
    "batters":  {},   # mlbam_id (str) → statcast metrics dict
    "pitchers": {},   # mlbam_id (str) → statcast metrics dict
    "loaded":   False,
}

# Thresholds for regression / breakout signal classification
STATCAST_XWOBA_THRESHOLD = 0.030  # |xwOBA - wOBA| gap: meaningful signal
STATCAST_XERA_THRESHOLD  = 1.00   # |xERA - ERA|  gap: meaningful signal
