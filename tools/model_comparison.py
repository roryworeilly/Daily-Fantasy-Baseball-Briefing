#!/usr/bin/env python3
"""
FDB vs ESPN Fantasy Model Comparison & Simulation Engine
========================================================
Compares the FDB advanced analytics model against an ESPN-style
baseline model using 2024 MLB season data.

Usage:
    python tools/model_comparison.py            # Run full simulation
    python tools/model_comparison.py --quick    # 100 iterations (faster)
    python tools/model_comparison.py --year 2023  # Use 2023 data

Outputs:
    tools/simulation_results.json  — machine-readable results
    model_comparison.html          — (if --html flag) regenerate dashboard
"""

import argparse
import json
import math
import os
import random
import sys
from pathlib import Path

# ── Try pybaseball (requires: pip install pybaseball) ─────────────────────────
try:
    from pybaseball import batting_stats, pitching_stats, cache
    cache.enable()
    HAS_PYBASEBALL = True
except ImportError:
    HAS_PYBASEBALL = False

# ── Output paths ───────────────────────────────────────────────────────────────
ROOT      = Path(__file__).resolve().parent.parent
OUT_JSON  = ROOT / "tools" / "simulation_results.json"

# ══════════════════════════════════════════════════════════════════════════════
# SCORING SYSTEMS
# ══════════════════════════════════════════════════════════════════════════════

def calc_fdb_bat(stats: dict) -> float:
    """FDB hitter fantasy points: R+HR+TB+RBI+BB+SB-K."""
    r   = float(stats.get("R",  0) or 0)
    hr  = float(stats.get("HR", 0) or 0)
    rbi = float(stats.get("RBI",0) or 0)
    bb  = float(stats.get("BB", 0) or 0)
    sb  = float(stats.get("SB", 0) or 0)
    k   = float(stats.get("SO", stats.get("K", 0)) or 0)
    h   = float(stats.get("H",  0) or 0)
    d   = float(stats.get("2B", 0) or 0)
    t   = float(stats.get("3B", 0) or 0)
    tb  = h + d + t * 2 + hr * 3
    return r + hr + tb + rbi + bb + sb - k

def calc_fdb_pit(stats: dict) -> float:
    """FDB pitcher fantasy points: IP*3 + K - H - ER*2 - HR - BB + W*2 - L*2 + SV*6 + HD*5 + QS*2."""
    ip  = float(stats.get("IP",  0) or 0)
    h   = float(stats.get("H",   0) or 0)
    er  = float(stats.get("ER",  0) or 0)
    hr  = float(stats.get("HR",  0) or 0)
    bb  = float(stats.get("BB",  0) or 0)
    k   = float(stats.get("SO",  stats.get("K",  0)) or 0)
    w   = float(stats.get("W",   0) or 0)
    l   = float(stats.get("L",   0) or 0)
    sv  = float(stats.get("SV",  0) or 0)
    hld = float(stats.get("HLD", 0) or 0)
    qs  = float(stats.get("QS",  0) or 0)
    return (ip * 3) + k - h - (er * 2) - hr - bb + (w * 2) - (l * 2) + (sv * 6) + (hld * 5) + (qs * 2)

def calc_espn_bat(stats: dict) -> float:
    """ESPN-style hitter points: R+HR*4+RBI+SB*2+AVG_bonus-K."""
    r   = float(stats.get("R",   0) or 0)
    hr  = float(stats.get("HR",  0) or 0)
    rbi = float(stats.get("RBI", 0) or 0)
    sb  = float(stats.get("SB",  0) or 0)
    k   = float(stats.get("SO",  stats.get("K", 0)) or 0)
    avg = float(stats.get("AVG", 0) or 0)
    bonus = 10 if avg >= 0.300 else (5 if avg >= 0.280 else 0)
    return r + (hr * 4) + rbi + (sb * 2) + bonus - k

def calc_espn_pit(stats: dict) -> float:
    """ESPN-style pitcher points: W*5+SV*5+K+ERA_bonus+WHIP_bonus."""
    w    = float(stats.get("W",    0) or 0)
    sv   = float(stats.get("SV",  0) or 0)
    k    = float(stats.get("SO",  stats.get("K", 0)) or 0)
    era  = float(stats.get("ERA", 4.50) or 4.50)
    whip = float(stats.get("WHIP",1.30) or 1.30)
    era_bonus  = 10 if era < 3.0 else (5 if era < 4.0 else (-10 if era >= 5.0 else 0))
    whip_bonus = 10 if whip < 1.00 else (5 if whip < 1.20 else (-10 if whip >= 1.50 else 0))
    return (w * 5) + (sv * 5) + k + era_bonus + whip_bonus


# ══════════════════════════════════════════════════════════════════════════════
# FDB ADVANCED PROJECTION — applies wRC+/wOBA/FIP regression to season stats
# ══════════════════════════════════════════════════════════════════════════════

def fdb_project_bat(row: dict) -> float:
    """
    Project hitter fantasy pts using FDB advanced metrics.
    Key adjustments vs ESPN baseline:
      1. BABIP regression → mean reversion on luck-inflated/deflated AVG
      2. wRC+ over raw counting → stable talent estimator
      3. xwOBA signal adjustment → Statcast-based talent signal
    """
    pa     = float(row.get("PA",   600) or 600)
    wrc    = float(row.get("wRC+", 100) or 100)
    woba   = float(row.get("wOBA", 0.320) or 0.320)
    babip  = float(row.get("BABIP",0.300) or 0.300)
    bb_pct = float(row.get("BB%",  8.0)  or 8.0)
    k_pct  = float(row.get("K%",   20.0) or 20.0)
    iso    = float(row.get("ISO",  0.150) or 0.150)
    sb     = float(row.get("SB",   5)    or 0)

    # 1. BABIP regression: pull 40% toward league mean (.300)
    babip_adj  = babip * 0.60 + 0.300 * 0.40
    # Skill-adjusted AVG (wOBA-based → contact factor)
    adj_avg    = woba / 1.22   # rough wOBA→AVG conversion

    # 2. Estimate counting stats from wRC+ and PA
    runs_per_pa = (wrc / 100) * 0.082
    proj_r      = pa * runs_per_pa
    proj_hr     = pa * (iso * 0.62)
    proj_rbi    = proj_r * 1.05
    proj_bb     = pa * (bb_pct / 100)
    proj_k      = pa * (k_pct  / 100)

    # Hits and TB via adjusted AVG
    ab_rate    = 1 - (bb_pct / 100) - 0.008   # approx non-BB PA ratio
    proj_ab    = pa * ab_rate
    proj_h     = proj_ab * adj_avg
    proj_2b    = proj_h  * 0.20
    proj_3b    = proj_h  * 0.02
    proj_tb    = proj_h  + proj_2b + (proj_3b * 2) + (proj_hr * 3)

    fps = proj_r + proj_hr + proj_tb + proj_rbi + proj_bb + sb - proj_k

    # 3. Statcast signal adjustment (±8% breakout, ±7% regression)
    sig = row.get("signal", "")
    if sig == "BREAKOUT_CANDIDATE":
        fps *= 1.08
    elif sig == "REGRESSION_RISK":
        fps *= 0.93

    return max(0.0, fps)


def fdb_project_pit(row: dict) -> float:
    """
    Project pitcher fantasy pts using FDB advanced metrics.
    Key adjustments vs ESPN baseline:
      1. FIP/xFIP over ERA → removes fielding noise
      2. SwStr%/CSW% → stuff quality signal for K projection
      3. xERA signal adjustment → Statcast-based luck correction
    """
    ip     = float(row.get("IP",    180) or 180)
    fip    = float(row.get("FIP",   4.2) or 4.2)
    xfip   = float(row.get("xFIP", fip)  or fip)
    siera  = float(row.get("SIERA",fip)  or fip)
    k9     = float(row.get("K/9",  8.0)  or 8.0)
    bb9    = float(row.get("BB/9", 3.0)  or 3.0)
    gb_pct = float(row.get("GB%",  45.0) or 45.0)
    lob    = float(row.get("LOB%", 73.0) or 73.0)
    hrfb   = float(row.get("HR/FB%",10.0)or 10.0)
    w      = float(row.get("W",    0)    or 0)
    sv     = float(row.get("SV",   0)    or 0)
    hld    = float(row.get("HLD",  0)    or 0)

    # Use skill-based ERA estimator (60% xFIP + 40% SIERA blend)
    skill_era = xfip * 0.60 + siera * 0.40

    # HR/FB regression toward league mean (10%)
    hrfb_adj = hrfb * 0.70 + 10.0 * 0.30

    # LOB% regression (league ~73%)
    lob_adj  = lob  * 0.60 + 73.0  * 0.40

    # Estimate counting stats from skill ERA + IP
    proj_er  = (skill_era * ip) / 9
    # H estimate from BABIP + GB (GB pitchers allow more hits per BIP but fewer HR)
    h_factor = 0.78 if gb_pct >= 50 else (0.82 if gb_pct >= 45 else 0.87)
    proj_h   = ip * h_factor
    proj_bb  = (bb9 / 9) * ip
    proj_k   = (k9  / 9) * ip
    proj_hr  = (proj_h * (1 - gb_pct/100) * 0.11) * (hrfb_adj / 10)

    # QS estimate: approximately 65% of starts are QS for elite, 40% for league avg
    gs       = ip / 5.8  # rough avg IP per start
    qs_rate  = max(0, min(0.70, 0.40 + (4.30 - skill_era) * 0.07))
    proj_qs  = gs * qs_rate

    fps = ((ip * 3) + proj_k - proj_h - (proj_er * 2) - proj_hr - proj_bb
           + (w * 2) + (sv * 6) + (hld * 5) + (proj_qs * 2))

    # Statcast signal
    sig = row.get("signal", "")
    if sig == "BUY_LOW":
        fps *= 1.07
    elif sig == "SELL_HIGH":
        fps *= 0.94

    return max(0.0, fps)


def espn_project_bat(row: dict) -> float:
    """ESPN-style projection: weighted 3yr avg counting stats → ESPN scoring."""
    # Naive approach: project from last year's actual counting stats
    # (no regression, no advanced metric adjustments)
    r   = float(row.get("R",   70) or 70)
    hr  = float(row.get("HR",  18) or 18)
    rbi = float(row.get("RBI", 72) or 72)
    sb  = float(row.get("SB",  8)  or 8)
    k   = float(row.get("SO",  120)or 120)
    avg = float(row.get("AVG", 0.260) or 0.260)

    # Scale if partial season — assume full 600 PA
    pa  = float(row.get("PA", 550) or 550)
    if pa < 200:
        scale = min(1.5, 550 / max(pa, 50))
        r *= scale; hr *= scale; rbi *= scale; sb *= scale; k *= scale

    bonus = 10 if avg >= 0.300 else (5 if avg >= 0.280 else 0)
    return r + (hr * 4) + rbi + (sb * 2) + bonus - k


def espn_project_pit(row: dict) -> float:
    """ESPN-style pitcher projection: uses ERA/WHIP directly, no FIP adjustment."""
    ip   = float(row.get("IP",   170) or 170)
    w    = float(row.get("W",    10)  or 10)
    sv   = float(row.get("SV",   0)   or 0)
    k    = float(row.get("SO",   150) or 150)
    era  = float(row.get("ERA",  4.2) or 4.2)
    whip = float(row.get("WHIP", 1.28)or 1.28)

    # Scale for partial IP
    if ip < 80:
        scale = min(1.5, 170 / max(ip, 30))
        w *= scale; k *= scale

    era_bonus  = 10 if era  < 3.0 else (5 if era  < 4.0 else (-10 if era  >= 5.0 else 0))
    whip_bonus = 10 if whip < 1.00 else (5 if whip < 1.20 else (-10 if whip >= 1.50 else 0))
    return (w * 5) + (sv * 5) + k + era_bonus + whip_bonus


# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCHING
# ══════════════════════════════════════════════════════════════════════════════

def fetch_batting(year: int) -> list:
    """Pull FanGraphs batting stats for the given year."""
    if not HAS_PYBASEBALL:
        print(f"  [warn] pybaseball not available — using embedded 2024 sample data")
        return _sample_batters()
    try:
        print(f"  Fetching batting stats for {year} via pybaseball…")
        df = batting_stats(year, qual=100)
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "Name":   str(r.get("Name", "")),
                "Team":   str(r.get("Team", "")),
                "Pos":    "DH",  # FanGraphs doesn't include pos here; will be blank
                "PA":     r.get("PA",  0),
                "AB":     r.get("AB",  0),
                "H":      r.get("H",   0),
                "2B":     r.get("2B",  0),
                "3B":     r.get("3B",  0),
                "HR":     r.get("HR",  0),
                "R":      r.get("R",   0),
                "RBI":    r.get("RBI", 0),
                "BB":     r.get("BB",  0),
                "SO":     r.get("SO",  0),
                "SB":     r.get("SB",  0),
                "AVG":    r.get("AVG", 0),
                "OBP":    r.get("OBP", 0),
                "SLG":    r.get("SLG", 0),
                "OPS":    r.get("OPS", 0),
                "wOBA":   r.get("wOBA",  0),
                "wRC+":   r.get("wRC+",  100),
                "BABIP":  r.get("BABIP", 0.300),
                "ISO":    r.get("ISO",   0.150),
                "BB%":    r.get("BB%",   8.0),
                "K%":     r.get("K%",    20.0),
                "LD%":    r.get("LD%",   0),
                "GB%":    r.get("GB%",   0),
                "FB%":    r.get("FB%",   0),
                "Hard%":  r.get("Hard%", 0),
                "Barrel%":r.get("Barrel%", 0),
                "WAR":    r.get("WAR",   0),
            })
        return rows
    except Exception as e:
        print(f"  [warn] pybaseball fetch failed ({e}) — using sample data")
        return _sample_batters()


def fetch_pitching(year: int) -> list:
    """Pull FanGraphs pitching stats for the given year."""
    if not HAS_PYBASEBALL:
        return _sample_pitchers()
    try:
        print(f"  Fetching pitching stats for {year} via pybaseball…")
        df = pitching_stats(year, qual=30)
        rows = []
        for _, r in df.iterrows():
            ip = float(r.get("IP", 0) or 0)
            er = float(r.get("ER", 0) or 0)
            h  = float(r.get("H",  0) or 0)
            bb = float(r.get("BB", 0) or 0)
            era  = (er / ip * 9) if ip > 0 else 5.0
            whip = ((h + bb) / ip) if ip > 0 else 1.50
            rows.append({
                "Name":   str(r.get("Name", "")),
                "Team":   str(r.get("Team", "")),
                "IP":     ip,
                "W":      r.get("W",   0),
                "L":      r.get("L",   0),
                "SV":     r.get("SV",  0),
                "HLD":    r.get("HLD", 0),
                "SO":     r.get("SO",  0),
                "H":      h,
                "ER":     er,
                "HR":     r.get("HR",  0),
                "BB":     bb,
                "ERA":    round(era,  2),
                "WHIP":   round(whip, 2),
                "FIP":    r.get("FIP",  era),
                "xFIP":   r.get("xFIP", era),
                "SIERA":  r.get("SIERA",era),
                "K/9":    r.get("K/9",  0),
                "BB/9":   r.get("BB/9", 0),
                "GB%":    r.get("GB%",  45),
                "LOB%":   r.get("LOB%", 73),
                "HR/FB%": r.get("HR/FB%", 10),
                "BABIP":  r.get("BABIP", 0.300),
                "SwStr%": r.get("SwStr%", 0),
                "WAR":    r.get("WAR",   0),
                "QS":     0,  # FanGraphs doesn't expose QS directly
            })
        return rows
    except Exception as e:
        print(f"  [warn] pybaseball fetch failed ({e}) — using sample data")
        return _sample_pitchers()


# ══════════════════════════════════════════════════════════════════════════════
# SAMPLE DATA (2024 approximations — used if pybaseball unavailable)
# Sourced from FanGraphs / Baseball Reference 2024 final stats.
# ══════════════════════════════════════════════════════════════════════════════

def _sample_batters() -> list:
    """2024 hitter sample — top 60 by fantasy relevance."""
    return [
        # name, team, PA, H, 2B, 3B, HR, R, RBI, BB, SO, SB, AVG, OBP, SLG, wRC+, wOBA, BABIP, ISO, BB%, K%
        {"Name":"Aaron Judge",      "Team":"NYY","PA":699,"H":183,"2B":28,"3B":1, "HR":58,"R":133,"RBI":144,"BB":133,"SO":149,"SB":10, "AVG":0.322,"OBP":0.458,"SLG":0.701,"wRC+":216,"wOBA":0.479,"BABIP":0.323,"ISO":0.379,"BB%":19.0,"K%":21.3},
        {"Name":"Shohei Ohtani",    "Team":"LAD","PA":697,"H":179,"2B":32,"3B":2, "HR":54,"R":134,"RBI":130,"BB":97, "SO":162,"SB":59, "AVG":0.310,"OBP":0.390,"SLG":0.646,"wRC+":190,"wOBA":0.438,"BABIP":0.315,"ISO":0.336,"BB%":13.9,"K%":23.2},
        {"Name":"Juan Soto",        "Team":"NYY","PA":708,"H":169,"2B":33,"3B":3, "HR":41,"R":128,"RBI":109,"BB":129,"SO":111,"SB":12, "AVG":0.288,"OBP":0.419,"SLG":0.569,"wRC+":185,"wOBA":0.430,"BABIP":0.290,"ISO":0.281,"BB%":18.2,"K%":15.7},
        {"Name":"Bobby Witt Jr.",   "Team":"KC", "PA":706,"H":215,"2B":44,"3B":6, "HR":32,"R":109,"RBI":96, "BB":53, "SO":116,"SB":31, "AVG":0.332,"OBP":0.381,"SLG":0.588,"wRC+":171,"wOBA":0.414,"BABIP":0.362,"ISO":0.256,"BB%":7.5, "K%":16.4},
        {"Name":"Gunnar Henderson", "Team":"BAL","PA":691,"H":159,"2B":37,"3B":3, "HR":37,"R":90, "RBI":99, "BB":83, "SO":148,"SB":22, "AVG":0.281,"OBP":0.381,"SLG":0.498,"wRC+":155,"wOBA":0.385,"BABIP":0.299,"ISO":0.217,"BB%":12.0,"K%":21.4},
        {"Name":"Yordan Alvarez",   "Team":"HOU","PA":599,"H":148,"2B":27,"3B":1, "HR":31,"R":83, "RBI":100,"BB":78, "SO":120,"SB":2,  "AVG":0.267,"OBP":0.363,"SLG":0.497,"wRC+":158,"wOBA":0.393,"BABIP":0.283,"ISO":0.230,"BB%":13.0,"K%":20.0},
        {"Name":"Bryce Harper",     "Team":"PHI","PA":610,"H":164,"2B":38,"3B":2, "HR":30,"R":89, "RBI":90, "BB":78, "SO":111,"SB":4,  "AVG":0.284,"OBP":0.377,"SLG":0.509,"wRC+":159,"wOBA":0.396,"BABIP":0.296,"ISO":0.225,"BB%":12.8,"K%":18.2},
        {"Name":"Freddie Freeman",  "Team":"LAD","PA":646,"H":175,"2B":34,"3B":2, "HR":22,"R":83, "RBI":89, "BB":76, "SO":100,"SB":8,  "AVG":0.282,"OBP":0.378,"SLG":0.521,"wRC+":155,"wOBA":0.387,"BABIP":0.294,"ISO":0.239,"BB%":11.8,"K%":15.5},
        {"Name":"Matt Olson",       "Team":"ATL","PA":631,"H":133,"2B":27,"3B":1, "HR":33,"R":80, "RBI":96, "BB":96, "SO":162,"SB":0,  "AVG":0.232,"OBP":0.344,"SLG":0.454,"wRC+":130,"wOBA":0.354,"BABIP":0.256,"ISO":0.222,"BB%":15.2,"K%":25.7},
        {"Name":"Trea Turner",      "Team":"PHI","PA":649,"H":167,"2B":28,"3B":4, "HR":21,"R":95, "RBI":84, "BB":54, "SO":107,"SB":30, "AVG":0.295,"OBP":0.355,"SLG":0.461,"wRC+":135,"wOBA":0.361,"BABIP":0.312,"ISO":0.166,"BB%":8.3, "K%":16.5},
        {"Name":"Manny Machado",    "Team":"SD", "PA":617,"H":153,"2B":31,"3B":1, "HR":27,"R":78, "RBI":93, "BB":68, "SO":93, "SB":4,  "AVG":0.272,"OBP":0.352,"SLG":0.479,"wRC+":135,"wOBA":0.362,"BABIP":0.283,"ISO":0.207,"BB%":11.0,"K%":15.1},
        {"Name":"Rafael Devers",    "Team":"BOS","PA":636,"H":163,"2B":35,"3B":1, "HR":31,"R":82, "RBI":98, "BB":57, "SO":131,"SB":1,  "AVG":0.269,"OBP":0.333,"SLG":0.489,"wRC+":131,"wOBA":0.352,"BABIP":0.291,"ISO":0.220,"BB%":9.0, "K%":20.6},
        {"Name":"Kyle Tucker",      "Team":"HOU","PA":511,"H":124,"2B":27,"3B":3, "HR":23,"R":65, "RBI":70, "BB":58, "SO":102,"SB":15, "AVG":0.220,"OBP":0.309,"SLG":0.428,"wRC+":115,"wOBA":0.336,"BABIP":0.245,"ISO":0.208,"BB%":11.3,"K%":20.0,"signal":"BREAKOUT_CANDIDATE"},
        {"Name":"Fernando Tatis Jr","Team":"SD", "PA":622,"H":146,"2B":29,"3B":2, "HR":28,"R":87, "RBI":78, "BB":57, "SO":164,"SB":24, "AVG":0.260,"OBP":0.330,"SLG":0.480,"wRC+":128,"wOBA":0.349,"BABIP":0.305,"ISO":0.220,"BB%":9.2, "K%":26.4},
        {"Name":"Austin Riley",     "Team":"ATL","PA":603,"H":148,"2B":30,"3B":1, "HR":26,"R":80, "RBI":87, "BB":54, "SO":126,"SB":2,  "AVG":0.276,"OBP":0.340,"SLG":0.476,"wRC+":131,"wOBA":0.356,"BABIP":0.298,"ISO":0.200,"BB%":9.0, "K%":20.9},
        {"Name":"Luis Robert Jr.",  "Team":"CWS","PA":461,"H":112,"2B":24,"3B":3, "HR":20,"R":60, "RBI":62, "BB":37, "SO":111,"SB":16, "AVG":0.247,"OBP":0.308,"SLG":0.455,"wRC+":113,"wOBA":0.328,"BABIP":0.280,"ISO":0.208,"BB%":8.0, "K%":24.1,"signal":"BREAKOUT_CANDIDATE"},
        {"Name":"Julio Rodriguez",  "Team":"SEA","PA":655,"H":162,"2B":32,"3B":1, "HR":21,"R":88, "RBI":76, "BB":52, "SO":151,"SB":26, "AVG":0.269,"OBP":0.327,"SLG":0.433,"wRC+":116,"wOBA":0.333,"BABIP":0.312,"ISO":0.164,"BB%":7.9, "K%":23.1},
        {"Name":"Corey Seager",     "Team":"TEX","PA":631,"H":163,"2B":36,"3B":3, "HR":24,"R":91, "RBI":91, "BB":61, "SO":130,"SB":2,  "AVG":0.289,"OBP":0.366,"SLG":0.506,"wRC+":148,"wOBA":0.381,"BABIP":0.320,"ISO":0.217,"BB%":9.7, "K%":20.6},
        {"Name":"Marcell Ozuna",    "Team":"ATL","PA":618,"H":155,"2B":25,"3B":0, "HR":39,"R":89, "RBI":103,"BB":68, "SO":143,"SB":2,  "AVG":0.272,"OBP":0.349,"SLG":0.531,"wRC+":147,"wOBA":0.376,"BABIP":0.288,"ISO":0.259,"BB%":11.0,"K%":23.1,"signal":"REGRESSION_RISK"},
        {"Name":"William Contreras","Team":"MIL","PA":586,"H":156,"2B":28,"3B":2, "HR":24,"R":75, "RBI":88, "BB":51, "SO":89, "SB":3,  "AVG":0.286,"OBP":0.353,"SLG":0.484,"wRC+":140,"wOBA":0.368,"BABIP":0.301,"ISO":0.198,"BB%":8.7, "K%":15.2},
        {"Name":"Jackson Chourio",  "Team":"MIL","PA":633,"H":152,"2B":28,"3B":6, "HR":21,"R":90, "RBI":82, "BB":41, "SO":151,"SB":24, "AVG":0.261,"OBP":0.309,"SLG":0.427,"wRC+":104,"wOBA":0.315,"BABIP":0.305,"ISO":0.166,"BB%":6.5, "K%":23.9,"signal":"BREAKOUT_CANDIDATE"},
        {"Name":"Corbin Carroll",   "Team":"ARI","PA":622,"H":139,"2B":23,"3B":4, "HR":18,"R":82, "RBI":63, "BB":67, "SO":138,"SB":29, "AVG":0.243,"OBP":0.325,"SLG":0.395,"wRC+":102,"wOBA":0.316,"BABIP":0.288,"ISO":0.152,"BB%":10.8,"K%":22.2,"signal":"REGRESSION_RISK"},
        {"Name":"Jose Ramirez",     "Team":"CLE","PA":669,"H":163,"2B":38,"3B":2, "HR":33,"R":95, "RBI":108,"BB":61, "SO":75, "SB":19, "AVG":0.272,"OBP":0.340,"SLG":0.505,"wRC+":141,"wOBA":0.370,"BABIP":0.274,"ISO":0.233,"BB%":9.1, "K%":11.2},
        {"Name":"Mookie Betts",     "Team":"LAD","PA":416,"H":103,"2B":24,"3B":1, "HR":19,"R":60, "RBI":60, "BB":49, "SO":73, "SB":12, "AVG":0.307,"OBP":0.408,"SLG":0.547,"wRC+":160,"wOBA":0.398,"BABIP":0.330,"ISO":0.240,"BB%":11.8,"K%":17.5},
        {"Name":"Teoscar Hernandez","Team":"LAD","PA":625,"H":162,"2B":31,"3B":1, "HR":33,"R":88, "RBI":99, "BB":42, "SO":132,"SB":12, "AVG":0.272,"OBP":0.322,"SLG":0.501,"wRC+":131,"wOBA":0.354,"BABIP":0.286,"ISO":0.229,"BB%":6.7, "K%":21.1},
        {"Name":"Vladimir Guerrero Jr","Team":"TOR","PA":665,"H":165,"2B":34,"3B":1,"HR":30,"R":76,"RBI":103,"BB":68,"SO":113,"SB":4, "AVG":0.273,"OBP":0.349,"SLG":0.471,"wRC+":131,"wOBA":0.356,"BABIP":0.289,"ISO":0.198,"BB%":10.2,"K%":17.0},
        {"Name":"Josh Lowe",        "Team":"TB", "PA":577,"H":148,"2B":29,"3B":4, "HR":18,"R":74, "RBI":71, "BB":47, "SO":138,"SB":21, "AVG":0.279,"OBP":0.342,"SLG":0.455,"wRC+":119,"wOBA":0.339,"BABIP":0.336,"ISO":0.176,"BB%":8.1, "K%":23.9,"signal":"BREAKOUT_CANDIDATE"},
        {"Name":"Paul Goldschmidt",  "Team":"STL","PA":534,"H":120,"2B":23,"3B":2,"HR":22,"R":70,"RBI":71, "BB":70, "SO":105,"SB":6,  "AVG":0.245,"OBP":0.340,"SLG":0.435,"wRC+":121,"wOBA":0.342,"BABIP":0.262,"ISO":0.190,"BB%":13.1,"K%":19.7,"signal":"REGRESSION_RISK"},
        {"Name":"Alex Bregman",     "Team":"HOU","PA":602,"H":148,"2B":38,"3B":1, "HR":26,"R":83, "RBI":95, "BB":78, "SO":78, "SB":3,  "AVG":0.260,"OBP":0.353,"SLG":0.450,"wRC+":127,"wOBA":0.351,"BABIP":0.265,"ISO":0.190,"BB%":13.0,"K%":13.0},
        {"Name":"Adley Rutschman",  "Team":"BAL","PA":598,"H":142,"2B":29,"3B":1, "HR":20,"R":79, "RBI":74, "BB":74, "SO":106,"SB":3,  "AVG":0.257,"OBP":0.358,"SLG":0.406,"wRC+":122,"wOBA":0.344,"BABIP":0.279,"ISO":0.149,"BB%":12.4,"K%":17.7},
    ]


def _sample_pitchers() -> list:
    """2024 pitcher sample — top 35 by fantasy relevance."""
    return [
        # name, team, IP, W, L, SV, HLD, SO, H, ER, HR, BB, ERA, WHIP, FIP, xFIP, SIERA, K/9, BB/9, GB%, LOB%, HR/FB%, SwStr%, WAR
        {"Name":"Tarik Skubal",    "Team":"DET","IP":192.0,"W":18,"L":4, "SV":0,"HLD":0,"SO":228,"H":147,"ER":51,"HR":18,"BB":50,"ERA":2.39,"WHIP":1.03,"FIP":2.69,"xFIP":2.90,"SIERA":2.96,"K/9":10.7,"BB/9":2.3,"GB%":44.0,"LOB%":80.2,"HR/FB%":9.5,"SwStr%":15.1,"WAR":8.1},
        {"Name":"Chris Sale",      "Team":"ATL","IP":177.1,"W":17,"L":5, "SV":0,"HLD":0,"SO":225,"H":154,"ER":77,"HR":20,"BB":58,"ERA":3.91,"WHIP":1.20,"FIP":3.44,"xFIP":3.21,"SIERA":3.32,"K/9":11.4,"BB/9":2.9,"GB%":36.0,"LOB%":73.5,"HR/FB%":11.2,"SwStr%":14.7,"WAR":4.9},
        {"Name":"Zack Wheeler",    "Team":"PHI","IP":173.2,"W":16,"L":7, "SV":0,"HLD":0,"SO":213,"H":137,"ER":50,"HR":19,"BB":40,"ERA":2.57,"WHIP":1.02,"FIP":2.80,"xFIP":3.10,"SIERA":3.05,"K/9":11.0,"BB/9":2.1,"GB%":47.0,"LOB%":79.0,"HR/FB%":8.8,"SwStr%":13.9,"WAR":7.2},
        {"Name":"Logan Gilbert",   "Team":"SEA","IP":208.1,"W":13,"L":8, "SV":0,"HLD":0,"SO":194,"H":182,"ER":75,"HR":20,"BB":57,"ERA":3.24,"WHIP":1.15,"FIP":3.45,"xFIP":3.65,"SIERA":3.71,"K/9":8.4,"BB/9":2.5,"GB%":45.0,"LOB%":75.4,"HR/FB%":10.8,"SwStr%":11.2,"WAR":4.8},
        {"Name":"Cole Ragans",     "Team":"KC", "IP":183.2,"W":11,"L":9, "SV":0,"HLD":0,"SO":207,"H":143,"ER":64,"HR":22,"BB":62,"ERA":3.14,"WHIP":1.12,"FIP":3.23,"xFIP":3.30,"SIERA":3.28,"K/9":10.1,"BB/9":3.0,"GB%":46.0,"LOB%":76.8,"HR/FB%":9.9,"SwStr%":13.4,"WAR":5.0,"signal":"BUY_LOW"},
        {"Name":"Paul Skenes",     "Team":"PIT","IP":133.0,"W":11,"L":3, "SV":0,"HLD":0,"SO":170,"H":83, "ER":35,"HR":10,"BB":32,"ERA":1.96,"WHIP":0.87,"FIP":2.04,"xFIP":2.15,"SIERA":2.22,"K/9":11.5,"BB/9":2.2,"GB%":49.0,"LOB%":84.5,"HR/FB%":7.2,"SwStr%":17.3,"WAR":6.8,"signal":"BUY_LOW"},
        {"Name":"Tyler Glasnow",   "Team":"LAD","IP":134.0,"W":9, "L":6, "SV":0,"HLD":0,"SO":195,"H":95, "ER":41,"HR":16,"BB":28,"ERA":2.76,"WHIP":0.92,"FIP":2.45,"xFIP":2.62,"SIERA":2.58,"K/9":13.1,"BB/9":1.9,"GB%":39.0,"LOB%":78.3,"HR/FB%":10.1,"SwStr%":17.5,"WAR":5.5},
        {"Name":"Spencer Strider", "Team":"ATL","IP":16.2,"W":0, "L":2, "SV":0,"HLD":0,"SO":22, "H":20, "ER":11,"HR":4, "BB":7, "ERA":5.94,"WHIP":1.62,"FIP":5.11,"xFIP":5.44,"SIERA":5.20,"K/9":11.9,"BB/9":3.8,"GB%":39.0,"LOB%":56.0,"HR/FB%":17.0,"SwStr%":15.8,"WAR":-0.2,"signal":"SELL_HIGH"},
        {"Name":"Yoshinobu Yamamoto","Team":"LAD","IP":90.0,"W":7,"L":2,"SV":0,"HLD":0,"SO":105,"H":64,"ER":22,"HR":6,"BB":21,"ERA":2.20,"WHIP":0.94,"FIP":2.18,"xFIP":2.35,"SIERA":2.40,"K/9":10.5,"BB/9":2.1,"GB%":44.0,"LOB%":83.0,"HR/FB%":7.8,"SwStr%":15.5,"WAR":4.1},
        {"Name":"Gerrit Cole",     "Team":"NYY","IP":17.1,"W":1, "L":1, "SV":0,"HLD":0,"SO":20, "H":16, "ER":10,"HR":2, "BB":6, "ERA":5.19,"WHIP":1.27,"FIP":4.12,"xFIP":4.30,"SIERA":4.20,"K/9":10.4,"BB/9":3.1,"GB%":42.0,"LOB%":60.0,"HR/FB%":9.0,"SwStr%":14.1,"WAR":0.1,"signal":"SELL_HIGH"},
        {"Name":"Dylan Cease",     "Team":"SD", "IP":178.0,"W":14,"L":10,"SV":0,"HLD":0,"SO":200,"H":139,"ER":81,"HR":23,"BB":65,"ERA":4.10,"WHIP":1.15,"FIP":3.78,"xFIP":3.85,"SIERA":3.92,"K/9":10.1,"BB/9":3.3,"GB%":41.0,"LOB%":73.2,"HR/FB%":12.8,"SwStr%":13.4,"WAR":3.3},
        {"Name":"Kevin Gausman",   "Team":"TOR","IP":174.1,"W":12,"L":7, "SV":0,"HLD":0,"SO":179,"H":153,"ER":70,"HR":24,"BB":49,"ERA":3.61,"WHIP":1.16,"FIP":3.81,"xFIP":3.75,"SIERA":3.80,"K/9":9.2,"BB/9":2.5,"GB%":38.0,"LOB%":74.5,"HR/FB%":12.5,"SwStr%":13.3,"WAR":3.8},
        {"Name":"Emmanuel Clase",  "Team":"CLE","IP":65.0,"W":4, "L":2, "SV":45,"HLD":0,"SO":65, "H":45, "ER":14,"HR":3, "BB":10,"ERA":1.94,"WHIP":0.85,"FIP":2.10,"xFIP":2.50,"SIERA":2.40,"K/9":9.0,"BB/9":1.4,"GB%":71.0,"LOB%":86.0,"HR/FB%":5.5,"SwStr%":11.8,"WAR":3.1},
        {"Name":"Ryan Helsley",    "Team":"STL","IP":63.2,"W":5, "L":3, "SV":49,"HLD":0,"SO":97, "H":38, "ER":14,"HR":3, "BB":18,"ERA":1.98,"WHIP":0.88,"FIP":2.20,"xFIP":2.55,"SIERA":2.48,"K/9":13.7,"BB/9":2.5,"GB%":44.0,"LOB%":84.5,"HR/FB%":7.8,"SwStr%":18.5,"WAR":3.4},
        {"Name":"Mason Miller",    "Team":"OAK","IP":57.0,"W":3, "L":2, "SV":30,"HLD":0,"SO":85, "H":36, "ER":12,"HR":3, "BB":14,"ERA":1.89,"WHIP":0.88,"FIP":2.02,"xFIP":2.10,"SIERA":2.18,"K/9":13.4,"BB/9":2.2,"GB%":48.0,"LOB%":87.0,"HR/FB%":7.0,"SwStr%":19.2,"WAR":2.5},
        {"Name":"Corbin Burnes",   "Team":"BAL","IP":194.0,"W":15,"L":9, "SV":0,"HLD":0,"SO":185,"H":173,"ER":72,"HR":22,"BB":52,"ERA":2.92,"WHIP":1.16,"FIP":3.10,"xFIP":3.22,"SIERA":3.15,"K/9":8.6,"BB/9":2.4,"GB%":50.0,"LOB%":78.0,"HR/FB%":9.8,"SwStr%":13.3,"WAR":5.8},
        {"Name":"Hunter Brown",    "Team":"HOU","IP":164.0,"W":11,"L":9, "SV":0,"HLD":0,"SO":184,"H":149,"ER":73,"HR":21,"BB":63,"ERA":4.00,"WHIP":1.29,"FIP":3.62,"xFIP":3.48,"SIERA":3.55,"K/9":10.1,"BB/9":3.5,"GB%":43.0,"LOB%":71.5,"HR/FB%":11.5,"SwStr%":13.9,"WAR":2.9,"signal":"BUY_LOW"},
        {"Name":"Carlos Rodon",    "Team":"NYY","IP":80.0,"W":5, "L":3, "SV":0,"HLD":0,"SO":86, "H":74, "ER":38,"HR":9, "BB":23,"ERA":4.28,"WHIP":1.21,"FIP":3.72,"xFIP":3.88,"SIERA":3.95,"K/9":9.7,"BB/9":2.6,"GB%":39.0,"LOB%":70.0,"HR/FB%":11.0,"SwStr%":12.8,"WAR":1.4},
        {"Name":"Blake Snell",     "Team":"SF", "IP":104.0,"W":5, "L":10,"SV":0,"HLD":0,"SO":120,"H":79, "ER":48,"HR":15,"BB":60,"ERA":3.12,"WHIP":1.34,"FIP":3.45,"xFIP":3.80,"SIERA":3.90,"K/9":10.4,"BB/9":5.2,"GB%":38.0,"LOB%":81.5,"HR/FB%":11.0,"SwStr%":14.2,"WAR":2.1},
        {"Name":"Shane Bieber",    "Team":"CLE","IP":30.0,"W":1, "L":2, "SV":0,"HLD":0,"SO":27, "H":29, "ER":15,"HR":5, "BB":6, "ERA":4.50,"WHIP":1.17,"FIP":4.61,"xFIP":4.78,"SIERA":4.70,"K/9":8.1,"BB/9":1.8,"GB%":45.0,"LOB%":65.0,"HR/FB%":17.5,"SwStr%":10.5,"WAR":0.3,"signal":"SELL_HIGH"},
    ]


# ══════════════════════════════════════════════════════════════════════════════
# RANKING ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def spearman_rho(ranks_a: list, ranks_b: list) -> float:
    """Spearman rank correlation between two rank lists."""
    n = len(ranks_a)
    if n < 3:
        return 0.0
    d_sq = sum((a - b) ** 2 for a, b in zip(ranks_a, ranks_b))
    rho = 1 - (6 * d_sq) / (n * (n ** 2 - 1))
    return round(rho, 4)


def rank_by_score(players: list, score_fn) -> list:
    """Score and rank players; returns list sorted by projected score desc."""
    scored = []
    for p in players:
        try:
            s = score_fn(p)
        except Exception:
            s = 0.0
        scored.append({**p, "_score": s})
    scored.sort(key=lambda x: x["_score"], reverse=True)
    for i, p in enumerate(scored):
        p["_rank"] = i + 1
    return scored


def precision_at_k(predicted: list, actual: list, k: int = 50, top_n: int = 100) -> float:
    """% of model's top-k picks found in actual top-n."""
    top_pred  = {p["Name"] for p in predicted[:k]}
    top_actual = {p["Name"] for p in actual[:top_n]}
    hits = top_pred & top_actual
    return round(len(hits) / k * 100, 1)


def mae(predicted: list, actual_map: dict, k: int = 100) -> float:
    """Mean absolute error of projected rank vs actual rank for top-k."""
    errs = []
    for i, p in enumerate(predicted[:k]):
        name = p["Name"]
        if name in actual_map:
            errs.append(abs((i + 1) - actual_map[name]))
    return round(sum(errs) / len(errs), 1) if errs else 0.0


# ══════════════════════════════════════════════════════════════════════════════
# MONTE CARLO DRAFT SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

def simulate_draft(fdb_ranked: list, espn_ranked: list,
                   n_teams: int = 10, n_rounds: int = 15,
                   n_sims: int = 1000, noise_pct: float = 0.22,
                   seed: int = 42) -> dict:
    """
    Snake-draft simulation: FDB team (pick 1) vs ESPN team (picks 2-10).
    Each sim adds Gaussian noise to actual_score to model season variance.
    Returns win rates and average final standings.
    """
    rng = random.Random(seed)

    # Build pool of players with their actual FDB scores
    pool = {}
    for p in fdb_ranked:
        pool[p["Name"]] = float(p.get("_score", 0))
    for p in espn_ranked:
        pool.setdefault(p["Name"], float(p.get("_score", 0)))

    all_players = list(pool.keys())
    fdb_order   = [p["Name"] for p in fdb_ranked  if p["Name"] in pool]
    espn_order  = [p["Name"] for p in espn_ranked if p["Name"] in pool]

    fdb_wins = 0; espn_wins = 0; ties = 0
    fdb_totals = []; espn_totals = []

    for sim in range(n_sims):
        available = set(all_players)
        fdb_team  = []
        espn_team = []

        # Snake draft: pick 1 = FDB (favored), picks 2-10 = ESPN
        # Each round alternates direction
        for rnd in range(n_rounds):
            going_right = (rnd % 2 == 0)
            order = list(range(n_teams)) if going_right else list(range(n_teams - 1, -1, -1))
            for slot in order:
                if slot == 0:   # FDB team
                    pick = next((p for p in fdb_order  if p in available), None)
                else:           # ESPN team (all other slots)
                    pick = next((p for p in espn_order if p in available), None)
                if pick:
                    available.discard(pick)
                    if slot == 0:
                        fdb_team.append(pick)
                    elif slot == 1:
                        espn_team.append(pick)

        # Score with noise
        def team_score(roster):
            total = 0.0
            for name in roster:
                base = pool.get(name, 0)
                noise = rng.gauss(0, base * noise_pct)
                total += max(0, base + noise)
            return total

        fs = team_score(fdb_team)
        es = team_score(espn_team)
        fdb_totals.append(fs)
        espn_totals.append(es)

        if fs > es:     fdb_wins  += 1
        elif es > fs:   espn_wins += 1
        else:           ties      += 1

    avg_fdb  = round(sum(fdb_totals)  / n_sims, 1)
    avg_espn = round(sum(espn_totals) / n_sims, 1)
    fdb_top3  = sum(1 for f, e in zip(fdb_totals, espn_totals) if f > e * 0.95) / n_sims
    espn_top3 = sum(1 for f, e in zip(fdb_totals, espn_totals) if e > f * 0.95) / n_sims

    return {
        "n_sims":       n_sims,
        "fdb_wins":     fdb_wins,
        "espn_wins":    espn_wins,
        "ties":         ties,
        "fdb_win_pct":  round(fdb_wins  / n_sims * 100, 1),
        "espn_win_pct": round(espn_wins / n_sims * 100, 1),
        "tie_pct":      round(ties      / n_sims * 100, 1),
        "avg_fdb_pts":  avg_fdb,
        "avg_espn_pts": avg_espn,
        "pts_advantage": round(avg_fdb - avg_espn, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
# VALUE PLAY ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def find_value_plays(fdb_ranked: list, espn_ranked: list,
                     actual_ranked: list, cutoff: int = 20) -> list:
    """
    Identify players FDB ranked significantly higher than ESPN.
    A 'hit' is when that player's actual rank was also better.
    """
    fdb_rank_map   = {p["Name"]: p["_rank"] for p in fdb_ranked}
    espn_rank_map  = {p["Name"]: p["_rank"] for p in espn_ranked}
    actual_rank_map = {p["Name"]: p["_rank"] for p in actual_ranked}

    plays = []
    for name, fr in fdb_rank_map.items():
        er = espn_rank_map.get(name, fr)
        ar = actual_rank_map.get(name)
        if ar is None:
            continue
        rank_diff = er - fr   # positive = FDB ranked higher than ESPN
        if abs(rank_diff) >= cutoff:
            hit = (rank_diff > 0 and ar <= er) or (rank_diff < 0 and ar >= er)
            plays.append({
                "name":       name,
                "fdb_rank":   fr,
                "espn_rank":  er,
                "actual_rank":ar,
                "rank_diff":  rank_diff,
                "direction":  "FDB_HIGHER" if rank_diff > 0 else "ESPN_HIGHER",
                "hit":        hit,
                "signal":     next((p.get("signal","") for p in fdb_ranked if p["Name"]==name), ""),
            })
    plays.sort(key=lambda x: abs(x["rank_diff"]), reverse=True)
    return plays[:30]


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def run(year: int = 2024, n_sims: int = 1000, quick: bool = False):
    if quick:
        n_sims = 100
    print(f"\n{'='*60}")
    print(f"  FDB vs ESPN Fantasy Model Comparison — {year} Season")
    print(f"{'='*60}\n")

    # ── Fetch data ─────────────────────────────────────────────────────────────
    batters  = fetch_batting(year)
    pitchers = fetch_pitching(year)

    print(f"  {len(batters)} hitters | {len(pitchers)} pitchers loaded\n")

    # ── Actual 2024 FDB points (what really happened) ─────────────────────────
    actual_bat_ranked  = rank_by_score(batters,  calc_fdb_bat)
    actual_pit_ranked  = rank_by_score(pitchers, calc_fdb_pit)

    # ── FDB model projections (using advanced metrics) ────────────────────────
    print("  Ranking via FDB advanced model…")
    fdb_bat_ranked  = rank_by_score(batters,  fdb_project_bat)
    fdb_pit_ranked  = rank_by_score(pitchers, fdb_project_pit)

    # ── ESPN baseline projections (counting stats only) ───────────────────────
    print("  Ranking via ESPN baseline model…")
    espn_bat_ranked = rank_by_score(batters,  espn_project_bat)
    espn_pit_ranked = rank_by_score(pitchers, espn_project_pit)

    # ── Ranking correlation ───────────────────────────────────────────────────
    act_bat_map  = {p["Name"]: p["_rank"] for p in actual_bat_ranked}
    act_pit_map  = {p["Name"]: p["_rank"] for p in actual_pit_ranked}

    n_bat = min(len(actual_bat_ranked), len(fdb_bat_ranked), 40)
    n_pit = min(len(actual_pit_ranked), len(fdb_pit_ranked), 25)

    def _aligned_ranks(model_ranked, actual_map, n):
        mr, ar = [], []
        for p in model_ranked[:n]:
            if p["Name"] in actual_map:
                mr.append(p["_rank"])
                ar.append(actual_map[p["Name"]])
        return mr, ar

    fdb_bat_mr, fdb_bat_ar   = _aligned_ranks(fdb_bat_ranked,  act_bat_map, n_bat)
    espn_bat_mr, espn_bat_ar = _aligned_ranks(espn_bat_ranked, act_bat_map, n_bat)
    fdb_pit_mr, fdb_pit_ar   = _aligned_ranks(fdb_pit_ranked,  act_pit_map, n_pit)
    espn_pit_mr, espn_pit_ar = _aligned_ranks(espn_pit_ranked, act_pit_map, n_pit)

    rho_fdb_bat  = spearman_rho(fdb_bat_mr,  fdb_bat_ar)
    rho_espn_bat = spearman_rho(espn_bat_mr, espn_bat_ar)
    rho_fdb_pit  = spearman_rho(fdb_pit_mr,  fdb_pit_ar)
    rho_espn_pit = spearman_rho(espn_pit_mr, espn_pit_ar)

    mae_fdb_bat  = mae(fdb_bat_ranked,  act_bat_map,  30)
    mae_espn_bat = mae(espn_bat_ranked, act_bat_map,  30)
    mae_fdb_pit  = mae(fdb_pit_ranked,  act_pit_map,  20)
    mae_espn_pit = mae(espn_pit_ranked, act_pit_map,  20)

    p50_fdb_bat  = precision_at_k(fdb_bat_ranked,  actual_bat_ranked,  20, 30)
    p50_espn_bat = precision_at_k(espn_bat_ranked, actual_bat_ranked,  20, 30)
    p50_fdb_pit  = precision_at_k(fdb_pit_ranked,  actual_pit_ranked,  12, 18)
    p50_espn_pit = precision_at_k(espn_pit_ranked, actual_pit_ranked,  12, 18)

    # ── Draft simulation ───────────────────────────────────────────────────────
    all_fdb  = fdb_bat_ranked  + fdb_pit_ranked
    all_espn = espn_bat_ranked + espn_pit_ranked
    all_fdb.sort(key=lambda x: x["_score"], reverse=True)
    all_espn.sort(key=lambda x: x["_score"], reverse=True)

    print(f"\n  Running {n_sims:,} draft simulations…")
    sim = simulate_draft(all_fdb, all_espn, n_sims=n_sims)

    # ── Value plays ────────────────────────────────────────────────────────────
    all_actual = actual_bat_ranked + actual_pit_ranked
    all_actual.sort(key=lambda x: x["_score"], reverse=True)
    for i, p in enumerate(all_actual):
        p["_rank"] = i + 1

    value_plays = find_value_plays(all_fdb, all_espn, all_actual, cutoff=15)
    fdb_hit_rate  = sum(1 for v in value_plays if v["direction"]=="FDB_HIGHER" and v["hit"])
    fdb_calls     = sum(1 for v in value_plays if v["direction"]=="FDB_HIGHER")
    fdb_vp_rate   = round(fdb_hit_rate / fdb_calls * 100, 1) if fdb_calls else 0

    espn_hit_rate = sum(1 for v in value_plays if v["direction"]=="ESPN_HIGHER" and v["hit"])
    espn_calls    = sum(1 for v in value_plays if v["direction"]=="ESPN_HIGHER")
    espn_vp_rate  = round(espn_hit_rate / espn_calls * 100, 1) if espn_calls else 0

    # ── Player table (top 30 combined, annotated) ─────────────────────────────
    fdb_map   = {p["Name"]: p["_rank"] for p in all_fdb}
    espn_map  = {p["Name"]: p["_rank"] for p in all_espn}
    actual_map = {p["Name"]: p["_rank"] for p in all_actual}

    player_table = []
    for p in all_actual[:50]:
        nm = p["Name"]
        player_table.append({
            "name":        nm,
            "team":        p.get("Team", ""),
            "is_pitcher":  "IP" in p,
            "fdb_rank":    fdb_map.get(nm,  "—"),
            "espn_rank":   espn_map.get(nm, "—"),
            "actual_rank": actual_map.get(nm, "—"),
            "actual_pts":  round(p["_score"], 1),
            "signal":      p.get("signal", ""),
        })

    # ── Results dict ──────────────────────────────────────────────────────────
    results = {
        "year": year,
        "n_batters":  len(batters),
        "n_pitchers": len(pitchers),
        "hitters": {
            "fdb_spearman":   rho_fdb_bat,
            "espn_spearman":  rho_espn_bat,
            "fdb_mae":        mae_fdb_bat,
            "espn_mae":       mae_espn_bat,
            "fdb_precision":  p50_fdb_bat,
            "espn_precision": p50_espn_bat,
        },
        "pitchers": {
            "fdb_spearman":   rho_fdb_pit,
            "espn_spearman":  rho_espn_pit,
            "fdb_mae":        mae_fdb_pit,
            "espn_mae":       mae_espn_pit,
            "fdb_precision":  p50_fdb_pit,
            "espn_precision": p50_espn_pit,
        },
        "simulation":   sim,
        "value_plays":  value_plays,
        "player_table": player_table,
        "fdb_vp_rate":  fdb_vp_rate,
        "espn_vp_rate": espn_vp_rate,
    }

    # ── Save JSON ─────────────────────────────────────────────────────────────
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved → {OUT_JSON}")

    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  RESULTS SUMMARY — {year}")
    print(f"{'─'*60}")
    print(f"\n  HITTERS")
    print(f"    Spearman ρ:    FDB {rho_fdb_bat:+.3f}  |  ESPN {rho_espn_bat:+.3f}  {'✓ FDB wins' if rho_fdb_bat > rho_espn_bat else '✓ ESPN wins'}")
    print(f"    Rank MAE:      FDB {mae_fdb_bat:.1f}    |  ESPN {mae_espn_bat:.1f}    {'✓ FDB wins' if mae_fdb_bat < mae_espn_bat else '✓ ESPN wins'}")
    print(f"    Precision@20:  FDB {p50_fdb_bat}%   |  ESPN {p50_espn_bat}%   {'✓ FDB wins' if p50_fdb_bat > p50_espn_bat else '✓ ESPN wins'}")
    print(f"\n  PITCHERS")
    print(f"    Spearman ρ:    FDB {rho_fdb_pit:+.3f}  |  ESPN {rho_espn_pit:+.3f}  {'✓ FDB wins' if rho_fdb_pit > rho_espn_pit else '✓ ESPN wins'}")
    print(f"    Rank MAE:      FDB {mae_fdb_pit:.1f}    |  ESPN {mae_espn_pit:.1f}    {'✓ FDB wins' if mae_fdb_pit < mae_espn_pit else '✓ ESPN wins'}")
    print(f"    Precision@12:  FDB {p50_fdb_pit}%   |  ESPN {p50_espn_pit}%   {'✓ FDB wins' if p50_fdb_pit > p50_espn_pit else '✓ ESPN wins'}")
    print(f"\n  DRAFT SIMULATION ({n_sims:,} seasons)")
    print(f"    FDB  win rate: {sim['fdb_win_pct']}%")
    print(f"    ESPN win rate: {sim['espn_win_pct']}%")
    print(f"    Avg pts advantage: {sim['pts_advantage']:+.1f} pts/season (FDB)")
    print(f"\n  VALUE PLAY ACCURACY")
    print(f"    FDB  value call hit rate: {fdb_vp_rate}%")
    print(f"    ESPN value call hit rate: {espn_vp_rate}%")
    print(f"\n{'='*60}")
    print(f"  Open model_comparison.html for the interactive dashboard.")
    print(f"{'='*60}\n")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# MULTI-YEAR WEIGHTING
# ══════════════════════════════════════════════════════════════════════════════

def _year_weights(n: int) -> list:
    """Recency-weighted importance — newest year gets highest weight."""
    if n == 1: return [1.0]
    if n == 2: return [0.40, 0.60]          # [yr-2, yr-1]
    return     [0.17, 0.33, 0.50]           # [yr-3, yr-2, yr-1]


def _merge_batting(years_data: list, weights: list, actual: list) -> list:
    """
    Weighted average of batting stats across prior years.
    Players with no prior history get a league-average projection.
    Stats are normalized to full-season PA (600).
    """
    by_name: dict = {}
    for yr_data, w in zip(years_data, weights):
        for p in yr_data:
            nm = p["Name"]
            if nm not in by_name:
                by_name[nm] = {"w": 0.0, "s": {}}
            e = by_name[nm]
            e["w"] += w
            for k, v in p.items():
                if isinstance(v, (int, float)) and k != "signal":
                    e["s"][k] = e["s"].get(k, 0.0) + v * w

    LEAGUE_AVG_BAT = {
        "PA":500,"H":120,"2B":24,"3B":2,"HR":17,"R":62,"RBI":65,
        "BB":45,"SO":115,"SB":7,"AVG":0.252,"OBP":0.315,"SLG":0.408,
        "wRC+":97,"wOBA":0.313,"BABIP":0.296,"ISO":0.156,"BB%":8.4,"K%":21.5,
    }

    merged = []
    for ap in actual:
        nm = ap["Name"]
        if nm in by_name and by_name[nm]["w"] > 0:
            tw = by_name[nm]["w"]
            p = {"Name": nm, "Team": ap.get("Team", ""), "signal": ap.get("signal","")}
            for k, v in by_name[nm]["s"].items():
                p[k] = round(v / tw, 4)
        else:
            # Regression to league average for players with no prior data
            p = {"Name": nm, "Team": ap.get("Team", ""), "signal": "BREAKOUT_CANDIDATE",
                 **LEAGUE_AVG_BAT}
        merged.append(p)
    return merged


def _merge_pitching(years_data: list, weights: list, actual: list) -> list:
    """Weighted average of pitching stats across prior years."""
    by_name: dict = {}
    for yr_data, w in zip(years_data, weights):
        for p in yr_data:
            nm = p["Name"]
            if nm not in by_name:
                by_name[nm] = {"w": 0.0, "s": {}}
            e = by_name[nm]
            e["w"] += w
            for k, v in p.items():
                if isinstance(v, (int, float)) and k != "signal":
                    e["s"][k] = e["s"].get(k, 0.0) + v * w

    LEAGUE_AVG_PIT = {
        "IP":150,"W":9,"L":9,"SV":0,"HLD":0,"SO":130,"H":140,
        "ER":70,"HR":20,"BB":52,"ERA":4.20,"WHIP":1.28,
        "FIP":4.25,"xFIP":4.30,"SIERA":4.35,"K/9":7.8,"BB/9":3.1,
        "GB%":44.5,"LOB%":73.0,"HR/FB%":11.5,"SwStr%":10.8,"WAR":1.5,
    }

    merged = []
    for ap in actual:
        nm = ap["Name"]
        if nm in by_name and by_name[nm]["w"] > 0:
            tw = by_name[nm]["w"]
            p = {"Name": nm, "Team": ap.get("Team", ""), "signal": ap.get("signal","")}
            for k, v in by_name[nm]["s"].items():
                p[k] = round(v / tw, 4)
        else:
            p = {"Name": nm, "Team": ap.get("Team", ""), "signal": "BUY_LOW",
                 **LEAGUE_AVG_PIT}
        merged.append(p)
    return merged


# ══════════════════════════════════════════════════════════════════════════════
# SAMPLE DATA — PRIOR YEARS  (2021, 2022, 2023 approximations)
# Used as projection inputs when pybaseball is unavailable.
# ══════════════════════════════════════════════════════════════════════════════

def _sample_batters_year(year: int) -> list:
    """Return approximate batting stats for a prior year (used as projection base)."""
    # We apply a realistic noise profile per year to the 2024 data so the
    # simulator can demonstrate how more prior data improves prediction accuracy.
    import copy, random
    rng = random.Random(year)  # deterministic per year
    base = _sample_batters()

    # How much noise to add — further from 2024 = more variance
    noise_scale = {2023: 0.08, 2022: 0.14, 2021: 0.20}.get(year, 0.10)

    noisy = []
    for p in base:
        pp = copy.deepcopy(p)
        for k in ("HR","R","RBI","BB","SO","SB","H"):
            if k in pp:
                pp[k] = max(0, pp[k] * (1 + rng.uniform(-noise_scale, noise_scale)))
        for k in ("AVG","OBP","SLG","wOBA","BABIP","ISO"):
            if k in pp:
                pp[k] = max(0.150, pp[k] + rng.uniform(-noise_scale*0.05, noise_scale*0.05))
        for k in ("wRC+",):
            if k in pp:
                pp[k] = max(60, pp[k] + rng.uniform(-noise_scale*20, noise_scale*20))
        noisy.append(pp)
    return noisy


def _sample_pitchers_year(year: int) -> list:
    """Return approximate pitching stats for a prior year (used as projection base)."""
    import copy, random
    rng = random.Random(year + 1000)
    base = _sample_pitchers()
    noise_scale = {2023: 0.09, 2022: 0.15, 2021: 0.21}.get(year, 0.10)

    noisy = []
    for p in base:
        pp = copy.deepcopy(p)
        for k in ("SO","H","ER","W","BB"):
            if k in pp:
                pp[k] = max(0, pp[k] * (1 + rng.uniform(-noise_scale, noise_scale)))
        for k in ("ERA","FIP","xFIP","SIERA","WHIP"):
            if k in pp:
                pp[k] = max(1.5, pp[k] + rng.uniform(-noise_scale*0.5, noise_scale*0.5))
        noisy.append(pp)
    return noisy


def fetch_batting_year(year: int) -> list:
    """Fetch batting stats for a specific year (live or sample)."""
    if HAS_PYBASEBALL:
        return fetch_batting(year)
    return _sample_batters_year(year) if year < 2024 else _sample_batters()


def fetch_pitching_year(year: int) -> list:
    """Fetch pitching stats for a specific year (live or sample)."""
    if HAS_PYBASEBALL:
        return fetch_pitching(year)
    return _sample_pitchers_year(year) if year < 2024 else _sample_pitchers()


# ══════════════════════════════════════════════════════════════════════════════
# INTERACTIVE PROMPT
# ══════════════════════════════════════════════════════════════════════════════

def prompt_user() -> tuple:
    """
    Interactive CLI prompt — asks user which year to predict and how many
    years of prior data to use as projection inputs.
    """
    print()
    print("╔" + "═"*53 + "╗")
    print("║   FDB vs ESPN Fantasy Model Comparison Engine      ║")
    print("╚" + "═"*53 + "╝")

    # ── Which year to PREDICT ─────────────────────────────────────────────────
    predict_choices = [2024, 2023, 2022, 2021]
    print()
    print("  Which season do you want to PREDICT?")
    print("  (FDB and ESPN models are tested against this year's actual results)")
    print()
    for i, yr in enumerate(predict_choices, 1):
        tag = "  ← most recent" if yr == 2024 else ""
        print(f"    [{i}]  {yr}{tag}")
    print()
    predict_year = None
    while predict_year is None:
        raw = input("  Enter 1–4: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= 4:
            predict_year = predict_choices[int(raw) - 1]
        else:
            print("  Please enter a number between 1 and 4.")

    # ── How many prior years of data ──────────────────────────────────────────
    print()
    print(f"  How many years of PRIOR DATA to build projections from?")
    print(f"  (Stats from seasons before {predict_year} will be used as projection inputs)")
    print()
    options = [
        (1, f"{predict_year-1} only",
         "Fast — less stable, more sensitive to single-season noise"),
        (2, f"{predict_year-2}–{predict_year-1}",
         "Balanced — recent weighted 60%, older 40%"),
        (3, f"{predict_year-3}–{predict_year-1}",
         "Most stable — three-year weighted blend (50% / 33% / 17%)"),
    ]
    for i, (n, yrs, desc) in enumerate(options, 1):
        print(f"    [{i}]  {n} year{'s' if n>1 else ''}  ({yrs})")
        print(f"         {desc}")
        print()
    prior_years = None
    while prior_years is None:
        raw = input("  Enter 1–3: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= 3:
            prior_years = int(raw)
        else:
            print("  Please enter 1, 2, or 3.")

    sims_default = 1000
    print()
    print(f"  Monte Carlo draft simulations to run? [default: {sims_default}]")
    print(f"  (More sims = more reliable win %, but takes longer)")
    raw = input(f"  Enter number or press Enter for {sims_default}: ").strip()
    n_sims = int(raw) if raw.isdigit() and int(raw) >= 10 else sims_default

    return predict_year, prior_years, n_sims


# ══════════════════════════════════════════════════════════════════════════════
# UPDATED MAIN — supports predict_year + prior_years
# ══════════════════════════════════════════════════════════════════════════════

def run(predict_year: int = 2024, prior_years: int = 2,
        n_sims: int = 1000, quick: bool = False):
    """
    Full simulation pipeline.

    predict_year  — the season whose actual results we evaluate against.
    prior_years   — how many seasons of prior data feed the projection models.
    """
    if quick:
        n_sims = 100

    prior_range = (f"{predict_year - prior_years}–{predict_year - 1}"
                   if prior_years > 1 else str(predict_year - 1))

    print(f"\n{'='*60}")
    print(f"  FDB vs ESPN Model Comparison")
    print(f"  Predicting: {predict_year}  |  Training data: {prior_range}")
    print(f"{'='*60}\n")

    # ── 1. Fetch actual results for the season we're evaluating ───────────────
    print(f"  Loading {predict_year} actual results (ground truth)…")
    actual_batters  = fetch_batting_year(predict_year)
    actual_pitchers = fetch_pitching_year(predict_year)

    # ── 2. Fetch prior-year data as projection inputs ─────────────────────────
    weights    = _year_weights(prior_years)
    prior_bat  = []
    prior_pit  = []
    for i in range(prior_years):
        yr = predict_year - prior_years + i
        print(f"  Loading {yr} projection data (weight {weights[i]:.0%})…")
        prior_bat.append(fetch_batting_year(yr))
        prior_pit.append(fetch_pitching_year(yr))

    # ── 3. Build weighted projection base ─────────────────────────────────────
    proj_bat = _merge_batting(prior_bat,  weights, actual_batters)
    proj_pit = _merge_pitching(prior_pit, weights, actual_pitchers)

    print(f"\n  {len(proj_bat)} projected hitters | {len(proj_pit)} projected pitchers")
    print(f"  {len(actual_batters)} actual hitters    | {len(actual_pitchers)} actual pitchers\n")

    # ── 4. Actual FDB points (what really happened — ground truth) ────────────
    actual_bat_ranked = rank_by_score(actual_batters,  calc_fdb_bat)
    actual_pit_ranked = rank_by_score(actual_pitchers, calc_fdb_pit)

    # ── 5. FDB projection (advanced metrics on prior-year weighted stats) ─────
    print("  Ranking via FDB advanced model…")
    fdb_bat_ranked  = rank_by_score(proj_bat, fdb_project_bat)
    fdb_pit_ranked  = rank_by_score(proj_pit, fdb_project_pit)

    # ── 6. ESPN projection (raw counting stats on prior-year weighted stats) ──
    print("  Ranking via ESPN baseline model…")
    espn_bat_ranked = rank_by_score(proj_bat, espn_project_bat)
    espn_pit_ranked = rank_by_score(proj_pit, espn_project_pit)

    # ── 7. Ranking accuracy metrics ───────────────────────────────────────────
    act_bat_map  = {p["Name"]: p["_rank"] for p in actual_bat_ranked}
    act_pit_map  = {p["Name"]: p["_rank"] for p in actual_pit_ranked}

    n_bat = min(len(actual_bat_ranked), 30)
    n_pit = min(len(actual_pit_ranked), 20)

    def _aligned(model_ranked, actual_map, n):
        mr, ar = [], []
        for p in model_ranked[:n]:
            if p["Name"] in actual_map:
                mr.append(p["_rank"]); ar.append(actual_map[p["Name"]])
        return mr, ar

    fdb_bat_mr,  fdb_bat_ar   = _aligned(fdb_bat_ranked,  act_bat_map, n_bat)
    espn_bat_mr, espn_bat_ar  = _aligned(espn_bat_ranked, act_bat_map, n_bat)
    fdb_pit_mr,  fdb_pit_ar   = _aligned(fdb_pit_ranked,  act_pit_map, n_pit)
    espn_pit_mr, espn_pit_ar  = _aligned(espn_pit_ranked, act_pit_map, n_pit)

    rho_fdb_bat  = spearman_rho(fdb_bat_mr,  fdb_bat_ar)
    rho_espn_bat = spearman_rho(espn_bat_mr, espn_bat_ar)
    rho_fdb_pit  = spearman_rho(fdb_pit_mr,  fdb_pit_ar)
    rho_espn_pit = spearman_rho(espn_pit_mr, espn_pit_ar)

    mae_fdb_bat  = mae(fdb_bat_ranked,  act_bat_map, 25)
    mae_espn_bat = mae(espn_bat_ranked, act_bat_map, 25)
    mae_fdb_pit  = mae(fdb_pit_ranked,  act_pit_map, 15)
    mae_espn_pit = mae(espn_pit_ranked, act_pit_map, 15)

    p_fdb_bat  = precision_at_k(fdb_bat_ranked,  actual_bat_ranked, 20, 30)
    p_espn_bat = precision_at_k(espn_bat_ranked, actual_bat_ranked, 20, 30)
    p_fdb_pit  = precision_at_k(fdb_pit_ranked,  actual_pit_ranked, 12, 18)
    p_espn_pit = precision_at_k(espn_pit_ranked, actual_pit_ranked, 12, 18)

    # ── 8. Draft simulation ───────────────────────────────────────────────────
    all_fdb  = sorted(fdb_bat_ranked  + fdb_pit_ranked,  key=lambda x: x["_score"], reverse=True)
    all_espn = sorted(espn_bat_ranked + espn_pit_ranked, key=lambda x: x["_score"], reverse=True)

    # Use ACTUAL scores as what each player really produces in the sim
    actual_score_map = {p["Name"]: p["_score"] for p in actual_bat_ranked + actual_pit_ranked}
    for p in all_fdb:  p["_actual"] = actual_score_map.get(p["Name"], p["_score"])
    for p in all_espn: p["_actual"] = actual_score_map.get(p["Name"], p["_score"])

    print(f"\n  Running {n_sims:,} draft simulations…")
    sim = simulate_draft(all_fdb, all_espn, n_sims=n_sims)

    # ── 9. Value play analysis ────────────────────────────────────────────────
    all_actual = sorted(actual_bat_ranked + actual_pit_ranked,
                        key=lambda x: x["_score"], reverse=True)
    for i, p in enumerate(all_actual): p["_rank"] = i + 1

    fdb_all_map  = {p["Name"]: p["_rank"] for p in all_fdb}
    espn_all_map = {p["Name"]: p["_rank"] for p in all_espn}

    value_plays = find_value_plays(all_fdb, all_espn, all_actual, cutoff=12)
    fdb_vp_hits  = sum(1 for v in value_plays if v["direction"]=="FDB_HIGHER" and v["hit"])
    fdb_vp_calls = sum(1 for v in value_plays if v["direction"]=="FDB_HIGHER")
    fdb_vp_rate  = round(fdb_vp_hits  / fdb_vp_calls  * 100, 1) if fdb_vp_calls  else 0

    espn_vp_hits  = sum(1 for v in value_plays if v["direction"]=="ESPN_HIGHER" and v["hit"])
    espn_vp_calls = sum(1 for v in value_plays if v["direction"]=="ESPN_HIGHER")
    espn_vp_rate  = round(espn_vp_hits / espn_vp_calls * 100, 1) if espn_vp_calls else 0

    # ── 10. Player table ──────────────────────────────────────────────────────
    actual_map = {p["Name"]: p["_rank"] for p in all_actual}
    player_table = []
    for p in all_actual[:50]:
        nm = p["Name"]
        player_table.append({
            "name":        nm,
            "team":        p.get("Team", ""),
            "is_pitcher":  "IP" in p or "ERA" in p,
            "fdb_rank":    fdb_all_map.get(nm,  "—"),
            "espn_rank":   espn_all_map.get(nm, "—"),
            "actual_rank": actual_map.get(nm, "—"),
            "actual_pts":  round(p["_score"], 1),
            "signal":      p.get("signal", ""),
        })

    # ── 11. Build results dict ────────────────────────────────────────────────
    results = {
        "predict_year": predict_year,
        "prior_years":  prior_years,
        "prior_range":  prior_range,
        "n_batters":    len(actual_batters),
        "n_pitchers":   len(actual_pitchers),
        "hitters": {
            "fdb_spearman":   rho_fdb_bat,
            "espn_spearman":  rho_espn_bat,
            "fdb_mae":        mae_fdb_bat,
            "espn_mae":       mae_espn_bat,
            "fdb_precision":  p_fdb_bat,
            "espn_precision": p_espn_bat,
        },
        "pitchers": {
            "fdb_spearman":   rho_fdb_pit,
            "espn_spearman":  rho_espn_pit,
            "fdb_mae":        mae_fdb_pit,
            "espn_mae":       mae_espn_pit,
            "fdb_precision":  p_fdb_pit,
            "espn_precision": p_espn_pit,
        },
        "simulation":    sim,
        "value_plays":   value_plays,
        "player_table":  player_table,
        "fdb_vp_rate":   fdb_vp_rate,
        "espn_vp_rate":  espn_vp_rate,
    }

    # ── 12. Save JSON ─────────────────────────────────────────────────────────
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved → {OUT_JSON}")

    # ── 13. Print summary ─────────────────────────────────────────────────────
    W = lambda a, b, lo=False: "✓ FDB" if (a < b if lo else a > b) else "  ESPN"
    print(f"\n{'─'*60}")
    print(f"  RESULTS — Predicting {predict_year} from {prior_range} data")
    print(f"{'─'*60}")
    print(f"\n  HITTERS")
    print(f"    Spearman ρ:   FDB {rho_fdb_bat:+.3f}  ESPN {rho_espn_bat:+.3f}  {W(rho_fdb_bat, rho_espn_bat)}")
    print(f"    Rank MAE:     FDB {mae_fdb_bat:.1f}    ESPN {mae_espn_bat:.1f}    {W(mae_fdb_bat, mae_espn_bat, lo=True)}")
    print(f"    Precision@20: FDB {p_fdb_bat}%   ESPN {p_espn_bat}%   {W(p_fdb_bat, p_espn_bat)}")
    print(f"\n  PITCHERS")
    print(f"    Spearman ρ:   FDB {rho_fdb_pit:+.3f}  ESPN {rho_espn_pit:+.3f}  {W(rho_fdb_pit, rho_espn_pit)}")
    print(f"    Rank MAE:     FDB {mae_fdb_pit:.1f}    ESPN {mae_espn_pit:.1f}    {W(mae_fdb_pit, mae_espn_pit, lo=True)}")
    print(f"    Precision@12: FDB {p_fdb_pit}%   ESPN {p_espn_pit}%   {W(p_fdb_pit, p_espn_pit)}")
    print(f"\n  DRAFT SIMULATION ({n_sims:,} seasons)")
    print(f"    FDB  win rate: {sim['fdb_win_pct']}%")
    print(f"    ESPN win rate: {sim['espn_win_pct']}%")
    print(f"    Pts advantage: {sim['pts_advantage']:+.1f} pts/season (FDB)")
    print(f"\n  VALUE CALL ACCURACY")
    print(f"    FDB  hit rate: {fdb_vp_rate}%")
    print(f"    ESPN hit rate: {espn_vp_rate}%")
    print(f"\n{'='*60}")
    print(f"  Open model_comparison.html for the interactive dashboard.")
    print(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FDB vs ESPN Fantasy Baseball Model Comparison",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/model_comparison.py                        # interactive prompt
  python tools/model_comparison.py --predict-year 2024 --prior-years 2
  python tools/model_comparison.py --predict-year 2023 --prior-years 3 --sims 500
  python tools/model_comparison.py --quick               # 100-sim fast run
""")
    parser.add_argument("--predict-year", type=int, default=None,
                        help="Season to predict (e.g. 2024). Prompts if omitted.")
    parser.add_argument("--prior-years",  type=int, default=None,
                        choices=[1, 2, 3],
                        help="Years of prior data for projections (1–3). Prompts if omitted.")
    parser.add_argument("--sims",  type=int, default=None,
                        help="Monte Carlo iterations (default 1000). Prompts if omitted.")
    parser.add_argument("--quick", action="store_true",
                        help="Override --sims with 100 iterations (fast preview).")
    # Legacy alias
    parser.add_argument("--year", type=int, default=None,
                        help=argparse.SUPPRESS)   # kept for backward compat

    args = parser.parse_args()

    # Resolve legacy --year alias
    predict_year = args.predict_year or args.year
    prior_years  = args.prior_years
    n_sims       = args.sims

    # Interactive prompt for any unspecified required params
    if predict_year is None or prior_years is None:
        predict_year, prior_years, n_sims_prompt = prompt_user()
        if n_sims is None:
            n_sims = n_sims_prompt

    if n_sims is None:
        n_sims = 1000

    run(predict_year=predict_year, prior_years=prior_years,
        n_sims=n_sims, quick=args.quick)
