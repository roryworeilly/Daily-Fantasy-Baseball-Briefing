"""
Build / refresh projection_cache.json  (Phase 3 — Analytics Roadmap)
──────────────────────────────────────────────────────────────────────
Run from the FB directory with the project venv:

    .venv/bin/python tools/build_projection_cache.py

Options:
    --force       Rebuild even if cache is fresh (< 7 days old)
    --season N    Override projection target season (default: current year)

What this fetches from FanGraphs (free CSV API):
  Batting (Steamer + ZiPS):
    PA, AB, R, HR, RBI, SB, BB, SO, AVG, OBP, SLG, H, 2B, 3B, TB
  Pitching (Steamer + ZiPS):
    IP, W, L, SV, HD, ERA, WHIP, SO, BB, H, HR, GS, QS (estimated)

Methodology:
  - Fetches both Steamer and ZiPS projections
  - Averages them (consensus beats any single system — per research)
  - Computes expected fantasy points using YOUR league's scoring rules
  - Stores as player-name-keyed JSON for fast lookup in model.py

Integration:
  - model.py load_projection_db() reads this cache on startup
  - get_projected_pts() uses consensus projection pts as the primary
    fallback when ESPN's own projection is unavailable or very low

Cache location: FB/projection_cache.json
Cache TTL: 7 days (projections update weekly early in season)
"""

import json
import importlib
import os
import sys
import time
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(SCRIPT_DIR, "projection_cache.json")
YEAR = int(os.environ.get("YEAR", "2026"))
CACHE_TTL_DAYS = 7

# ── Scoring rules — import from settings.py (single source of truth) ──────────
# Add src/ to path so we can import fdb.settings
_SRC = os.path.join(SCRIPT_DIR, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
try:
    from fdb.settings import BATTING_SCORING, PITCHING_SCORING
except ImportError:
    # Fallback if import fails (e.g. running outside the project venv)
    BATTING_SCORING = {
        "R": 1, "HR": 1, "TB": 1, "RBI": 1, "BB": 1,
        "SB": 1, "K": -1, "E": -1, "GWRBI": 2, "GSHR": 4, "CYC": 15,
    }
    PITCHING_SCORING = {
        "IP": 3, "H": -1, "ER": -2, "HR": -1, "BB": -1,
        "K": 1, "QS": 2, "CG": 5, "SO": 9, "NH": 10, "PG": 35,
        "W": 2, "L": -2, "SV": 6, "BS": -3, "HD": 5, "SVHD": 2,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

_utils = importlib.import_module("fdb.utils")
normalize_name = _utils.normalize_name
_c = _utils.compact
_cache_is_fresh = _utils.cache_is_fresh


def _fetch_fg_projection_json(proj_type: str, stats: str) -> list[dict]:
    """
    Fetch a FanGraphs projection via the JSON API (replaces the old CSV endpoint).

    proj_type: 'steamer' | 'zips'
    stats:     'bat' | 'pit'

    FanGraphs JSON API (public, no auth required as of 2024+):
      https://www.fangraphs.com/api/projections?type={proj_type}&stats={stats}
        &pos=all&team=0&players=0&lg=all

    Returns list of dicts. Player name key is 'PlayerName'.
    Falls back to [] on any error.
    """
    try:
        import certifi
        import requests

        url = (
            "https://www.fangraphs.com/api/projections"
            f"?type={proj_type}&stats={stats}&pos=all&team=0&players=0&lg=all"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.fangraphs.com/projections",
        }
        resp = requests.get(url, headers=headers, timeout=30, verify=certifi.where())
        resp.raise_for_status()

        # Confirm we got JSON and not an HTML redirect/login page
        ct = resp.headers.get("Content-Type", "")
        raw = resp.text.strip()
        if raw.startswith("<!") or "text/html" in ct:
            print(f"    [{proj_type}/{stats}] Received HTML instead of JSON — skipping")
            return []

        data = resp.json()
        # FanGraphs sometimes wraps in {"data": [...]}
        if isinstance(data, dict):
            data = data.get("data", data.get("rows", []))

        rows = list(data) if data else []
        # Normalise player-name key: JSON uses "PlayerName", CSV used "Name"
        for row in rows:
            if "PlayerName" in row and "Name" not in row:
                row["Name"] = row["PlayerName"]

        print(f"    [{proj_type}/{stats}] {len(rows)} players fetched")
        return rows

    except Exception as exc:
        print(f"    [{proj_type}/{stats}] fetch failed: {type(exc).__name__}: {exc}")
        return []


def _hitter_pts_from_proj(row: dict) -> float:
    """Compute fantasy points from a FanGraphs projection row (hitter)."""
    def f(k, *alt):
        for key in (k,) + alt:
            try:
                v = float(row.get(key, 0) or 0)
                if v == v:  # NaN guard
                    return v
            except Exception:
                pass
        return 0.0

    r = f("R")
    hr = f("HR")
    rbi = f("RBI")
    sb = f("SB")
    bb = f("BB")
    so = f("SO", "K")
    h = f("H")
    d = f("2B")
    t = f("3B")
    pa = f("PA")
    # TB = H + 2B + 2×3B + 3×HR  (singles = 1, 2B = 2, 3B = 3, HR = 4)
    tb = f("TB") or (h + d + 2 * t + 3 * hr)

    score = BATTING_SCORING["R"] * r
    score += BATTING_SCORING["HR"] * hr
    score += BATTING_SCORING["TB"] * tb
    score += BATTING_SCORING["RBI"] * rbi
    score += BATTING_SCORING["BB"] * bb
    score += BATTING_SCORING["SB"] * sb
    score += BATTING_SCORING["K"] * (-so)  # K = -1 pts
    # GWRBI estimate: ~2% of RBI
    score += BATTING_SCORING["GWRBI"] * (rbi * 0.02)
    # Grand slam estimate: ~0.3% of PA
    score += BATTING_SCORING["GSHR"] * (pa * 0.003)
    return max(0.0, score)


def _pitcher_pts_from_proj(row: dict) -> float:
    """Compute fantasy points from a FanGraphs projection row (pitcher)."""
    def f(k, *alt):
        for key in (k,) + alt:
            try:
                v = float(row.get(key, 0) or 0)
                if v == v:
                    return v
            except Exception:
                pass
        return 0.0

    ip = f("IP")
    h = f("H")
    er = f("ER")
    hr = f("HR")
    bb = f("BB")
    so = f("SO", "K")
    w = f("W")
    losses = f("L")
    sv = f("SV")
    hd = f("HLD", "HD")
    gs = f("GS")
    qs = f("QS") or (gs * 0.55)  # estimate when not in projection data
    bs = f("BS")

    score = PITCHING_SCORING["IP"] * ip
    score += PITCHING_SCORING["H"] * h
    score += PITCHING_SCORING["ER"] * er
    score += PITCHING_SCORING["HR"] * hr
    score += PITCHING_SCORING["BB"] * bb
    score += PITCHING_SCORING["K"] * so
    score += PITCHING_SCORING["QS"] * qs
    score += PITCHING_SCORING["W"] * w
    score += PITCHING_SCORING["L"] * losses
    score += PITCHING_SCORING["SV"] * sv
    score += PITCHING_SCORING["BS"] * bs
    score += PITCHING_SCORING["HD"] * hd
    score += PITCHING_SCORING["SVHD"] * (sv + hd)
    score += PITCHING_SCORING["CG"] * (gs * 0.01)
    score += PITCHING_SCORING["SO"] * (gs * 0.001)
    return max(0.0, score)


def _build_hitter_entry(name: str, steamer_row: dict | None, zips_row: dict | None) -> dict:
    """Merge Steamer + ZiPS into a consensus projection dict for a hitter."""
    def _avg(*vals):
        valid = [v for v in vals if v and v > 0]
        return round(sum(valid) / len(valid), 4) if valid else 0.0

    def f(row, k, *alt):
        if not row:
            return 0.0
        for key in (k,) + alt:
            try:
                v = float(row.get(key, 0) or 0)
                if v == v:
                    return v
            except Exception:
                pass
        return 0.0

    # Compute pts for each system
    s_pts = _hitter_pts_from_proj(steamer_row) if steamer_row else 0.0
    z_pts = _hitter_pts_from_proj(zips_row) if zips_row else 0.0
    consensus_pts = _avg(s_pts, z_pts)

    return {
        "name": name,
        "steamer_pts": _c(s_pts, 1),
        "zips_pts": _c(z_pts, 1),
        "consensus_pts": _c(consensus_pts, 1),
        # Key counting stats (averaged for display)
        "PA": _c(_avg(f(steamer_row, "PA"), f(zips_row, "PA")), 1),
        "HR": _c(_avg(f(steamer_row, "HR"), f(zips_row, "HR")), 1),
        "R": _c(_avg(f(steamer_row, "R"), f(zips_row, "R")), 1),
        "RBI": _c(_avg(f(steamer_row, "RBI"), f(zips_row, "RBI")), 1),
        "SB": _c(_avg(f(steamer_row, "SB"), f(zips_row, "SB")), 1),
        "AVG": _c(_avg(f(steamer_row, "AVG"), f(zips_row, "AVG"))),
        "OPS": _c(_avg(f(steamer_row, "OPS"), f(zips_row, "OPS"))),
    }


def _build_pitcher_entry(name: str, steamer_row: dict | None, zips_row: dict | None) -> dict:
    """Merge Steamer + ZiPS into a consensus projection dict for a pitcher."""
    def _avg(*vals):
        valid = [v for v in vals if v and v > 0]
        return round(sum(valid) / len(valid), 4) if valid else 0.0

    def f(row, k, *alt):
        if not row:
            return 0.0
        for key in (k,) + alt:
            try:
                v = float(row.get(key, 0) or 0)
                if v == v:
                    return v
            except Exception:
                pass
        return 0.0

    s_pts = _pitcher_pts_from_proj(steamer_row) if steamer_row else 0.0
    z_pts = _pitcher_pts_from_proj(zips_row) if zips_row else 0.0
    consensus_pts = _avg(s_pts, z_pts)

    return {
        "name": name,
        "steamer_pts": _c(s_pts, 1),
        "zips_pts": _c(z_pts, 1),
        "consensus_pts": _c(consensus_pts, 1),
        # Key counting stats (averaged for display)
        "IP": _c(_avg(f(steamer_row, "IP"), f(zips_row, "IP")), 1),
        "W": _c(_avg(f(steamer_row, "W"), f(zips_row, "W")), 1),
        "SV": _c(_avg(f(steamer_row, "SV"), f(zips_row, "SV")), 1),
        "HD": _c(_avg(f(steamer_row, "HLD", "HD"), f(zips_row, "HLD", "HD")), 1),
        "ERA": _c(_avg(f(steamer_row, "ERA"), f(zips_row, "ERA"))),
        "WHIP": _c(_avg(f(steamer_row, "WHIP"), f(zips_row, "WHIP"))),
        "SO": _c(_avg(f(steamer_row, "SO", "K"), f(zips_row, "SO", "K")), 1),
        "GS": _c(_avg(f(steamer_row, "GS"), f(zips_row, "GS")), 1),
    }


def build_projection_cache(force: bool = False, season: int = YEAR) -> dict:
    """Fetch Steamer + ZiPS projections and return the merged cache dict."""

    print(f"\n{'=' * 60}")
    print("  Fantasy Baseball Projection Cache Builder")
    print(f"  Target season: {season}")
    print(f"  Output: {CACHE_PATH}")
    print(f"{'=' * 60}\n")

    if not force and _cache_is_fresh(CACHE_PATH):
        age_h = (time.time() - os.path.getmtime(CACHE_PATH)) / 3600
        print(f"  Cache is fresh ({age_h:.0f}h old). Use --force to rebuild.")
        with open(CACHE_PATH) as _f:
            return json.load(_f)

    # ── Step 1: Fetch all four projection tables ───────────────────────────────
    print("Fetching Steamer batting projections...")
    st_bat = _fetch_fg_projection_json("steamer", "bat")

    print("Fetching Steamer pitching projections...")
    st_pit = _fetch_fg_projection_json("steamer", "pit")

    print("Fetching ZiPS batting projections...")
    zp_bat = _fetch_fg_projection_json("zips", "bat")

    print("Fetching ZiPS pitching projections...")
    zp_pit = _fetch_fg_projection_json("zips", "pit")

    # If all fetches failed, abort rather than writing an empty cache
    if not st_bat and not zp_bat and not st_pit and not zp_pit:
        print("\n  ✗ All projection fetches failed — cache not updated.")
        print("  Check your internet connection and try again.")
        return {}

    # ── Step 2: Index by normalized name ──────────────────────────────────────
    def _index(rows, name_key="Name"):
        d = {}
        for r in rows:
            nm = normalize_name(r.get(name_key, r.get("name", "")))
            if nm:
                d[nm] = r
        return d

    st_bat_idx = _index(st_bat)
    st_pit_idx = _index(st_pit)
    zp_bat_idx = _index(zp_bat)
    zp_pit_idx = _index(zp_pit)

    # ── Step 3: Merge into consensus ──────────────────────────────────────────
    all_hitter_names = set(st_bat_idx) | set(zp_bat_idx)
    all_pitcher_names = set(st_pit_idx) | set(zp_pit_idx)

    hitters = {}
    pitchers = {}

    for nm in all_hitter_names:
        sr = st_bat_idx.get(nm)
        zr = zp_bat_idx.get(nm)
        entry = _build_hitter_entry(nm, sr, zr)
        if entry["consensus_pts"] > 0 or entry["PA"] > 0:
            hitters[nm] = entry

    for nm in all_pitcher_names:
        sr = st_pit_idx.get(nm)
        zr = zp_pit_idx.get(nm)
        entry = _build_pitcher_entry(nm, sr, zr)
        if entry["consensus_pts"] > 0 or entry["IP"] > 0:
            pitchers[nm] = entry

    # ── Step 4: Write cache ───────────────────────────────────────────────────
    cache = {
        "season": season,
        "built_at": datetime.utcnow().isoformat() + "Z",
        "sources": {
            "steamer_bat": len(st_bat),
            "steamer_pit": len(st_pit),
            "zips_bat": len(zp_bat),
            "zips_pit": len(zp_pit),
        },
        "hitters": hitters,
        "pitchers": pitchers,
    }

    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, separators=(",", ":"))

    print("\n  ✓ Projection cache written:")
    print(f"    {len(hitters)} hitters · {len(pitchers)} pitchers")
    print(f"    Steamer: {len(st_bat)} bat / {len(st_pit)} pit")
    print(f"    ZiPS:    {len(zp_bat)} bat / {len(zp_pit)} pit")
    print(f"    Path:    {CACHE_PATH}")

    return cache


if __name__ == "__main__":
    force_rebuild = "--force" in sys.argv
    debug_mode = "--debug" in sys.argv
    season_override = YEAR
    for i, arg in enumerate(sys.argv):
        if arg == "--season" and i + 1 < len(sys.argv):
            try:
                season_override = int(sys.argv[i + 1])
            except ValueError:
                pass

    if debug_mode:
        # Quick raw-response check — prints the first 500 chars so you can see
        # whether you're getting JSON or HTML before running the full build.
        import certifi
        import requests

        for pt, st in [("steamer", "bat"), ("steamer", "pit"), ("zips", "bat")]:
            url = (
                f"https://www.fangraphs.com/api/projections"
                f"?type={pt}&stats={st}&pos=all&team=0&players=0&lg=all"
            )
            try:
                r = requests.get(
                    url,
                    timeout=20,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                        "Referer": "https://www.fangraphs.com/projections",
                    },
                    verify=certifi.where(),
                )
                print(f"\n[{pt}/{st}] status={r.status_code}  CT={r.headers.get('Content-Type', '')}")
                print(r.text[:500])
            except Exception as e:
                print(f"[{pt}/{st}] error: {e}")
        sys.exit(0)

    build_projection_cache(force=force_rebuild, season=season_override)
