"""
Build / refresh player_reference_cache.json
────────────────────────────────────────────
Run once from the FB directory with the project venv:

    cd /Users/roryoreilly/Desktop/FB
    .venv/bin/python tools/build_reference_cache.py

Options:
    --force     Rebuild even if cache is fresh (< 7 days old)
    --season N  Override the target season (default: YEAR - 1)

Tries FanGraphs first (JSON API — reliable), falls back to
Baseball Reference HTML scraping if FanGraphs fails.

Phase 1 Advanced Metrics added (see Analytics_Roadmap.md):
  Hitters : wRC+, wOBA, ISO, BB%, K%, BABIP, LD%, GB%, FB%, Hard%, Barrel%
  Pitchers: FIP, xFIP, SIERA, SwStr%, GB%, LD%, FB%, K/9, BB/9, K-BB%, HR/FB%, LOB%

Token-optimization strategy:
  • Cache TTL = 7 days — avoids redundant FanGraphs fetches on every run
  • Floats rounded to 4 decimal places — reduces JSON size ~15% vs full precision
  • Only columns actually used by model.py are stored (no full-DataFrame dump)
"""

import os, sys, json, re, time
from datetime import datetime

# ── Cache TTL ─────────────────────────────────────────────────────────────────
CACHE_TTL_DAYS = 7  # rebuild if cache is older than this

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from fdb.utils import normalize_name, compact as _compact, get_metric, cache_is_fresh as _cache_is_fresh

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(SCRIPT_DIR, "player_reference_cache.json")
import datetime as _dt
YEAR   = int(os.environ.get("YEAR", str(_dt.datetime.now().year)))
SEASON = YEAR - 1


# ── pybaseball import ─────────────────────────────────────────────────────────

try:
    from pybaseball import (
        batting_stats, pitching_stats,
        batting_stats_bref, pitching_stats_bref,
        bwar_bat, bwar_pitch,
    )
except ImportError:
    sys.exit("ERROR: pybaseball not installed.  Run:  pip install pybaseball")

# ── FanGraphs loader ──────────────────────────────────────────────────────────

def load_from_fangraphs(season):
    print(f"  Fetching {season} batting stats from FanGraphs...")
    h_df = batting_stats(season, season, qual=0)
    print(f"    → {len(h_df)} rows,  columns: {list(h_df.columns[:12])}")

    print(f"  Fetching {season} pitching stats from FanGraphs...")
    p_df = pitching_stats(season, season, qual=0)
    print(f"    → {len(p_df)} rows,  columns: {list(p_df.columns[:12])}")

    hitters = {}
    for row in h_df.to_dict(orient="records"):
        name = normalize_name(row.get("Name", ""))
        if not name:
            continue
        h  = get_metric(row, "H")
        d  = get_metric(row, "2B")
        t  = get_metric(row, "3B")
        hr = get_metric(row, "HR")
        hitters[name] = {
            "display_name": row.get("Name", ""),
            # ── Counting stats (existing) ─────────────────────────────────────
            "PA":  _compact(get_metric(row, "PA"), 1),
            "H":   _compact(h, 1),
            "2B":  _compact(d, 1),
            "3B":  _compact(t, 1),
            "HR":  _compact(hr, 1),
            "R":   _compact(get_metric(row, "R"), 1),
            "RBI": _compact(get_metric(row, "RBI"), 1),
            "SB":  _compact(get_metric(row, "SB"), 1),
            "BB":  _compact(get_metric(row, "BB"), 1),
            "SO":  _compact(get_metric(row, "SO"), 1),
            "TB":  _compact(h + d + 2 * t + 3 * hr, 1),
            "OPS": _compact(get_metric(row, "OPS")),
            "WAR": _compact(get_metric(row, "WAR")),
            # ── Phase 1: FanGraphs advanced rate stats ────────────────────────
            # Slash / value
            "wRCp":  _compact(get_metric(row, "wRC+")),     # wRC+ (100 = avg)
            "wOBA":  _compact(get_metric(row, "wOBA")),     # weighted OBA
            "ISO":   _compact(get_metric(row, "ISO")),      # isolated power (SLG-AVG)
            # Plate discipline
            "BBp":   _compact(get_metric(row, "BB%")),      # walk rate
            "Kp":    _compact(get_metric(row, "K%")),       # strikeout rate
            # Batted ball / luck
            "BABIP": _compact(get_metric(row, "BABIP")),    # regression signal
            "LDp":   _compact(get_metric(row, "LD%")),      # line-drive rate
            "GBp":   _compact(get_metric(row, "GB%")),      # ground-ball rate
            "FBp":   _compact(get_metric(row, "FB%")),      # fly-ball rate
            "Hardp": _compact(get_metric(row, "Hard%")),    # hard-hit rate (FG)
            "Brlp":  _compact(get_metric(row, "Barrel%")),  # barrel rate (Statcast-via-FG)
            "Spd":   _compact(get_metric(row, "Spd")),      # speed score
        }

    pitchers = {}
    for row in p_df.to_dict(orient="records"):
        name = normalize_name(row.get("Name", ""))
        if not name:
            continue
        era  = get_metric(row, "ERA")
        whip = get_metric(row, "WHIP")
        fip  = get_metric(row, "FIP")
        xfip = get_metric(row, "xFIP")
        pitchers[name] = {
            "display_name": row.get("Name", ""),
            # ── Counting stats (existing) ─────────────────────────────────────
            "IP":   _compact(get_metric(row, "IP"), 1),
            "H":    _compact(get_metric(row, "H"), 1),
            "ER":   _compact(get_metric(row, "ER"), 1),
            "HR":   _compact(get_metric(row, "HR"), 1),
            "BB":   _compact(get_metric(row, "BB"), 1),
            "SO":   _compact(get_metric(row, "SO"), 1),
            "W":    _compact(get_metric(row, "W"), 1),
            "L":    _compact(get_metric(row, "L"), 1),
            "SV":   _compact(get_metric(row, "SV"), 1),
            "HD":   _compact(get_metric(row, "HLD", "HD"), 1),
            "BS":   _compact(get_metric(row, "BS"), 1),
            "QS":   _compact(get_metric(row, "QS"), 1),
            "GS":   _compact(get_metric(row, "GS"), 1),
            "ERA":  _compact(era  if era  > 0 else 99.0),
            "WHIP": _compact(whip if whip > 0 else 9.9),
            "WAR":  _compact(get_metric(row, "WAR")),
            # ── Phase 1: FanGraphs advanced ERA estimators ────────────────────
            "FIP":   _compact(fip  if fip  > 0 else 0.0),   # fielding-independent ERA
            "xFIP":  _compact(xfip if xfip > 0 else 0.0),  # xFIP (normalized HR/FB)
            "SIERA": _compact(get_metric(row, "SIERA")),    # best ERA predictor
            # Swing / stuff
            "SwStp": _compact(get_metric(row, "SwStr%")),   # swinging-strike rate
            "CSWp":  _compact(get_metric(row, "CSW%")),     # called + whiff rate
            # Batted ball profile
            "GBp":   _compact(get_metric(row, "GB%")),      # ground-ball rate
            "LDp":   _compact(get_metric(row, "LD%")),
            "FBp":   _compact(get_metric(row, "FB%")),
            # Component rates
            "K9":    _compact(get_metric(row, "K/9")),      # K per 9
            "BB9":   _compact(get_metric(row, "BB/9")),     # BB per 9
            "KBBp":  _compact(get_metric(row, "K-BB%")),    # best single ERA predictor
            # Regression signals
            "HRFBp": _compact(get_metric(row, "HR/FB")),    # HR per fly ball (mean-reverts)
            "LOBp":  _compact(get_metric(row, "LOB%")),     # strand rate (mean-reverts)
            "BABIPp":_compact(get_metric(row, "BABIP")),    # pitcher BABIP allowed
        }

    return hitters, pitchers

# ── Baseball Reference loader (fallback) ──────────────────────────────────────

def load_from_bref(season):
    print(f"  Fetching {season} batting stats from Baseball Reference...")
    hitters_df  = batting_stats_bref(season)
    print(f"    → {len(hitters_df)} rows")

    print(f"  Fetching {season} pitching stats from Baseball Reference...")
    pitchers_df = pitching_stats_bref(season)
    print(f"    → {len(pitchers_df)} rows")

    print("  Fetching bWAR data...")
    h_war_df = bwar_bat()
    p_war_df = bwar_pitch()
    h_war_df = h_war_df[h_war_df["year_ID"] == season]
    p_war_df = p_war_df[p_war_df["year_ID"] == season]
    print(f"    → {len(h_war_df)} hitter WAR rows, {len(p_war_df)} pitcher WAR rows")

    hitters = {}
    for row in hitters_df.to_dict(orient="records"):
        name = normalize_name(row.get("Name", ""))
        if not name:
            continue
        e = hitters.setdefault(name, {
            "display_name": row.get("Name", ""),
            "PA": 0.0, "H": 0.0, "2B": 0.0, "3B": 0.0, "HR": 0.0,
            "R": 0.0, "RBI": 0.0, "SB": 0.0, "BB": 0.0, "SO": 0.0,
            "TB": 0.0, "OPS": 0.0, "WAR": 0.0,
            # Advanced metrics — zero-filled so the renderer never KeyErrors
            # when FanGraphs is unavailable and BRef is the fallback source.
            "wRCp": 0.0, "wOBA": 0.0, "ISO": 0.0,
            "BBp": 0.0, "Kp": 0.0,
            "BABIP": 0.0, "LDp": 0.0, "GBp": 0.0, "FBp": 0.0,
            "Hardp": 0.0, "Brlp": 0.0, "Spd": 0.0,
        })
        e["PA"]  += get_metric(row, "PA")
        e["H"]   += get_metric(row, "H")
        e["2B"]  += get_metric(row, "2B")
        e["3B"]  += get_metric(row, "3B")
        e["HR"]  += get_metric(row, "HR")
        e["R"]   += get_metric(row, "R")
        e["RBI"] += get_metric(row, "RBI")
        e["SB"]  += get_metric(row, "SB")
        e["BB"]  += get_metric(row, "BB")
        e["SO"]  += get_metric(row, "SO", "K")
        e["TB"]  += get_metric(row, "TB")
        e["OPS"]  = max(e["OPS"], get_metric(row, "OPS"))

    for row in h_war_df.to_dict(orient="records"):
        name = normalize_name(row.get("name_common", ""))
        if name in hitters:
            hitters[name]["WAR"] += get_metric(row, "WAR")

    pitchers = {}
    for row in pitchers_df.to_dict(orient="records"):
        name = normalize_name(row.get("Name", ""))
        if not name:
            continue
        e = pitchers.setdefault(name, {
            "display_name": row.get("Name", ""),
            "IP": 0.0, "H": 0.0, "ER": 0.0, "HR": 0.0, "BB": 0.0,
            "SO": 0.0, "W": 0.0, "L": 0.0, "SV": 0.0, "HD": 0.0,
            "BS": 0.0, "QS": 0.0, "GS": 0.0, "ERA": 99.0, "WHIP": 9.9,
            "WAR": 0.0,
            # Advanced metrics — zero-filled so the renderer never KeyErrors
            # when FanGraphs is unavailable and BRef is the fallback source.
            "FIP": 0.0, "xFIP": 0.0, "SIERA": 0.0,
            "SwStp": 0.0, "CSWp": 0.0,
            "K9": 0.0, "BB9": 0.0, "KBBp": 0.0,
            "GBp": 0.0, "FBp": 0.0, "LDp": 0.0,
            "HRFBp": 0.0, "LOBp": 0.0, "BABIPp": 0.0,
        })
        e["IP"]  += get_metric(row, "IP")
        e["H"]   += get_metric(row, "H")
        e["ER"]  += get_metric(row, "ER")
        e["HR"]  += get_metric(row, "HR")
        e["BB"]  += get_metric(row, "BB")
        e["SO"]  += get_metric(row, "SO", "K")
        e["W"]   += get_metric(row, "W")
        e["L"]   += get_metric(row, "L")
        e["SV"]  += get_metric(row, "SV")
        e["HD"]  += get_metric(row, "HLD", "HD")
        e["QS"]  += get_metric(row, "QS")
        e["GS"]  += get_metric(row, "GS")
        era  = get_metric(row, "ERA")
        whip = get_metric(row, "WHIP")
        if era  > 0: e["ERA"]  = min(e["ERA"],  era)
        if whip > 0: e["WHIP"] = min(e["WHIP"], whip)

    for row in p_war_df.to_dict(orient="records"):
        name = normalize_name(row.get("name_common", ""))
        if name in pitchers:
            pitchers[name]["WAR"] += get_metric(row, "WAR")

    return hitters, pitchers

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    force   = "--force" in sys.argv
    season_override = next(
        (int(sys.argv[i + 1]) for i, a in enumerate(sys.argv) if a == "--season" and i + 1 < len(sys.argv)),
        None,
    )
    season = season_override or SEASON

    print(f"\nBuilding reference cache for {season} season")
    print(f"Output: {CACHE_PATH}\n")

    # ── Token-optimization: skip rebuild if cache is fresh ────────────────────
    if not force and _cache_is_fresh(CACHE_PATH, CACHE_TTL_DAYS):
        age_hours = (time.time() - os.path.getmtime(CACHE_PATH)) / 3600
        print(f"  Cache is fresh ({age_hours:.1f}h old, TTL={CACHE_TTL_DAYS}d). Skipping rebuild.")
        print(f"  Use --force to rebuild anyway.\n")
        return

    hitters = pitchers = None
    source  = None

    # Try FanGraphs first
    try:
        hitters, pitchers = load_from_fangraphs(season)
        source = "fangraphs"
    except Exception as e:
        print(f"\n  FanGraphs failed: {type(e).__name__}: {e}")
        print("  Falling back to Baseball Reference...\n")
        try:
            hitters, pitchers = load_from_bref(season)
            source = "pybaseball"
        except Exception as e2:
            print(f"\n  Baseball Reference also failed: {type(e2).__name__}: {e2}")
            sys.exit(1)

    data = {
        "season":    season,
        "built_at":  datetime.utcnow().isoformat() + "Z",
        "hitters":   hitters,
        "pitchers":  pitchers,
        "loaded":    True,
        "source":    source,
    }

    with open(CACHE_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))  # compact JSON — no extra whitespace

    size_kb = os.path.getsize(CACHE_PATH) / 1024
    print(f"\nSUCCESS ({source})")
    print(f"  {len(hitters)} hitters  |  {len(pitchers)} pitchers")
    print(f"  Cache size: {size_kb:.1f} KB")
    print(f"  Saved to: {CACHE_PATH}")
    print(f"  Next rebuild due: in {CACHE_TTL_DAYS} days (or use --force)\n")
    print("Run fdbRV.py — it will load from cache instantly.\n")

if __name__ == "__main__":
    main()
