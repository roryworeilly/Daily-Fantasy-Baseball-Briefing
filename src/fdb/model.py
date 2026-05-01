"""
Machine-generated from fdbRV.py — see .build/generate_fdb_package.py.
"""
import os
import sys
import math
import json
import re
import html
import time
import hashlib
from datetime import datetime, timedelta

from fdb.settings import (
    SCRIPT_DIR,
    LEAGUE_ID, YEAR, SWID, ESPN_S2, MY_TEAM_NAME, N_TEAMS,
    BATTING_SCORING, PITCHING_SCORING, SLOTS_PER_TEAM,
    REPLACEMENT_BUFFER,
    WEEKLY_IP_LIMIT,
    STASH_SCORE_THRESHOLD, SEASON_INTEL_FA_THRESHOLD,
    SEASON_TREND_MIN_GAMES, SEASON_TREND_LOOKBACK,
    MARKET, WEEKLY_STARTS, SCALING,
    REFERENCE_DB_PATH, REFERENCE_DB,
    PROJECTION_DB_PATH, PROJECTION_DB,
    STATCAST_DB_PATH, STATCAST_DB,
    PYBASEBALL_AVAILABLE,
    League,
    batting_stats, pitching_stats,
    batting_stats_bref, pitching_stats_bref,
    bwar_bat, bwar_pitch,
)
from espn_api.baseball.player import Player as ESPNPlayer
from fdb.utils import normalize_name


def safe_get(obj, *attrs, default=None):
    for attr in attrs:
        val = getattr(obj, attr, None)
        if val is not None:
            return val
    return default

def as_float(value, default=0.0):
    try:
        return float(value) if value not in (None, "") else default
    except Exception:
        return default

def normalize_pos(pos):
    return str(pos).upper() if pos else "?"

def get_player_slots(player):
    slots = safe_get(player, "eligibleSlots", default=[]) or []
    return [normalize_pos(s) for s in slots] if slots else ["?"]

def get_lineup_slot(player):
    return normalize_pos(safe_get(player, "lineupSlot", default="?"))

def get_player_status(player):
    return safe_get(player, "injuryStatus", default="ACTIVE") or "ACTIVE"

def get_player_team(player):
    return safe_get(player, "proTeam", default="?")

def is_pitcher(player):
    return bool(set(get_player_slots(player)) & {"SP", "RP", "P"})

def is_hitter(player):
    return not is_pitcher(player)

# ── Pitcher role detection (starter vs. reliever) ─────────────────────────────

def _pitcher_gs_from_ref(player):
    """Return GS from last-season reference DB, or -1.0 if the player isn't found."""
    m = get_reference_metrics(player)
    if not m:
        return -1.0
    return get_metric(m, "GS")   # 0.0 for confirmed pure relievers

def is_starter_role(player):
    """
    True if pitcher is primarily a starter.

    Priority:
      1. If ESPN's current lineup slot is SP → starter (2026 reality)
      2. If eligibility slots are SP-only (no RP) → starter
      3. If reference DB GS ≥ 15 → starter (2025 proxy)
      4. Default: False
    """
    if not is_pitcher(player):
        return False
    # 1. Current-season ESPN slot (most accurate for 2026 role changes)
    current_slot = normalize_pos(safe_get(player, "lineupSlot", default="?"))
    if current_slot == "SP":
        return True
    # 2. Eligibility slots — SP-only means they're classified as a starter
    slots = set(get_player_slots(player))
    if "SP" in slots and "RP" not in slots:
        return True
    # 3. Reference DB prior-season GS (2025 fallback)
    gs = _pitcher_gs_from_ref(player)
    if gs >= 0:
        return gs >= 15
    return False

def is_reliever_role(player):
    """
    True if pitcher is primarily a reliever.

    Priority:
      1. Current ESPN slot is RP/P and not SP → reliever
      2. Eligibility slots RP-only → reliever
      3. Reference DB GS < 10 → reliever
    """
    if not is_pitcher(player):
        return False
    # 1. Current-season ESPN slot
    current_slot = normalize_pos(safe_get(player, "lineupSlot", default="?"))
    if current_slot in ("RP", "P") and current_slot != "SP":
        # But also check eligibility — SP-eligible pitchers in RP slot may be openers
        slots = set(get_player_slots(player))
        if "SP" not in slots:
            return True
    # 2. Eligibility slots — RP-only
    slots = set(get_player_slots(player))
    if "RP" in slots and "SP" not in slots:
        return True
    # 3. Reference DB prior-season GS
    gs = _pitcher_gs_from_ref(player)
    if gs >= 0:
        return gs < 10
    return False

def is_active_slot(slot):
    return slot not in {"BE", "BENCH", "IL", "IR", "NA"}

def get_metric(row, *keys, default=0.0):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return as_float(row[key], default)
    return default

def esc(v):
    return html.escape(str(v))

def fmt(v, d=2):
    try:
        return f"{float(v):.{d}f}"
    except Exception:
        return str(v)

def get_player_headshot_url(player):
    """ESPN CDN primary headshot — uses the espn-api player ID."""
    for attr in ("playerId", "player_id", "id"):
        try:
            pid = int(safe_get(player, attr) or 0)
            if pid > 0:
                return f"https://a.espncdn.com/i/headshots/mlb/players/full/{pid}.png"
        except Exception:
            pass
    return ""

def get_player_headshot_url_mlb(player):
    """MLB Stats CDN secondary headshot — uses the MLBAM pro player ID."""
    for attr in ("proId", "pro_id", "proPlayerId"):
        try:
            pid = int(safe_get(player, attr) or 0)
            if pid > 0:
                return (
                    f"https://img.mlbstatic.com/mlb-photos/image/upload/"
                    f"w_180,q_auto:best/v1/people/{pid}/headshot/67/current"
                )
        except Exception:
            pass
    return ""

# Populated by load_statcast_db() — normalized name → MLBAM ID str.
# Declared here (before get_mlbam_id) so the function body can reference it.
_SC_NAME_TO_MLBAM: dict[str, str] = {}


def get_mlbam_id(player):
    """
    Return the MLBAM (MLB Stats API) player ID as a string, or '' if unavailable.

    ESPN's Player class exposes no proId/proAthleteId attribute, so we fall back
    to the name → MLBAM index built from the Statcast cache (which IS keyed by
    MLBAM ID and contains a 'name' field for each entry).
    """
    # 1) Direct attribute — works if player came from a custom source
    for attr in ("proId", "pro_id", "proPlayerId", "proAthleteId"):
        try:
            pid = int(safe_get(player, attr) or 0)
            if pid > 0:
                return str(pid)
        except Exception:
            pass
    # 2) Statcast name index — fast dict lookup, no HTTP call required
    name = getattr(player, "name", "")
    if name and _SC_NAME_TO_MLBAM:
        nm = normalize_name(name)
        mlbam = _SC_NAME_TO_MLBAM.get(nm, "")
        if mlbam:
            return mlbam
    return ""

def get_espn_id(player):
    """Return the ESPN player ID as a string, or '' if unavailable."""
    for attr in ("playerId", "player_id", "id"):
        try:
            pid = int(safe_get(player, attr) or 0)
            if pid > 0:
                return str(pid)
        except Exception:
            pass
    return ""

def get_initials(name):
    parts = [p for p in str(name).split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) > 1 else parts[0][:2].upper()

def avatar_seed(name):
    return hashlib.md5(name.encode()).hexdigest()[:10]


# ══════════════════════════════════════════════════════════════════════════════
# ESPN HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def connect():
    league = League(league_id=LEAGUE_ID, year=YEAR, swid=SWID, espn_s2=ESPN_S2)
    _reload_rosters_today(league)
    return league


def _reload_rosters_today(league):
    """
    Re-fetch all team rosters with today's scoringPeriodId so lineupSlot
    reflects actual daily assignments (active vs. bench) rather than the
    week-start default returned by the bare mRoster view.

    Baseball has one scoring period per day (period ID increments daily).
    Without this call, a player your manager benched today still shows as
    'active', and players added/moved this morning may show in stale slots.
    """
    from espn_api.baseball.player import Player as ESPNPlayer
    try:
        period = getattr(league, "current_week", None) or getattr(league, "scoringPeriodId", None)
        if not period:
            return

        params = {
            "view": ["mRoster"],
            "scoringPeriodId": period,
        }
        data = league.espn_request.league_get(params=params)

        fresh: dict[int, dict] = {}
        for td in data.get("teams", []):
            tid     = td.get("id")
            roster  = td.get("roster")
            if tid is not None and roster:
                fresh[tid] = roster

        updated = 0
        for team in league.teams:
            if team.team_id in fresh:
                team._fetch_roster(fresh[team.team_id], league.year)
                updated += 1

        print(f"  Roster refresh: {updated}/{len(league.teams)} teams synced to period {period}")
    except Exception as exc:
        print(f"  Roster refresh skipped ({type(exc).__name__}: {exc})")


def get_my_team(league):
    for team in league.teams:
        if MY_TEAM_NAME.lower() in team.team_name.lower():
            return team
    return None

def get_matchup(league, my_team):
    """Return (matchup, my_team_obj, opponent_team_obj) or (None, None, None)."""
    for m in league.box_scores(league.current_week):
        home = getattr(m, "home_team", None)
        away = getattr(m, "away_team", None)
        if not home or not away:
            continue
        if home.team_name == my_team.team_name:
            return m, home, away
        if away.team_name == my_team.team_name:
            return m, away, home
    return None, None, None


def get_matchup_scoring_breakdown(league, my_team):
    """
    Extract player-level weekly scoring from the ESPN box score.

    Returns (my_players, opp_players) — each a list of dicts:
        name        str   – player name
        slot        str   – lineup slot ('C', 'SP', 'BE', 'IL', …)
        pts         float – actual points scored this week
        proj        float – projected points this week
        is_bench    bool  – True if slot is BE / IL / BN
        breakdown   dict  – {stat_name: pts_contribution} for non-zero stats

    Players are sorted: active first, then descending by pts within each group.
    """
    matchup, me, opp = get_matchup(league, my_team)
    if not matchup:
        return [], []

    is_home    = (me.team_name == getattr(matchup.home_team, "team_name", None))
    my_lineup  = getattr(matchup, "home_lineup"  if is_home else "away_lineup",  [])
    opp_lineup = getattr(matchup, "away_lineup"  if is_home else "home_lineup",  [])

    def _extract(lineup):
        rows = []
        for bp in lineup:
            slot      = getattr(bp, "slot_position", "") or ""
            pts       = as_float(getattr(bp, "points",            0))
            proj      = as_float(getattr(bp, "projected_points",  0))
            breakdown = getattr(bp, "points_breakdown", {}) or {}
            # Keep only non-zero point contributions, rounded to 1 dp
            bd_clean  = {
                k: round(float(v), 1)
                for k, v in breakdown.items()
                if v and float(v) != 0
            }
            rows.append({
                "name":      getattr(bp, "name", "") or "",
                "slot":      slot,
                "pts":       round(pts,  1),
                "proj":      round(proj, 1),
                "is_bench":  slot in ("BE", "IL", "BN", "IR"),
                "breakdown": bd_clean,
            })
        # Active players first, then bench/IL; within each group sort by pts desc
        rows.sort(key=lambda r: (r["is_bench"], -r["pts"]))
        return rows

    try:
        return _extract(my_lineup), _extract(opp_lineup)
    except Exception as e:
        print(f"  Warning: lineup extraction failed (non-fatal): {e}")
        return [], []


def get_recent_activity(league, size=40):
    """Return (adds_counter, drops_counter, move_list).

    Each entry in move_list is a dict with at minimum {"team", "move", "player"}.

    Special move types emitted:
      "SWAP"   – 1-for-1 FA/waiver pickup: also has "dropped" key.
      "TRADED" – trade between two teams: has "team", "gave" (list), "to_team",
                 "received" (list).  "player" is set to the first received player
                 for backward-compat callers that only look at "player".
      "ADD"    – unpaired FA/waiver add (no simultaneous drop).
      "DROP"   – unpaired drop.

    TRADED actions (messageTypeId 244) are kept entirely separate from the
    SWAP/ADD/DROP logic — they cannot accidentally be folded into a SWAP.
    """
    adds, drops, moves = {}, {}, []
    try:
        for act in league.recent_activity(size=size):
            actions = getattr(act, "actions", [])
            if not actions:
                continue

            # ── Separate trade actions from add/drop actions ───────────────
            trade_actions  = []   # (team_name, player_name) — team GAVE player away
            pickup_actions = []   # (team_name, move_type_lower, player_name)

            for action in actions:
                if len(action) < 3:
                    continue
                team_obj, move_type_raw, player_obj = action[0], action[1], action[2]
                tname  = getattr(team_obj,   "team_name", "?")
                pname  = getattr(player_obj, "name",      str(player_obj))
                mtype  = str(move_type_raw).lower()

                if mtype == "traded":
                    trade_actions.append((tname, pname))
                else:
                    pickup_actions.append((tname, mtype, pname))
                    norm = normalize_name(pname)
                    if "add"  in mtype: adds[norm]  = adds.get(norm,  0) + 1
                    if "drop" in mtype: drops[norm] = drops.get(norm, 0) + 1

            # ── Emit trade as a single consolidated entry ──────────────────
            if trade_actions:
                # Each entry means that team gave away that player.
                # Group by team to find each side's contributions.
                trade_sides = {}
                for tname, pname in trade_actions:
                    trade_sides.setdefault(tname, []).append(pname)

                teams = list(trade_sides.keys())
                if len(teams) == 2:
                    team_a, team_b = teams[0], teams[1]
                    gave_a = trade_sides[team_a]   # what TeamA gave away (TeamB received)
                    gave_b = trade_sides[team_b]   # what TeamB gave away (TeamA received)
                    moves.append({
                        "move":     "TRADED",
                        "team":     team_a,
                        "gave":     gave_a,
                        "to_team":  team_b,
                        "received": gave_b,
                        "player":   (gave_b[0] if gave_b else gave_a[0]) if (gave_b or gave_a) else "Unknown",
                    })
                else:
                    # 3-way trade or unusual structure — one row per team
                    for tname, players in trade_sides.items():
                        for pname in players:
                            moves.append({"move": "TRADED", "team": tname, "player": pname})

            # ── Emit add/drop actions; pair same-team ADD+DROP as SWAP ─────
            if pickup_actions:
                team_buckets = {}
                for tname, mtype, pname in pickup_actions:
                    team_buckets.setdefault(tname, {"adds": [], "drops": [], "other": []})
                    if "add" in mtype:
                        team_buckets[tname]["adds"].append(pname)
                    elif "drop" in mtype:
                        team_buckets[tname]["drops"].append(pname)
                    else:
                        team_buckets[tname]["other"].append((mtype.upper(), pname))

                for tname, tb in team_buckets.items():
                    ta, td = tb["adds"], tb["drops"]
                    pairs = min(len(ta), len(td))
                    for i in range(pairs):
                        moves.append({
                            "team":    tname,
                            "move":    "SWAP",
                            "player":  ta[i],
                            "dropped": td[i],
                        })
                    for p in ta[pairs:]:
                        moves.append({"team": tname, "move": "ADD", "player": p})
                    for p in td[pairs:]:
                        moves.append({"team": tname, "move": "DROP", "player": p})
                    for mtype, p in tb["other"]:
                        moves.append({"team": tname, "move": mtype, "player": p})
    except Exception as e:
        print(f"  Warning: recent_activity() parse failed (non-fatal): {e}")
    return adds, drops, moves


# ══════════════════════════════════════════════════════════════════════════════
# PYBASEBALL REFERENCE LAYER
# ══════════════════════════════════════════════════════════════════════════════

def _compact(v, ndigits=4):
    """Round a float for compact cache storage; returns 0.0 for non-numeric."""
    try:
        f = float(v)
        return round(f, ndigits) if f == f else 0.0  # NaN guard
    except Exception:
        return 0.0


def _load_reference_from_fangraphs(season):
    """
    FanGraphs via pybaseball — JSON-based API, far more stable than BRef scraping.

    Phase 1 advanced metrics now included (see Analytics_Roadmap.md):
      Hitters : wRC+, wOBA, ISO, BB%, K%, BABIP, LD%, GB%, FB%, Hard%, Barrel%
      Pitchers: FIP, xFIP, SIERA, SwStr%, GB%, LD%, FB%, K/9, BB/9, K-BB%, HR/FB%, LOB%

    Token-optimization: _compact() rounds all floats to 4 decimal places,
    reducing JSON cache size while preserving meaningful precision.
    Columns that don't exist in a given API response silently return 0.0.
    """
    h_df = batting_stats(season, season, qual=0)
    p_df = pitching_stats(season, season, qual=0)

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
            "PA":  _compact(get_metric(row, "PA"),  1),
            "H":   _compact(h,                      1),
            "2B":  _compact(d,                      1),
            "3B":  _compact(t,                      1),
            "HR":  _compact(hr,                     1),
            "R":   _compact(get_metric(row, "R"),   1),
            "RBI": _compact(get_metric(row, "RBI"), 1),
            "SB":  _compact(get_metric(row, "SB"),  1),
            "BB":  _compact(get_metric(row, "BB"),  1),
            "SO":  _compact(get_metric(row, "SO"),  1),
            "TB":  _compact(h + d + 2 * t + 3 * hr, 1),
            "OPS": _compact(get_metric(row, "OPS")),
            "WAR": _compact(get_metric(row, "WAR")),
            # ── Phase 1: FanGraphs advanced metrics ───────────────────────────
            "wRCp":  _compact(get_metric(row, "wRC+")),    # wRC+ (100 = league avg)
            "wOBA":  _compact(get_metric(row, "wOBA")),    # weighted on-base avg
            "ISO":   _compact(get_metric(row, "ISO")),     # isolated power (SLG - AVG)
            "BBp":   _compact(get_metric(row, "BB%")),     # walk rate (very stable)
            "Kp":    _compact(get_metric(row, "K%")),      # strikeout rate
            "BABIP": _compact(get_metric(row, "BABIP")),   # regression signal
            "LDp":   _compact(get_metric(row, "LD%")),     # line-drive rate
            "GBp":   _compact(get_metric(row, "GB%")),     # ground-ball rate
            "FBp":   _compact(get_metric(row, "FB%")),     # fly-ball rate
            "Hardp": _compact(get_metric(row, "Hard%")),   # hard-hit rate (FG definition)
            "Brlp":  _compact(get_metric(row, "Barrel%")), # barrel rate (Statcast-via-FG)
            "Spd":   _compact(get_metric(row, "Spd")),     # speed score
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
            "IP":   _compact(get_metric(row, "IP"),      1),
            "H":    _compact(get_metric(row, "H"),       1),
            "ER":   _compact(get_metric(row, "ER"),      1),
            "HR":   _compact(get_metric(row, "HR"),      1),
            "BB":   _compact(get_metric(row, "BB"),      1),
            "SO":   _compact(get_metric(row, "SO"),      1),
            "W":    _compact(get_metric(row, "W"),       1),
            "L":    _compact(get_metric(row, "L"),       1),
            "SV":   _compact(get_metric(row, "SV"),      1),
            "HD":   _compact(get_metric(row, "HLD", "HD"), 1),
            "BS":   _compact(get_metric(row, "BS"),      1),
            "QS":   _compact(get_metric(row, "QS"),      1),
            "GS":   _compact(get_metric(row, "GS"),      1),
            "ERA":  _compact(era  if era  > 0 else 99.0),
            "WHIP": _compact(whip if whip > 0 else 9.9),
            "WAR":  _compact(get_metric(row, "WAR")),
            # ── Phase 1: FanGraphs advanced ERA estimators ────────────────────
            "FIP":   _compact(fip  if fip  > 0 else 0.0),  # fielding-independent ERA
            "xFIP":  _compact(xfip if xfip > 0 else 0.0), # xFIP (normalizes HR/FB)
            "SIERA": _compact(get_metric(row, "SIERA")),   # best ERA predictor
            # Stuff / swing metrics
            "SwStp": _compact(get_metric(row, "SwStr%")),  # swinging-strike rate
            "CSWp":  _compact(get_metric(row, "CSW%")),    # called strikes + whiffs
            # Batted ball profile
            "GBp":   _compact(get_metric(row, "GB%")),     # ground-ball rate
            "LDp":   _compact(get_metric(row, "LD%")),     # line-drive rate
            "FBp":   _compact(get_metric(row, "FB%")),     # fly-ball rate
            # Component rates
            "K9":    _compact(get_metric(row, "K/9")),     # K per 9 innings
            "BB9":   _compact(get_metric(row, "BB/9")),    # BB per 9 innings
            "KBBp":  _compact(get_metric(row, "K-BB%")),   # best single ERA predictor
            # Regression signals
            "HRFBp": _compact(get_metric(row, "HR/FB")),   # HR/fly-ball (mean-reverts ~10%)
            "LOBp":  _compact(get_metric(row, "LOB%")),    # strand rate (mean-reverts ~72%)
            "BABIPp":_compact(get_metric(row, "BABIP")),   # BABIP allowed
        }

    return hitters, pitchers


def _load_reference_from_pybaseball(season):
    hitters_df  = batting_stats_bref(season)
    pitchers_df = pitching_stats_bref(season)
    h_war_df    = bwar_bat()
    p_war_df    = bwar_pitch()
    h_war_df    = h_war_df[h_war_df["year_ID"] == season]
    p_war_df    = p_war_df[p_war_df["year_ID"] == season]

    hitters  = {}
    pitchers = {}

    for row in hitters_df.to_dict(orient="records"):
        name = normalize_name(row.get("Name", ""))
        if not name:
            continue
        e = hitters.setdefault(name, {
            "display_name": row.get("Name", ""),
            "PA": 0.0, "H": 0.0, "2B": 0.0, "3B": 0.0, "HR": 0.0,
            "R": 0.0, "RBI": 0.0, "SB": 0.0, "BB": 0.0, "SO": 0.0,
            "TB": 0.0, "OPS": 0.0, "WAR": 0.0,
            # Advanced metrics — zero-filled so _build_adv_json never KeyErrors
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
            # Advanced metrics — zero-filled so _build_adv_json never KeyErrors
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

def load_reference_db():
    """
    Load prior-season FanGraphs stats from cache or re-fetch via pybaseball.

    Token-optimization: writes compact JSON (no whitespace) and checks cache
    freshness before re-fetching. Cache is valid for the same YEAR-1 season;
    a fresh season's data requires running tools/build_reference_cache.py.
    """
    season = YEAR - 1

    # 1. Try on-disk cache (fastest path — zero network cost)
    if os.path.exists(REFERENCE_DB_PATH):
        try:
            with open(REFERENCE_DB_PATH) as f:
                data = json.load(f)
            if data.get("season") == season:
                REFERENCE_DB.update(data)
                REFERENCE_DB["loaded"] = True
                REFERENCE_DB["source"] = "cache"
                print(f"  Reference DB: loaded from cache ({season})")
                return
        except Exception as e:
            print(f"  Reference DB: cache read failed ({e}), re-fetching...")

    if not PYBASEBALL_AVAILABLE:
        print("  Reference DB: pybaseball not installed — skipping")
        REFERENCE_DB["season"] = season
        REFERENCE_DB["source"] = "pybaseball-unavailable"
        return

    # 2. FanGraphs (primary — JSON API, stable)
    try:
        print(f"  Reference DB: fetching {season} from FanGraphs...")
        hitters, pitchers = _load_reference_from_fangraphs(season)
        data = {
            "season":   season,
            "built_at": datetime.utcnow().isoformat() + "Z",
            "hitters":  hitters,
            "pitchers": pitchers,
            "loaded":   True,
            "source":   "fangraphs",
        }
        REFERENCE_DB.update(data)
        with open(REFERENCE_DB_PATH, "w") as f:
            json.dump(data, f, separators=(",", ":"))  # compact — saves ~15% JSON size
        print(f"  Reference DB: {len(hitters)} hitters, {len(pitchers)} pitchers — saved to cache")
        return
    except Exception as e:
        print(f"  Reference DB: FanGraphs failed ({type(e).__name__}: {e}) — trying BRef...")

    # 3. Baseball Reference (fallback)
    try:
        print(f"  Reference DB: fetching {season} from Baseball Reference...")
        hitters, pitchers = _load_reference_from_pybaseball(season)
        data = {
            "season":   season,
            "built_at": datetime.utcnow().isoformat() + "Z",
            "hitters":  hitters,
            "pitchers": pitchers,
            "loaded":   True,
            "source":   "pybaseball",
        }
        REFERENCE_DB.update(data)
        with open(REFERENCE_DB_PATH, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        print(f"  Reference DB: {len(hitters)} hitters, {len(pitchers)} pitchers — saved to cache")
        return
    except Exception as e:
        print(f"  Reference DB: BRef also failed ({type(e).__name__}: {e})")
        REFERENCE_DB["season"] = season
        REFERENCE_DB["source"] = f"load-failed: {e}"


def load_statcast_db():
    """
    Load Phase 2 Statcast cache (xwOBA, xBA, xSLG, xERA, EV, barrel%, sprint speed).

    Built by: tools/build_statcast_cache.py  (run weekly — TTL 7 days)
    Keyed by MLBAM ID (str) for reliable cross-source matching.
    Also builds _SC_NAME_TO_MLBAM reverse index so ESPN players (which carry
    no proId attribute) can be matched by name.
    Silently skips if the file doesn't exist — briefing degrades gracefully.
    """
    global _SC_NAME_TO_MLBAM
    if not os.path.exists(STATCAST_DB_PATH):
        print("  Statcast DB: cache not found — run tools/build_statcast_cache.py")
        return
    try:
        with open(STATCAST_DB_PATH) as f:
            data = json.load(f)
        STATCAST_DB.update(data)
        STATCAST_DB["loaded"] = True
        age_h = (time.time() - os.path.getmtime(STATCAST_DB_PATH)) / 3600
        nb, np_ = len(data.get("batters", {})), len(data.get("pitchers", {}))
        print(f"  Statcast DB: loaded {nb} batters, {np_} pitchers ({age_h:.0f}h old)")

        # Build name → MLBAM reverse index from both batter and pitcher entries
        idx: dict[str, str] = {}
        for mlbam, entry in data.get("batters",  {}).items():
            nm = normalize_name(entry.get("name", ""))
            if nm:
                idx[nm] = str(mlbam)
        for mlbam, entry in data.get("pitchers", {}).items():
            nm = normalize_name(entry.get("name", ""))
            if nm:
                idx[nm] = str(mlbam)
        _SC_NAME_TO_MLBAM = idx
        print(f"  Statcast DB: built name→MLBAM index ({len(idx)} entries)")
    except Exception as e:
        print(f"  Statcast DB: load failed ({e})")


def load_projection_db():
    """
    Load Phase 3 Steamer/ZiPS consensus projection cache.

    Built by: tools/build_projection_cache.py  (run weekly — TTL 7 days)
    Keyed by normalized player name for cross-source matching.
    Silently skips if the file doesn't exist — briefing degrades gracefully to
    prior-season stats as the fallback (same behavior as before Phase 3).
    """
    if not os.path.exists(PROJECTION_DB_PATH):
        print("  Projection DB: cache not found — run tools/build_projection_cache.py")
        return
    try:
        with open(PROJECTION_DB_PATH) as f:
            data = json.load(f)
        PROJECTION_DB.update(data)
        PROJECTION_DB["loaded"] = True
        age_h = (time.time() - os.path.getmtime(PROJECTION_DB_PATH)) / 3600
        nh, np_ = len(data.get("hitters", {})), len(data.get("pitchers", {}))
        src = data.get("sources", {})
        print(f"  Projection DB: loaded {nh} hitters, {np_} pitchers ({age_h:.0f}h old) "
              f"[Steamer {src.get('steamer_bat',0)}/{src.get('steamer_pit',0)} · "
              f"ZiPS {src.get('zips_bat',0)}/{src.get('zips_pit',0)}]")
    except Exception as e:
        print(f"  Projection DB: load failed ({e})")


def get_projection_metrics(player) -> dict:
    """
    Return Phase 3 consensus projection metrics for a player, or {} if not found.
    Keys: consensus_pts, steamer_pts, zips_pts, PA/HR/R/RBI/SB (hitters),
          IP/W/SV/HD/ERA/WHIP/SO/GS (pitchers).
    """
    if not PROJECTION_DB["loaded"]:
        return {}
    name = normalize_name(getattr(player, "name", ""))
    db   = PROJECTION_DB["pitchers"] if is_pitcher(player) else PROJECTION_DB["hitters"]
    return db.get(name, {})


def get_reference_metrics(player):
    """Return the FanGraphs reference row for a player (Phase 1 advanced metrics included)."""
    name = normalize_name(getattr(player, "name", ""))
    db   = REFERENCE_DB["pitchers"] if is_pitcher(player) else REFERENCE_DB["hitters"]
    return db.get(name, {})


def get_statcast_metrics(player):
    """
    Return Statcast metrics for a player from the Phase 2 cache.

    Looks up by MLBAM ID (via Statcast name index, since ESPN Player objects
    don't expose proId). Returns {} for rookies / players without 2025 data.
    Keys: xwOBA, xwOBA_gap, xBA, xBA_gap, xSLG, EV, Brlp, HHp, Spd,
          signal (BUY_LOW / SELL_HIGH / NEUTRAL)
    Pitchers: xERA, xERA_gap, xwOBA_a, Brlp_a, HHp_a, EV_a, signal
    """
    if not STATCAST_DB["loaded"]:
        return {}
    mlbam = get_mlbam_id(player)
    if not mlbam:
        return {}
    db = STATCAST_DB["pitchers"] if is_pitcher(player) else STATCAST_DB["batters"]
    return db.get(mlbam, {})


# ── Phase 7: Live 2026 in-season data layer ───────────────────────────────────
# Blended with preseason projections once minimum sample thresholds are met.
# Hitters: ≥ 30 PA.  Pitchers: ≥ 10 IP.
# Cache TTL: 12 hours (refresh twice daily during the season).
_CURRENT_SEASON_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "current_season_cache.json"
)
_CURRENT_SEASON_DB_PATH = os.path.normpath(_CURRENT_SEASON_DB_PATH)
_CURRENT_SEASON_DB: dict = {
    "season":    None,
    "built_at":  None,
    "hitters":   {},
    "pitchers":  {},
    "loaded":    False,
}
_CURRENT_SEASON_MIN_PA  = 30   # minimum PA before including a hitter's 2026 stats
_CURRENT_SEASON_MIN_IP  = 10   # minimum IP before including a pitcher's 2026 stats

# ── Actual FP cache — keyed by normalized player name ─────────────────────────
# Persisted to fp_actual_cache.json with a 30-minute TTL so values survive
# across build_payload() calls within the same day without re-running the
# full stat computation.  Invalidated whenever current_season_cache.json is
# refreshed (12h TTL on that file drives the underlying stats).
_FP_ACTUAL_CACHE_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "fp_actual_cache.json"
))
_FP_ACTUAL_CACHE: dict = {}   # name_key → actual FP float


def load_current_season_db():
    """
    Load live in-season stats from cache or re-fetch from the best available source.

    Three-tier fetch strategy:
      1. FanGraphs direct JSON API (/api/leaders/major-league/data)
         Browser-style headers bypass the 403 block on leaders-legacy.aspx.
         Full stat set: counting stats + wRC+, wOBA, FIP, xFIP, SIERA, K-BB%, SwStr%.
      2. pybaseball batting_stats/pitching_stats (legacy fallback, may 403)
         Kept as a fallback in case FanGraphs API changes its schema.
      3. MLB Stats API (statsapi.mlb.com — always available, free, no auth)
         Counting stats only (no FanGraphs-specific advanced metrics).
         Sufficient for fantasy point computation and season blending.

    Only includes players above the minimum sample threshold (≥30 PA / ≥10 IP).
    Cache TTL: 12 hours. Degrades gracefully to preseason projections on failure.
    """
    import time as _time

    # Check if cache is fresh (< 12 hours old)
    if os.path.exists(_CURRENT_SEASON_DB_PATH):
        try:
            age_h = (_time.time() - os.path.getmtime(_CURRENT_SEASON_DB_PATH)) / 3600
            if age_h < 12:
                with open(_CURRENT_SEASON_DB_PATH) as f:
                    data = json.load(f)
                if data.get("season") == YEAR and data.get("hitters"):
                    _CURRENT_SEASON_DB.update(data)
                    _CURRENT_SEASON_DB["loaded"] = True
                    nh = len(data.get("hitters", {}))
                    np_ = len(data.get("pitchers", {}))
                    print(f"  Current Season DB: loaded {nh} hitters, {np_} pitchers from cache ({age_h:.1f}h old)")
                    return
        except Exception:
            pass

    # ── Helper: parse one row from any source into a standardised hitter dict ──
    def _parse_hitter_row(row: dict) -> dict | None:
        """Accepts rows from FanGraphs API, pybaseball, or MLB Stats API."""
        # Name — FanGraphs uses "Name" or "PlayerName"; MLB Stats uses "fullName"
        name = normalize_name(
            row.get("Name") or row.get("PlayerName") or row.get("fullName") or ""
        )
        if not name:
            return None
        pa = as_float(row.get("PA") or row.get("plateAppearances") or 0)
        if pa < _CURRENT_SEASON_MIN_PA:
            return None
        h  = as_float(row.get("H") or row.get("hits") or 0)
        d  = as_float(row.get("2B") or row.get("doubles") or 0)
        t  = as_float(row.get("3B") or row.get("triples") or 0)
        hr = as_float(row.get("HR") or row.get("homeRuns") or 0)
        return {
            "name":  name,
            "PA":    _compact(pa, 1),
            "AB":    _compact(as_float(row.get("AB") or row.get("atBats") or 0), 1),
            "G":     _compact(as_float(row.get("G") or row.get("gamesPlayed") or 0), 1),
            "H":     _compact(h, 1),
            "2B":    _compact(d, 1),
            "3B":    _compact(t, 1),
            "HR":    _compact(hr, 1),
            "R":     _compact(as_float(row.get("R") or row.get("runs") or 0), 1),
            "RBI":   _compact(as_float(row.get("RBI") or row.get("rbi") or 0), 1),
            "SB":    _compact(as_float(row.get("SB") or row.get("stolenBases") or 0), 1),
            "BB":    _compact(as_float(row.get("BB") or row.get("baseOnBalls") or 0), 1),
            "SO":    _compact(as_float(row.get("SO") or row.get("K") or row.get("strikeOuts") or 0), 1),
            "TB":    _compact(
                as_float(row.get("TB") or row.get("totalBases") or 0) or (h + d + 2 * t + 3 * hr), 1
            ),
            "OPS":   _compact(as_float(row.get("OPS") or 0)),
            # FanGraphs-only advanced metrics (absent from MLB Stats API fallback, stored as 0)
            "wRCp":  _compact(as_float(row.get("wRC+") or row.get("wRCp") or 0)),
            "wOBA":  _compact(as_float(row.get("wOBA") or 0)),
            "BABIP": _compact(as_float(row.get("BABIP") or 0)),
            "Kp":    _compact(as_float(row.get("K%") or row.get("Kp") or 0)),
            "BBp":   _compact(as_float(row.get("BB%") or row.get("BBp") or 0)),
            "ISO":   _compact(as_float(row.get("ISO") or 0)),
        }

    def _parse_pitcher_row(row: dict) -> dict | None:
        """Accepts rows from FanGraphs API, pybaseball, or MLB Stats API."""
        name = normalize_name(
            row.get("Name") or row.get("PlayerName") or row.get("fullName") or ""
        )
        if not name:
            return None
        ip = as_float(row.get("IP") or row.get("inningsPitched") or 0)
        if ip < _CURRENT_SEASON_MIN_IP:
            return None
        era  = as_float(row.get("ERA") or row.get("era") or 0)
        whip = as_float(row.get("WHIP") or row.get("whip") or 0)
        fip  = as_float(row.get("FIP") or 0)
        return {
            "name": name,
            "IP":    _compact(ip, 1),
            "G":     _compact(as_float(row.get("G") or row.get("gamesPlayed") or 0), 1),
            "H":     _compact(as_float(row.get("H") or row.get("hits") or 0), 1),
            "ER":    _compact(as_float(row.get("ER") or row.get("earnedRuns") or 0), 1),
            "HR":    _compact(as_float(row.get("HR") or row.get("homeRuns") or 0), 1),
            "BB":    _compact(as_float(row.get("BB") or row.get("baseOnBalls") or 0), 1),
            "SO":    _compact(as_float(row.get("SO") or row.get("K") or row.get("strikeOuts") or 0), 1),
            "W":     _compact(as_float(row.get("W") or row.get("wins") or 0), 1),
            "L":     _compact(as_float(row.get("L") or row.get("losses") or 0), 1),
            "SV":    _compact(as_float(row.get("SV") or row.get("saves") or 0), 1),
            "HD":    _compact(as_float(row.get("HLD") or row.get("HD") or row.get("holds") or 0), 1),
            "GS":    _compact(as_float(row.get("GS") or row.get("gamesStarted") or 0), 1),
            "QS":    _compact(as_float(row.get("QS") or row.get("qualityStarts") or 0), 1),
            "ERA":   _compact(era if era > 0 else 99.0),
            "WHIP":  _compact(whip if whip > 0 else 9.9),
            # FanGraphs-only advanced metrics (absent from MLB Stats API fallback)
            "FIP":   _compact(fip if fip > 0 else 0.0),
            "xFIP":  _compact(as_float(row.get("xFIP") or 0)),
            "SIERA": _compact(as_float(row.get("SIERA") or 0)),
            "KBBp":  _compact(as_float(row.get("K-BB%") or row.get("KBBp") or 0)),
            "SwStp": _compact(as_float(row.get("SwStr%") or row.get("SwStp") or 0)),
        }

    # ── Tier 1: FanGraphs direct JSON API (bypasses the 403-blocked legacy endpoint) ──
    # Same browser-header pattern as the working projection cache.
    # Returns full FanGraphs stat set including wRC+, wOBA, FIP, xFIP, SIERA, K-BB%, SwStr%.
    def _fetch_fg_direct(stats_type: str) -> list:
        """
        Fetch current-season stats from FanGraphs' new JSON API.
        stats_type: 'bat' | 'pit'

        Uses the /api/leaders/major-league/data endpoint (not the deprecated
        leaders-legacy.aspx that pybaseball targets and which returns 403 in 2025+).
        Fetches type=8 (standard/dashboard) which includes counting stats + key rates.
        """
        try:
            import requests as _req, certifi as _cert
        except ImportError:
            raise RuntimeError("requests/certifi not installed")

        _FG_HEADERS = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer":         "https://www.fangraphs.com/leaders.aspx",
        }

        merged: dict[str, dict] = {}  # name → merged row across stat types

        # Fetch two stat groups: standard (type=8) + advanced (type=2)
        # type=8 = dashboard (counting stats + wRC+ for bat, ERA/WHIP/FIP for pit)
        # type=2 = advanced (wOBA, BABIP, K%, BB%, ISO for bat; xFIP, SIERA, SwStr% for pit)
        for fg_type in (8, 2):
            url = (
                "https://www.fangraphs.com/api/leaders/major-league/data"
                f"?age=&pos=all&stats={stats_type}&lg=all&qual=0"
                f"&season={YEAR}&season1={YEAR}&startdate=&enddate=&month=0"
                f"&hand=&team=0&pageitems=2000&pagenum=1&ind=0&rost=0"
                f"&players=0&type={fg_type}&postseason=&sortdir=default&sortstat=WAR"
            )
            try:
                resp = _req.get(url, headers=_FG_HEADERS, timeout=20,
                                verify=_cert.where())
                resp.raise_for_status()
                ct  = resp.headers.get("Content-Type", "")
                raw = resp.text.strip()
                if raw.startswith("<!") or "text/html" in ct:
                    print(f"  FG direct [{stats_type}/type={fg_type}]: received HTML — skipping")
                    continue
                data = resp.json()
                rows = data.get("data", data) if isinstance(data, dict) else list(data)
                for row in rows:
                    # Normalise name key: API uses "PlayerName"; pybaseball uses "Name"
                    if "PlayerName" in row and "Name" not in row:
                        row["Name"] = row["PlayerName"]
                    nm = row.get("Name") or row.get("PlayerName") or ""
                    if nm:
                        existing = merged.get(nm, {})
                        existing.update(row)   # later type overwrites only new keys
                        merged[nm] = existing
                print(f"  FG direct [{stats_type}/type={fg_type}]: {len(rows)} players")
            except Exception as _e:
                print(f"  FG direct [{stats_type}/type={fg_type}]: {type(_e).__name__}: {_e}")
                continue

        return list(merged.values())

    # ── Tier 2: pybaseball (legacy fallback — may still work on some machines) ──
    def _fetch_pybaseball(stats_type: str):
        """Returns a pandas DataFrame or raises."""
        if not PYBASEBALL_AVAILABLE:
            raise RuntimeError("pybaseball not available")
        if stats_type == "bat":
            return batting_stats(YEAR, YEAR, qual=0)
        return pitching_stats(YEAR, YEAR, qual=0)

    # ── Tier 3: MLB Stats API fallback (always available, no rate-limiting) ──
    # Provides all counting stats needed to compute fantasy points.
    # Does NOT provide wRC+, wOBA, FIP, xFIP, SIERA, K%, BB%, SwStr%
    # (those come from the reference/Statcast caches built weekly).
    def _fetch_mlb_stats_api(stats_type: str) -> list:
        """
        Fetch current-season counting stats from the free MLB Stats API.
        stats_type: 'bat' (hitting) | 'pit' (pitching)
        """
        import requests as _req, certifi as _cert
        group = "hitting" if stats_type == "bat" else "pitching"
        url = (
            f"https://statsapi.mlb.com/api/v1/stats"
            f"?stats=season&group={group}&season={YEAR}&sportId=1"
            f"&limit=2000&offset=0&sortStat="
            f"{'plateAppearances' if stats_type == 'bat' else 'inningsPitched'}"
            f"&order=desc"
        )
        resp = _req.get(url, timeout=20, verify=_cert.where())
        resp.raise_for_status()
        data = resp.json()
        rows = []
        for stat_block in data.get("stats", []):
            for split in stat_block.get("splits", []):
                player_info = split.get("player", {})
                stat        = split.get("stat", {})
                stat["fullName"] = player_info.get("fullName", "")
                rows.append(stat)
        print(f"  MLB Stats API [{group}]: {len(rows)} players")
        return rows

    # ── Attempt fetch with tier fallback ──────────────────────────────────────
    def _load_rows(stats_type: str) -> tuple[list, str]:
        """
        Try each tier in order; return (rows_list, source_label).
        rows_list items are plain dicts compatible with _parse_hitter_row /
        _parse_pitcher_row.
        """
        # Tier 1 — FanGraphs direct API
        try:
            rows = _fetch_fg_direct(stats_type)
            if rows:
                return rows, "FanGraphs API"
        except Exception as e1:
            print(f"  Current Season DB [FG direct/{stats_type}]: {e1}")

        # Tier 2 — pybaseball (falls back to legacy endpoint; may hit 403)
        try:
            df = _fetch_pybaseball(stats_type)
            if df is not None and not df.empty:
                return df.to_dict(orient="records"), "pybaseball"
        except Exception as e2:
            print(f"  Current Season DB [pybaseball/{stats_type}]: {e2}")

        # Tier 3 — MLB Stats API
        try:
            rows = _fetch_mlb_stats_api(stats_type)
            if rows:
                return rows, "MLB Stats API"
        except Exception as e3:
            print(f"  Current Season DB [MLB Stats API/{stats_type}]: {e3}")

        return [], "none"

    try:
        print(f"  Current Season DB: fetching live {YEAR} stats...")
        h_rows, h_src = _load_rows("bat")
        p_rows, p_src = _load_rows("pit")

        hitters = {}
        for row in h_rows:
            parsed = _parse_hitter_row(row)
            if parsed:
                hitters[parsed.pop("name")] = parsed

        pitchers = {}
        for row in p_rows:
            parsed = _parse_pitcher_row(row)
            if parsed:
                pitchers[parsed.pop("name")] = parsed

        if not hitters and not pitchers:
            print("  Current Season DB: all sources returned empty — using preseason only")
            return

        data = {
            "season":   YEAR,
            "built_at": datetime.utcnow().isoformat() + "Z",
            "sources":  {"hitters": h_src, "pitchers": p_src},
            "hitters":  hitters,
            "pitchers": pitchers,
        }
        _CURRENT_SEASON_DB.update(data)
        _CURRENT_SEASON_DB["loaded"] = True
        with open(_CURRENT_SEASON_DB_PATH, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        print(
            f"  Current Season DB: {len(hitters)} hitters (≥{_CURRENT_SEASON_MIN_PA} PA) [{h_src}], "
            f"{len(pitchers)} pitchers (≥{_CURRENT_SEASON_MIN_IP} IP) [{p_src}] — saved to cache"
        )

    except Exception as e:
        print(f"  Current Season DB: fetch failed ({type(e).__name__}: {e}) — using preseason only")


def get_current_season_metrics(player) -> dict:
    """
    Return live 2026 in-season stats for a player, or {} if not available
    (player hasn't reached minimum sample threshold yet).
    """
    if not _CURRENT_SEASON_DB.get("loaded"):
        return {}
    name = normalize_name(getattr(player, "name", ""))
    db   = _CURRENT_SEASON_DB["pitchers"] if is_pitcher(player) else _CURRENT_SEASON_DB["hitters"]
    return db.get(name, {})


def get_inseason_blend_weight() -> float:
    """
    Return the weight to give live 2026 stats vs preseason projections.
    Increases as the season progresses: 15% in week 2 → 70% by July.
    Uses day-of-season (April 1 = day 1) as the basis.
    """
    try:
        # Approximate MLB opening day — varies by year; late March is typical.
        # Using March 27 as a safe default; adjust if season starts later.
        season_start = datetime(YEAR, 3, 27)
        days_in = max(0, (datetime.now() - season_start).days)
        # Linear ramp: 0% preseason → 15% at 14 days → 50% at 75 days → 70% at 120 days
        if days_in <= 7:
            return 0.10
        elif days_in <= 21:
            return 0.20
        elif days_in <= 45:
            return 0.35
        elif days_in <= 75:
            return 0.50
        elif days_in <= 105:
            return 0.62
        else:
            return 0.70
    except (TypeError, ValueError, AttributeError) as e:
        print(f"  Warning: blend weight calculation failed: {e}")
        return 0.15


# ══════════════════════════════════════════════════════════════════════════════
# PROJECTED FANTASY POINTS
# ══════════════════════════════════════════════════════════════════════════════

def _hitter_pts_from_stats(m):
    score  = BATTING_SCORING["R"]   * get_metric(m, "R")
    score += BATTING_SCORING["HR"]  * get_metric(m, "HR")
    score += BATTING_SCORING["TB"]  * get_metric(m, "TB")
    score += BATTING_SCORING["RBI"] * get_metric(m, "RBI")
    score += BATTING_SCORING["BB"]  * get_metric(m, "BB")
    score += BATTING_SCORING["SB"]  * get_metric(m, "SB")
    score += BATTING_SCORING["K"]   * get_metric(m, "SO", "K")
    rbi = get_metric(m, "RBI")
    pa  = get_metric(m, "PA")
    score += BATTING_SCORING["GWRBI"] * (rbi * 0.02)
    score += BATTING_SCORING["GSHR"]  * (pa  * 0.003)
    return score

def _pitcher_pts_from_stats(m):
    sv = get_metric(m, "SV")
    hd = get_metric(m, "HD", "HLD")
    gs = get_metric(m, "GS")
    ip = get_metric(m, "IP")
    so = get_metric(m, "SO", "K")
    qs = get_metric(m, "QS") if get_metric(m, "QS") > 0 else gs * 0.55
    score  = PITCHING_SCORING["IP"]  * ip
    score += PITCHING_SCORING["H"]   * get_metric(m, "H")
    score += PITCHING_SCORING["ER"]  * get_metric(m, "ER")
    score += PITCHING_SCORING["HR"]  * get_metric(m, "HR")
    score += PITCHING_SCORING["BB"]  * get_metric(m, "BB")
    score += PITCHING_SCORING["K"]   * so
    score += PITCHING_SCORING["QS"]  * qs
    score += PITCHING_SCORING["W"]   * get_metric(m, "W")
    score += PITCHING_SCORING["L"]   * get_metric(m, "L")
    score += PITCHING_SCORING["SV"]  * sv
    score += PITCHING_SCORING["BS"]  * get_metric(m, "BS")
    score += PITCHING_SCORING["HD"]  * hd
    score += PITCHING_SCORING["SVHD"] * (sv + hd)
    score += PITCHING_SCORING["CG"] * (gs * 0.01)
    score += PITCHING_SCORING["SO"] * (gs * 0.001)
    return score

def _apply_regression_corrections(player, pts: float) -> float:
    """
    Apply statistical regression corrections to projected fantasy points.

    Hitters:
      - High BABIP (luck-driven hot start) → discount pts
      - xwOBA gap (outperforming expected) → discount pts
      - xwOBA gap (underperforming expected) → boost pts (buy-low)

    Pitchers:
      - High LOB% (strand rate) → discount pts (ERA will rise)
      - Low LOB% (depressed strand rate) → boost pts (ERA will fall)
      - Low HR/FB% → discount pts (HRs will normalize upward)
      - High HR/FB% → boost pts (HRs will normalize downward)

    Only applied when pts > 5 and reference/statcast data is available.
    Never adjusts more than ±18% to avoid overcorrecting small samples.
    """
    if pts <= 5:
        return pts

    ref = get_reference_metrics(player)
    sc  = get_statcast_metrics(player)
    multiplier = 1.0

    if is_pitcher(player):
        # ── Pitcher LOB% regression ──────────────────────────────────────────
        # LOB% mean-reverts to ~72-73%.  Extreme values signal pending ERA change.
        if ref:
            lob = get_metric(ref, "LOBp")   # stored as decimal, e.g. 0.78
            hrfb = get_metric(ref, "HRFBp") # HR/FB rate, e.g. 0.10
            if lob > 0:
                lob_pct = lob * 100 if lob < 1 else lob
                if lob_pct > 80:
                    multiplier *= 0.90    # ERA will rise — heavily penalize
                elif lob_pct > 77:
                    multiplier *= 0.95    # mild regression likely
                elif lob_pct < 65:
                    multiplier *= 1.06    # improvement pending
                elif lob_pct < 68:
                    multiplier *= 1.03
            if hrfb > 0:
                hrfb_pct = hrfb * 100 if hrfb < 1 else hrfb
                if hrfb_pct < 7:
                    multiplier *= 0.93    # HR rate will normalize up → more ER
                elif hrfb_pct < 8.5:
                    multiplier *= 0.97
                elif hrfb_pct > 15:
                    multiplier *= 1.05    # HR rate will normalize down → fewer ER
                elif hrfb_pct > 13:
                    multiplier *= 1.02
        # ── Pitcher xERA signal ──────────────────────────────────────────────
        if sc:
            xera_gap = sc.get("xERA_gap", 0.0)  # positive = xERA > ERA (sell/regression risk)
            if xera_gap <= -1.5:
                multiplier *= 1.06    # ERA artificially inflated vs xERA — buy low
            elif xera_gap <= -0.8:
                multiplier *= 1.03
            elif xera_gap >= 1.5:
                multiplier *= 0.92    # ERA artificially deflated vs xERA — sell high
            elif xera_gap >= 0.8:
                multiplier *= 0.96
    else:
        # ── Hitter BABIP regression ───────────────────────────────────────────
        # BABIP mean-reverts to ~.295-.310.  Sprint speed raises the sustainable floor.
        if ref:
            babip = get_metric(ref, "BABIP")  # stored as decimal, e.g. 0.32
            sprint = get_metric(ref, "Spd")   # FanGraphs speed score (not ft/s)
            sc_spd = sc.get("Spd", 0) if sc else 0
            has_elite_speed = (sc_spd >= 28 or sprint >= 6.5)  # top-tier speed
            if babip > 0:
                babip_val = babip if babip < 1 else babip / 1000
                if babip_val > 0.410 and not has_elite_speed:
                    multiplier *= 0.80    # severe BABIP luck — strong regression
                elif babip_val > 0.370 and not has_elite_speed:
                    multiplier *= 0.88    # notable overperformance
                elif babip_val > 0.345 and not has_elite_speed:
                    multiplier *= 0.94    # mild overperformance
                elif babip_val < 0.255:
                    multiplier *= 1.05    # underperforming BABIP — improvement likely
        # ── Hitter xwOBA gap correction ──────────────────────────────────────
        if sc:
            xwoba_gap = sc.get("xwOBA_gap", 0.0)  # positive = xwOBA > wOBA (buy)
            xwoba     = sc.get("xwOBA", 0.0)
            if xwoba > 0:
                if xwoba_gap >= 0.060:
                    multiplier *= 1.08    # strong buy-low: true talent >> results
                elif xwoba_gap >= 0.035:
                    multiplier *= 1.04
                elif xwoba_gap <= -0.060:
                    multiplier *= 0.88    # strong sell-high: results >> true talent
                elif xwoba_gap <= -0.035:
                    multiplier *= 0.94

    # Cap at ±18% to prevent overcorrecting small samples
    multiplier = max(0.82, min(1.18, multiplier))
    return pts * multiplier

def get_projected_pts(player):
    """
    Season-total projected fantasy points for a player.

    Source priority (weighted blend):
      1. Live 2026 in-season stats (if ≥ sample threshold met) — blended with preseason
      2. ESPN live projection — primary preseason anchor
      3. Steamer+ZiPS consensus — secondary preseason anchor
      4. Prior-season FanGraphs stats — fallback
      5. ESPN avg × 26 — last resort

    All paths apply _apply_regression_corrections() for BABIP/xwOBA/LOB%/HR-FB% adjustment.
    """
    espn_proj    = as_float(safe_get(player, "projected_total_points", default=0))
    proj_m       = get_projection_metrics(player)
    steamer_pts  = as_float(proj_m.get("consensus_pts", 0)) if proj_m else 0.0

    # ── Live 2026 in-season data (Phase 7) ───────────────────────────────────
    cs = get_current_season_metrics(player)
    if cs:
        cs_pts = _pitcher_pts_from_stats(cs) if is_pitcher(player) \
                 else _hitter_pts_from_stats(cs)
        if cs_pts > 5:
            # We have live data. Extrapolate to full season, then blend.
            pa_or_ip = get_metric(cs, "PA") if not is_pitcher(player) else get_metric(cs, "IP")
            # Extrapolate partial season to full season
            if not is_pitcher(player):
                full_season_pa = 550.0
                scale = full_season_pa / max(pa_or_ip, 1)
            else:
                full_season_ip = 180.0
                scale = full_season_ip / max(pa_or_ip, 1)
            cs_full = cs_pts * min(scale, 6.0)  # cap scale at 6x to prevent tiny sample explosion

            # Determine preseason baseline (ESPN > Steamer > ref)
            if espn_proj > 5 and steamer_pts > 5:
                preseason = 0.60 * espn_proj + 0.40 * steamer_pts
            elif espn_proj > 5:
                preseason = espn_proj
            elif steamer_pts > 5:
                preseason = steamer_pts
            else:
                metrics = get_reference_metrics(player)
                preseason = (_pitcher_pts_from_stats(metrics) if is_pitcher(player)
                             else _hitter_pts_from_stats(metrics)) if metrics else 0.0

            if preseason > 5:
                w = get_inseason_blend_weight()
                blended = w * cs_full + (1 - w) * preseason
                return _apply_regression_corrections(player, blended)
            elif cs_full > 5:
                return _apply_regression_corrections(player, cs_full)

    # ── Preseason-only path (no in-season data yet) ───────────────────────────
    if espn_proj > 5 and steamer_pts > 5:
        raw_pts = 0.60 * espn_proj + 0.40 * steamer_pts
        return _apply_regression_corrections(player, raw_pts)

    if espn_proj > 5:
        return _apply_regression_corrections(player, espn_proj)

    if steamer_pts > 5:
        return _apply_regression_corrections(player, steamer_pts)

    metrics = get_reference_metrics(player)
    if metrics:
        pts = _pitcher_pts_from_stats(metrics) if is_pitcher(player) \
              else _hitter_pts_from_stats(metrics)
        if pts > 5:
            return _apply_regression_corrections(player, pts)

    avg = as_float(safe_get(player, "avg_points", default=0))
    if avg > 0:
        return avg * 26
    return 0.0


def get_weekly_projected_pts(player) -> float:
    """
    Per-scoring-period (weekly) projected points.

    Used for:
      • best_lineup_pts(weekly=True)  — best lineup this week
      • compute_power_rankings  — weekly ceiling component

    Logic:
      - IL/injured players return 0.0 (can't contribute this week).
      - Primary source: ESPN ``projected_avg_points`` (per-period, updated weekly).
      - Fallback:  season projection ÷ 26 scoring periods.
      - Starting pitchers are then multiplied by get_two_start_multiplier()
        (0.30× no starts, 1.0× one start, 1.75× two starts).
      - Relievers and hitters use a multiplier of 1.0.
    """
    slot   = get_lineup_slot(player)
    status = get_player_status(player)
    on_il  = slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", "")
    if on_il:
        return 0.0  # unavailable this week; don't project any contribution

    # ESPN's per-period projection — most accurate for the current week
    weekly = as_float(safe_get(player, "projected_avg_points", default=0))
    if weekly <= 0:
        # Fallback: derive weekly rate from season projection
        season = get_projected_pts(player)
        weekly = season / 26.0 if season > 0 else 0.0

    # Starting pitchers: scale by scheduled starts this week
    weekly *= get_two_start_multiplier(player)
    return max(0.0, weekly)


# ══════════════════════════════════════════════════════════════════════════════
# MARKET CONTEXT  —  replacement levels + pool depth
# ══════════════════════════════════════════════════════════════════════════════

def build_market_context(league):
    all_players = {p.name: p for t in league.teams for p in t.roster}
    try:
        for p in league.free_agents(size=500):
            all_players.setdefault(p.name, p)
    except Exception as e:
        print(f"  Warning: free_agents() call failed (non-fatal): {e}")

    by_pos = {}
    for player in all_players.values():
        pts  = get_projected_pts(player)
        for pos in set(get_player_slots(player)):
            if pos in ("BE", "BENCH", "IL", "IR", "NA", "UTIL", "?"):
                continue
            by_pos.setdefault(pos, []).append(pts)

    for pos, pts_list in by_pos.items():
        pts_list.sort(reverse=True)
        n      = SLOTS_PER_TEAM.get(pos, N_TEAMS + 1) * N_TEAMS
        lo     = n
        hi     = min(n + REPLACEMENT_BUFFER, len(pts_list))
        if hi > lo:
            tier = pts_list[lo:hi]
            repl = sum(tier) / len(tier)
        elif pts_list:
            repl = pts_list[-1] * 0.85
        else:
            repl = 0.0
        MARKET["replacement_levels"][pos] = max(0.0, repl)
        MARKET["pool_above_repl"][pos] = sum(
            1 for p in pts_list if p > repl * 1.05
        )

    # ── Role-split pitcher replacement levels ────────────────────────────────
    # The pooled "P" slot mixes starters and relievers, which drags RP values
    # down (the deep SP pool lowers the bar) and inflates SP values (closers
    # inflate the RP end).  Fix: compute separate pools using prior-season GS.
    sp_pts: list = []
    rp_pts: list = []
    for player in all_players.values():
        if not is_pitcher(player):
            continue
        pts = get_projected_pts(player)
        if is_starter_role(player):
            sp_pts.append(pts)
        elif is_reliever_role(player):
            rp_pts.append(pts)

    def _repl_for(pts_list, slots_per_team):
        pts_list = sorted(pts_list, reverse=True)
        n  = slots_per_team * N_TEAMS
        lo = n
        hi = min(n + REPLACEMENT_BUFFER, len(pts_list))
        if hi > lo:
            tier = pts_list[lo:hi]
            return sum(tier) / len(tier)
        return pts_list[-1] * 0.85 if pts_list else 0.0

    MARKET["sp_repl"] = max(0.0, _repl_for(sp_pts, SLOTS_PER_TEAM.get("SP", 4)))
    MARKET["rp_repl"] = max(0.0, _repl_for(rp_pts, SLOTS_PER_TEAM.get("RP", 3)))

    # Hold depth — count of RPs whose projected pts clears the RP replacement bar
    # with meaningful cushion; used by the hold-scarcity bonus in scoring.
    hold_threshold = MARKET["rp_repl"] * 1.15
    MARKET["hold_depth"] = sum(
        1 for p in all_players.values()
        if is_reliever_role(p) and get_projected_pts(p) > hold_threshold
    )

    # Fallback replacement level — minimum non-zero positional repl across all
    # positions.  Used by get_replacement_level() as a last resort so the player
    # modal never displays "Replacement Lvl: 0.0" for players with ambiguous roles
    # or eligible slots that don't match any specific MARKET key.
    nonzero_repls = [v for v in MARKET["replacement_levels"].values() if v > 0]
    MARKET["fallback_repl"] = min(nonzero_repls) if nonzero_repls else 0.0

    MARKET["ready"] = True


def get_replacement_level(player):
    """
    Return the most-favorable replacement level for this player.
    For pitchers with confirmed role data we use the role-split levels
    (sp_repl / rp_repl) which avoids the pooled-P mixed-signal bias.

    Falls back to MARKET["fallback_repl"] (min non-zero positional repl)
    when no specific level can be matched — prevents 0.0 from leaking into
    the player modal's "Replacement Lvl" display and inflating VAR values.
    """
    if is_pitcher(player):
        sp = MARKET["sp_repl"]
        rp = MARKET["rp_repl"]
        if sp > 0 or rp > 0:
            if is_starter_role(player) and sp > 0:
                return sp
            if is_reliever_role(player) and rp > 0:
                return rp
            # Pitcher with ambiguous role — use whichever role-split level is
            # available (conservative: take the lower of the two non-zero values)
            nonzero_p = [v for v in (sp, rp) if v > 0]
            if nonzero_p:
                return min(nonzero_p)

    # Hitters (and pitchers without role-split data) — use positional pool
    best = None
    for pos in get_player_slots(player):
        repl = MARKET["replacement_levels"].get(pos)
        if repl is not None and repl > 0:
            best = repl if best is None else min(best, repl)

    if best is not None and best > 0:
        return best

    # Ultimate fallback: use the minimum non-zero positional replacement level
    # computed across the whole league.  This prevents the player modal from
    # showing "Replacement Lvl: 0.0" for players whose eligible slots don't
    # map to any MARKET key (e.g., generic "P" slot pitchers with no role data).
    fb = MARKET.get("fallback_repl", 0.0)
    return fb if fb > 0 else 0.0

def get_scarcity_multiplier(player):
    best = 0.0
    proj = get_projected_pts(player)
    for pos in get_player_slots(player):
        if pos in ("BE", "BENCH", "IL", "IR", "NA", "UTIL", "?"):
            continue
        repl  = MARKET["replacement_levels"].get(pos, 0)
        if proj <= repl:
            continue
        depth = MARKET["pool_above_repl"].get(pos, 50)
        mult  = 1.0 + (1.0 / math.sqrt(depth + 1))
        best  = max(best, mult)

    # ── Hold-scarcity bonus ───────────────────────────────────────────────────
    # Elite setup men (HD ≥ 15 prior season) are rare but conventionally
    # undervalued because they're lumped into the same RP pool as middling arms.
    # If hold depth is thin (fewer than 25 qualifying relievers) apply an
    # additional scarcity premium proportional to how few there are.
    if is_reliever_role(player) and proj > MARKET.get("rp_repl", 0):
        m = get_reference_metrics(player)
        if m and get_metric(m, "HD", "HLD") >= 15:
            hold_d = max(MARKET.get("hold_depth", 1), 1)
            if hold_d < 25:
                hold_bonus = 1.0 + (1.0 / math.sqrt(hold_d))
                best = max(best, hold_bonus)

    # ── Positional scarcity floors ───────────────────────────────────────────
    # Structurally scarce positions get a minimum multiplier regardless of pool
    # depth calculation. C and SS have thin talent pools and few roster slots.
    _SCARCITY_FLOORS = {"C": 1.28, "SS": 1.15, "2B": 1.07}
    for pos in get_player_slots(player):
        floor = _SCARCITY_FLOORS.get(pos, 0.0)
        if floor > 0 and proj > get_replacement_level(player):
            best = max(best, floor)

    return best if best > 0 else 1.0


# ══════════════════════════════════════════════════════════════════════════════
# CORE VALUE MODEL
# ══════════════════════════════════════════════════════════════════════════════

def calculate_base_score_raw(player):
    status  = get_player_status(player)
    slot    = get_lineup_slot(player)

    # Treat as injured/IL if EITHER the lineup slot is IL/IR (player was placed on IL
    # by their manager even if ESPN injuryStatus is blank) OR the injury status is
    # explicitly non-active.  This is critical for players like Gerrit Cole who ESPN
    # may report as "ACTIVE" status while sitting in the IL roster slot.
    on_il = slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", "")

    if on_il:
        # ── Injury severity detection ────────────────────────────────────────
        # Parse ESPN injury description to distinguish season-ending injuries
        # from short-term stints. Severe injuries (TJS, labrum, etc.) get a
        # much heavier discount since the player is likely lost for the season.
        _inj_note = (
            getattr(player, "injuryNote",    "") or
            getattr(player, "injury_note",   "") or
            getattr(player, "injury_status", "") or ""
        ).lower()
        _SEVERE_KW = ("tommy john", "ucl", "labrum", "acl", "mcl", "surgery",
                      "season-ending", "season ending", "60-day", "tjs")
        _LONG_KW   = ("elbow", "shoulder", "knee", "back", "oblique", "60 day")
        _is_severe = any(kw in _inj_note for kw in _SEVERE_KW)
        _is_long   = any(kw in _inj_note for kw in _LONG_KW)

        if _is_severe:
            injury_factor = 0.15   # essentially out for season
        elif _is_long and slot in ("IL", "IR"):
            injury_factor = 0.55   # long IL stint expected
        elif slot in ("IL", "IR"):
            injury_factor = 0.80   # standard IL stint
        else:
            injury_factor = 0.60   # day-to-day
        # Use healthy full-season projection — bypasses the partial/zero ESPN
        # projection that depresses IL players below replacement level.
        proj = get_healthy_projected_pts(player)
        # Two-start multiplier is irrelevant for IL players (they can't start
        # this week regardless), and applying 0.30× on top of injury_factor
        # double-penalises them.  Use 1.0 so injury_factor alone captures the discount.
        weekly_mult = 1.0
    else:
        injury_factor = 1.0
        proj = get_projected_pts(player)
        # Base score = season-long intrinsic value.
        # Weekly start scheduling is ephemeral — a bench SP who isn't starting
        # THIS week is still an elite pitcher with a great season projection.
        # Applying a 0.30× "no-start" penalty here would permanently depress their
        # grade and make top starters look "Droppable" when benched mid-season.
        # The two-start bonus lives ONLY in get_weekly_projected_pts().
        weekly_mult = 1.0

    var = max(0.0, proj - get_replacement_level(player))

    # ── Pitcher quality premium ───────────────────────────────────────────────
    # Pitchers' raw var is structurally compressed vs hitters in this scoring
    # system (fewer counting stats, heavy negative weights on ER/H/BB).  Apply
    # a quality-based premium to top SPs and elite closers so their true draft
    # and waiver value isn't systematically underrepresented relative to hitters.
    pitcher_quality_mult = 1.0
    if is_pitcher(player) and var > 0:
        ref = get_reference_metrics(player)
        sc  = get_statcast_metrics(player)
        if is_starter_role(player) and ref:
            siera = get_metric(ref, "SIERA", "FIP")
            swstr = get_metric(ref, "SwStr%", "SwStrp") * (100 if get_metric(ref, "SwStrp") < 1 else 1)
            ip    = get_metric(ref, "IP")
            k_bb  = get_metric(ref, "KBBp", "K-BB%")
            if siera > 0 and siera < 3.5:
                pitcher_quality_mult += 0.12   # elite: durability premium (IP×3 is huge)
            elif siera > 0 and siera < 4.0:
                pitcher_quality_mult += 0.07
            if swstr > 12:
                pitcher_quality_mult += 0.06   # swing-and-miss stuff = floor
            if ip >= 190:
                pitcher_quality_mult += 0.05   # workhorse: maximises IP×3 benefit
            if k_bb >= 18:
                pitcher_quality_mult += 0.04   # K-BB% excellence
        elif is_reliever_role(player) and ref:
            sv  = get_metric(ref, "SV")
            hd  = get_metric(ref, "HD", "HLD")
            era = get_metric(ref, "ERA")
            if sv >= 25:
                pitcher_quality_mult += 0.14   # locked-in closer (SV×6 + SVHD×2 = 8 pts each)
            elif sv >= 15:
                pitcher_quality_mult += 0.08
            if hd >= 20:
                pitcher_quality_mult += 0.10   # high-hold setup man (HD×5 + SVHD×2 = 7 pts each)
            elif hd >= 10:
                pitcher_quality_mult += 0.05
            if era > 0 and era < 3.0:
                pitcher_quality_mult += 0.05
        pitcher_quality_mult = min(pitcher_quality_mult, 1.35)  # cap at +35%

    return var * get_scarcity_multiplier(player) * injury_factor * weekly_mult * pitcher_quality_mult


def calculate_fit_score_raw(player, team):
    base = calculate_base_score_raw(player)
    proj = get_projected_pts(player)

    # Build positional map using eligible slots (NOT lineup slot).
    # This correctly handles bench players whose lineupSlot == "BE" — their
    # eligible positions are what matter for roster construction analysis.
    # A player on bench is still a roster asset at their eligible positions.
    _SKIP_SLOTS = {"BE", "BENCH", "IL", "IR", "NA", "UTIL", "?"}
    roster_pts_by_pos: dict = {}
    for p in team.roster:
        slot   = get_lineup_slot(p)
        status = get_player_status(p)
        # Skip truly unavailable players (IL/IR or non-ACTIVE injury status)
        if slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", ""):
            continue
        pp = get_projected_pts(p)
        for eligible_pos in get_player_slots(p):
            if eligible_pos not in _SKIP_SLOTS:
                roster_pts_by_pos.setdefault(eligible_pos, []).append(pp)

    upgrade = 0.0
    slots   = get_player_slots(player)

    for pos in slots:
        if pos in _SKIP_SLOTS:
            continue
        current = roster_pts_by_pos.get(pos, [])
        if current:
            weakest = min(current)
            upgrade = max(upgrade, proj - weakest)

    if is_hitter(player):
        # Also consider UTIL — any hitter eligible for UTIL
        util_hitters = [get_projected_pts(p) for p in team.roster
                        if is_hitter(p) and get_lineup_slot(p) == "UTIL"]
        if util_hitters:
            upgrade = max(upgrade, proj - min(util_hitters))

    # Family-level fallback: compare against weakest same-family player on
    # roster (bench included — we want realistic competition baseline)
    if upgrade == 0.0:
        if is_pitcher(player):
            fam_pts = [get_projected_pts(p) for p in team.roster
                       if is_pitcher(p)
                       and get_lineup_slot(p) not in ("IL", "IR")
                       and get_player_status(p) in ("ACTIVE", "NORMAL", "")]
        else:
            fam_pts = [get_projected_pts(p) for p in team.roster
                       if is_hitter(p)
                       and get_lineup_slot(p) not in ("IL", "IR")
                       and get_player_status(p) in ("ACTIVE", "NORMAL", "")]
        if fam_pts:
            upgrade = max(0.0, proj - min(fam_pts))

    upgrade_contribution = max(0.0, upgrade) * 0.40

    # Use ALL non-IL rostered players (including bench) for balance calculation.
    # Excluding bench inflated P/H imbalance flags, causing incorrect bonuses.
    def _avail(p):
        s = get_lineup_slot(p)
        return s not in ("IL", "IR") and get_player_status(p) in ("ACTIVE", "NORMAL", "")

    h_pts = sum(get_projected_pts(p) for p in team.roster if is_hitter(p) and _avail(p))
    p_pts = sum(get_projected_pts(p) for p in team.roster if is_pitcher(p) and _avail(p))
    total = max(h_pts + p_pts, 1.0)

    balance_bonus = 0.0
    if is_pitcher(player) and p_pts / total < 0.40:
        balance_bonus = base * 0.10
    elif is_hitter(player) and h_pts / total < 0.40:
        balance_bonus = base * 0.10

    # Need bonus: count available (non-IL) roster players by eligible position.
    # Cap per-position count at SLOTS_PER_TEAM to avoid over-counting multi-eligible players.
    rostered_pos: dict = {}
    for p in team.roster:
        if not _avail(p):
            continue
        for eligible_pos in get_player_slots(p):
            if eligible_pos not in _SKIP_SLOTS:
                cap = SLOTS_PER_TEAM.get(eligible_pos, 1)
                rostered_pos[eligible_pos] = min(
                    rostered_pos.get(eligible_pos, 0) + 1, cap
                )

    need_multiplier = 0.0
    for pos in slots:
        if pos in _SKIP_SLOTS:
            continue
        expected = SLOTS_PER_TEAM.get(pos, 1)
        actual   = rostered_pos.get(pos, 0)
        if actual < expected:
            deficit = (expected - actual) / expected
            need_multiplier = max(need_multiplier, deficit * 0.12)

    need_bonus = base * need_multiplier
    return base + upgrade_contribution + balance_bonus + need_bonus


def build_score_scaling(league):
    all_players = {p.name: p for t in league.teams for p in t.roster}
    try:
        for p in league.free_agents(size=350):
            all_players.setdefault(p.name, p)
    except Exception:
        pass

    pitchers = [p for p in all_players.values() if is_pitcher(p)]
    hitters  = [p for p in all_players.values() if is_hitter(p)]

    p_base = sorted(calculate_base_score_raw(p) for p in pitchers)
    h_base = sorted(calculate_base_score_raw(p) for p in hitters)

    p_fit, h_fit = [], []
    my_team = get_my_team(league)
    if my_team:
        p_fit = sorted(calculate_fit_score_raw(p, my_team) for p in pitchers)
        h_fit = sorted(calculate_fit_score_raw(p, my_team) for p in hitters)

    def percentile_bounds(scores, lo=2, hi=98):
        if not scores:
            return 0.0, 1.0
        n = len(scores)
        return scores[max(0, int(n * lo / 100))], scores[min(n - 1, int(n * hi / 100))]

    SCALING["p_base_min"], SCALING["p_base_max"] = percentile_bounds(p_base)
    SCALING["h_base_min"], SCALING["h_base_max"] = percentile_bounds(h_base)
    SCALING["p_fit_min"],  SCALING["p_fit_max"]  = percentile_bounds(p_fit) if p_fit else (0.0, 1.0)
    SCALING["h_fit_min"],  SCALING["h_fit_max"]  = percentile_bounds(h_fit) if h_fit else (0.0, 1.0)

    # Legacy unified scale
    all_base = sorted(p_base + h_base)
    SCALING["base_min"], SCALING["base_max"] = percentile_bounds(all_base)
    if p_fit and h_fit:
        SCALING["fit_min"], SCALING["fit_max"] = percentile_bounds(sorted(p_fit + h_fit))

    SCALING["ready"] = True


def _scale(value, vmin, vmax):
    if vmax <= vmin:
        return 50.0
    return max(0.0, min(100.0, 100.0 * (value - vmin) / (vmax - vmin)))

def base_score(player):
    raw = calculate_base_score_raw(player)
    if not SCALING["ready"]:
        return raw
    if is_pitcher(player):
        return _scale(raw, SCALING["p_base_min"], SCALING["p_base_max"])
    return _scale(raw, SCALING["h_base_min"], SCALING["h_base_max"])

def fit_score(player, team):
    raw = calculate_fit_score_raw(player, team)
    if not SCALING["ready"]:
        return raw
    if is_pitcher(player):
        return _scale(raw, SCALING["p_fit_min"], SCALING["p_fit_max"])
    return _scale(raw, SCALING["h_fit_min"], SCALING["h_fit_max"])

def get_value_tier(score):
    """5-level tier label based on family-relative 0-100 score."""
    if score >= 90:  return "Elite"
    if score >= 65:  return "Starter"
    if score >= 40:  return "Depth"
    if score >= 20:  return "Replacement"
    return "Droppable"


# ══════════════════════════════════════════════════════════════════════════════
# WAIVER INTELLIGENCE
# ══════════════════════════════════════════════════════════════════════════════

def _suggest_drop(my_team, pickup):
    """
    Suggest the best player to drop for a given pickup.

    Priority order:
    1. Injured bench players (dead roster weight)
    2. Lowest-value same-family player that doesn't leave a positional gap
    3. Lowest-value same-family player overall (if no safe option exists)

    Also returns a warning string if dropping creates a blueprint gap.
    """
    family      = "P" if is_pitcher(pickup) else "H"
    same_family = [
        p for p in my_team.roster
        if (is_pitcher(p) if family == "P" else is_hitter(p))
    ]
    cross_family = [
        p for p in my_team.roster
        if not (is_pitcher(p) if family == "P" else is_hitter(p))
    ]

    # Detect positional scarcity (C and SS are scarce — don't drop the last one)
    def _is_only_at_pos(p, pos):
        roster_at_pos = [
            x for x in my_team.roster
            if pos in get_player_slots(x) and x.name != p.name
        ]
        return len(roster_at_pos) == 0

    def drop_priority(p):
        slot     = get_lineup_slot(p)
        on_bench = 1 if slot in ("BE", "BENCH") else 0
        on_il    = 1 if slot in ("IL", "IR") else 0
        proj     = get_projected_pts(p)
        status   = get_player_status(p)
        injured  = 1 if status not in ("ACTIVE", "NORMAL", "") else 0
        # Penalty for dropping scarce positions
        scarcity = 0
        for scarce_pos in ("C", "SS"):
            if scarce_pos in get_player_slots(p) and _is_only_at_pos(p, scarce_pos):
                scarcity = 20
                break
        return (on_bench + on_il + injured) * 10 - proj - scarcity

    pool = same_family if same_family else cross_family
    if not pool:
        return "No clear drop"
    pool.sort(key=drop_priority, reverse=True)
    best = pool[0]

    # Check if this drop creates a positional gap — append warning if so
    drop_name = best.name
    for scarce_pos in ("C", "SS", "2B"):
        if scarce_pos in get_player_slots(best) and _is_only_at_pos(best, scarce_pos):
            drop_name += f" ⚠ (only {scarce_pos})"
            break
    return drop_name


# ── Flaw 7: Dynamic closer role tracking ─────────────────────────────────────
# Detects when a known closer has likely lost their role based on ESPN recent
# activity patterns. A closer mass-dropped across the league signals a role loss.
# Cached per-run so we only compute once per briefing.
_CLOSER_ALERT_CACHE: dict = {}   # norm_name → alert_str (computed once per run)

# ── Today's probable starters ────────────────────────────────────────────────
# Populated once early in build_payload() so _player_row() can read it.
# Contains MLBAM IDs (as strings) of pitchers who are probable starters today.
_TODAY_STARTER_IDS: set = set()


def detect_closer_role_change(player, drops_counter: dict) -> str:
    """
    Return a warning string if a known closer appears to have lost their role,
    or an empty string if the role appears stable.

    Uses the drops_counter (from get_recent_activity) to detect mass drops.
    A closer with ≥2 drops in the recent activity window likely lost the role.

    Also checks current Statcast / reference data for SV count to confirm
    this player was actually a closer (≥15 SV last season).
    """
    if not is_pitcher(player):
        return ""
    norm = normalize_name(getattr(player, "name", ""))
    if norm in _CLOSER_ALERT_CACHE:
        return _CLOSER_ALERT_CACHE[norm]

    metrics = get_reference_metrics(player)
    sv = get_metric(metrics, "SV") if metrics else 0
    alert = ""
    if sv >= 15:
        drop_ct = drops_counter.get(norm, 0)
        if drop_ct >= 3:
            alert = (f"⚠ CLOSER ROLE ALERT: {int(drop_ct)} drops this week — "
                     f"likely lost save opps. Verify before rostering.")
        elif drop_ct >= 2:
            alert = (f"⚠ Closer role uncertainty: {int(drop_ct)} league drops — "
                     f"monitor news before committing a roster spot.")
    _CLOSER_ALERT_CACHE[norm] = alert
    return alert


def clear_closer_alert_cache():
    """Call at start of each briefing run to reset per-run cache."""
    _CLOSER_ALERT_CACHE.clear()


def _pickup_reason(player, team, adds_counter, drops_counter=None):
    """
    Returns a list of {"text": str, "tone": str} dicts — up to 6 bullets.
    Tones: "good" (green), "warn" (amber), "bad" (red), "neutral" (gray).
    Also returns a legacy string for backward compat via the "reason" key.
    drops_counter (Flaw 7): dict of norm_name → drop count, used for closer role alerts.
    """
    items    = []
    proj     = get_projected_pts(player)
    repl     = get_replacement_level(player)
    var      = max(0.0, proj - repl)
    scarcity = get_scarcity_multiplier(player)
    metrics  = get_reference_metrics(player)
    sc       = get_statcast_metrics(player)
    norm     = normalize_name(player.name)
    isp      = is_pitcher(player)

    # ── Flaw 7: Closer role change alert (show first if present) ─────────────
    if isp and drops_counter:
        _role_alert = detect_closer_role_change(player, drops_counter)
        if _role_alert:
            items.append({"text": _role_alert, "tone": "warn"})

    # ── 1. Two-start signal (SP only — highest weekly lever) ─────────────────
    if is_starter_role(player) and WEEKLY_STARTS["loaded"] and len(WEEKLY_STARTS["starts"]) >= 60:
        wk = get_weekly_start_count(player)
        if wk >= 2:
            items.append({"text": "2-start week — 1.75× this-week value; single biggest in-season edge", "tone": "good"})
        elif wk == 0:
            items.append({"text": "0 starts this week — hold for future weeks; stream elsewhere now", "tone": "warn"})

    # ── 2. Statcast regression / breakout signal ──────────────────────────────
    signal = sc.get("signal", "") if sc else ""
    if isp:
        xera      = sc.get("xERA", 0) if sc else 0
        xera_gap  = sc.get("xERA_gap", 0) if sc else 0   # positive = xERA > ERA (sell/regression risk)
        if xera_gap <= -1.0 and xera > 0:
            items.append({"text": f"BUY-LOW: xERA {xera:.2f} vs actual ERA — true talent better than results suggest", "tone": "good"})
        elif xera_gap >= 1.0 and xera > 0:
            items.append({"text": f"CAUTION: xERA {xera:.2f} vs ERA — underlying metrics worse than surface stats", "tone": "warn"})
    else:
        xwoba     = sc.get("xwOBA", 0) if sc else 0
        xwoba_gap = sc.get("xwOBA_gap", 0) if sc else 0  # xwOBA − wOBA (positive = buy)
        _sc_season = STATCAST_DB.get("season", YEAR)
        _sc_stale = f" [{_sc_season} data — verify {YEAR} form]" if _sc_season and _sc_season < YEAR else ""
        if xwoba_gap >= 0.030 and xwoba > 0:
            items.append({"text": f"BREAKOUT CANDIDATE: xwOBA {xwoba:.3f} vs actual — true talent exceeds results by {xwoba_gap:+.3f}{_sc_stale}", "tone": "good"})
        elif xwoba_gap <= -0.030 and xwoba > 0:
            items.append({"text": f"REGRESSION RISK: xwOBA {xwoba:.3f} vs actual — luck component detected, decline likely{_sc_stale}", "tone": "warn"})

    # ── 3. Pitcher-specific intel ─────────────────────────────────────────────
    if isp and metrics:
        sv    = get_metric(metrics, "SV")
        hd    = get_metric(metrics, "HD", "HLD")
        gs    = get_metric(metrics, "GS")
        ip    = get_metric(metrics, "IP")
        era   = get_metric(metrics, "ERA")
        fip   = get_metric(metrics, "FIP")
        siera = get_metric(metrics, "SIERA")
        kbb   = get_metric(metrics, "KBBp")  # K-BB% (decimal, e.g. 0.18)
        swstr = get_metric(metrics, "SwStp")  # SwStr% (decimal)
        k9    = get_metric(metrics, "K9")

        # ── Flaw 7: Dynamic closer role staleness check ──────────────────────
        # Cross-reference recent ESPN activity — if a known closer has been
        # mass-dropped this week, they likely lost the role. Flag the warning.
        _player_norm = normalize_name(getattr(player, "name", ""))
        if sv >= 25:
            items.append({"text": f"Proven closer: {int(sv)} SV last season — direct source of SV pts", "tone": "good"})
        elif sv >= 10:
            items.append({"text": f"Save opportunities: {int(sv)} SV last season — closer-in-waiting", "tone": "good"})

        if hd >= 20:
            hold_d = MARKET.get("hold_depth", 99)
            scarcity_note = f"; only {hold_d} qualifying setup men on waivers" if hold_d < 25 else ""
            items.append({"text": f"Elite holds producer: {int(hd)} HLD last season{scarcity_note}. HD=5 pts is massively undervalued — 30 HLD ≈ same pts as elite closer", "tone": "good"})
        elif hd >= 10:
            items.append({"text": f"Solid holds value: {int(hd)} HLD last season — setup role generates 5 pts/hold", "tone": "good"})

        if gs >= 20 and ip > 0:
            era_note = f", ERA {era:.2f}" if era > 0 else ""
            fip_note = f" / FIP {fip:.2f}" if fip > 0 else ""
            items.append({"text": f"Full rotation starter: {int(gs)} GS, {ip:.0f} IP{era_note}{fip_note} — volume + quality combo", "tone": "good" if era > 0 and era <= 4.00 else "neutral"})

        if siera > 0 and siera <= 3.30:
            items.append({"text": f"Elite SIERA {siera:.2f} — best true talent ERA estimator; accounts for batted ball mix", "tone": "good"})
        elif siera > 0 and siera <= 3.80:
            items.append({"text": f"Strong SIERA {siera:.2f} — above-average true talent, sustainable performance likely", "tone": "good"})

        if kbb > 0:
            kbb_pct = kbb * 100 if kbb < 1 else kbb
            if kbb_pct >= 20:
                items.append({"text": f"Elite K-BB% {kbb_pct:.1f}% — dominant command + swing-and-miss combo", "tone": "good"})
            elif kbb_pct >= 15:
                items.append({"text": f"Solid K-BB% {kbb_pct:.1f}% — above-average command profile", "tone": "good"})

        if swstr > 0:
            sw_pct = swstr * 100 if swstr < 1 else swstr
            if sw_pct >= 13:
                items.append({"text": f"Elite SwStr% {sw_pct:.1f}% — top-tier whiff rate; K upside is real", "tone": "good"})

    # ── 4. Hitter-specific intel ──────────────────────────────────────────────
    elif not isp and metrics:
        pa    = get_metric(metrics, "PA")
        hr    = get_metric(metrics, "HR")
        sb    = get_metric(metrics, "SB")
        ops   = get_metric(metrics, "OPS")
        so    = get_metric(metrics, "SO", "K")
        wrc   = get_metric(metrics, "wRCp")   # wRC+ (100 = league avg)
        brl   = get_metric(metrics, "Brlp")   # Barrel% (decimal)
        kpct  = get_metric(metrics, "Kp")     # K% (decimal)
        spd   = get_metric(metrics, "Spd")    # Sprint speed (ft/s) — from reference
        sc_spd = sc.get("Spd", 0) if sc else 0  # Statcast sprint speed

        sprint = sc_spd if sc_spd > 0 else spd

        if pa >= 550:
            items.append({"text": f"Everyday starter: {int(pa)} PA — full lineup volume guarantees counting stat opportunities", "tone": "good"})
        elif pa >= 400:
            items.append({"text": f"Regular playing time: {int(pa)} PA — consistent lineup presence", "tone": "neutral"})

        if wrc >= 140:
            items.append({"text": f"Elite wRC+ {int(wrc)} — top-tier offensive production (100 = league avg)", "tone": "good"})
        elif wrc >= 115:
            items.append({"text": f"Strong wRC+ {int(wrc)} — above-average hitter by best context-neutral metric", "tone": "good"})

        if hr >= 30:
            items.append({"text": f"Plus power: {int(hr)} HR last season — consistent TB contributions", "tone": "good"})
        elif hr >= 20:
            items.append({"text": f"Solid power: {int(hr)} HR last season", "tone": "good"})

        if sb >= 25:
            items.append({"text": f"Speed weapon: {int(sb)} SB last season — SB = +2 pts each, rare asset on wire", "tone": "good"})
        elif sb >= 15:
            items.append({"text": f"Speed contributor: {int(sb)} SB last season", "tone": "good"})

        if brl > 0:
            brl_pct = brl * 100 if brl < 1 else brl
            if brl_pct >= 10:
                items.append({"text": f"Elite barrel rate {brl_pct:.1f}% — top-tier hard contact; HR/XBH upside is real", "tone": "good"})

        if sprint >= 28:
            items.append({"text": f"Elite sprint speed {sprint:.1f} ft/s — top-10% speed; SB upside and excellent BABIP floor", "tone": "good"})

        # Flag the K-rate tax — most ESPN players don't think about this
        if kpct > 0:
            k_pct_val = kpct * 100 if kpct < 1 else kpct
            so_rate = (so / max(pa, 1)) if pa > 0 else 0
            if k_pct_val >= 28 or so_rate > 0.28:
                items.append({"text": f"⚠ High K-rate ({k_pct_val:.0f}%) — each strikeout costs 1 pt; 30% K in 600 PA = −180 pts drag", "tone": "warn"})
            elif k_pct_val <= 15:
                items.append({"text": f"Low K-rate {k_pct_val:.0f}% — avoids the K-tax; hidden edge vs ESPN ADP", "tone": "good"})

    # ── 5. Scarcity + VAR context ─────────────────────────────────────────────
    if scarcity >= 1.7:
        items.append({"text": "Scarce position — very few viable alternatives on the wire; window to add closes fast", "tone": "warn"})
    elif scarcity >= 1.4:
        items.append({"text": "Moderately scarce position — limited depth at this spot", "tone": "neutral"})

    if var >= 200 and not any(i["tone"] == "good" for i in items):
        items.append({"text": f"Elite VAR +{var:.0f} — ranks in top tier vs replacement-level players at this position", "tone": "good"})
    elif var >= 100 and len(items) < 2:
        items.append({"text": f"Strong VAR +{var:.0f} — solid upgrade over freely available replacement", "tone": "good"})

    # ── 6. Market urgency ─────────────────────────────────────────────────────
    add_ct = adds_counter.get(norm, 0)
    if add_ct >= 2:
        items.append({"text": f"Hot on the wire — {add_ct} teams actively targeting him this week; act fast", "tone": "warn"})
    elif add_ct == 1:
        items.append({"text": "Drawing waiver interest from at least one other team", "tone": "neutral"})

    if not items:
        items.append({"text": "Available value above replacement level for this position", "tone": "neutral"})

    # Cap at 6 bullets; prioritize good > warn > neutral > bad
    priority = {"good": 0, "warn": 1, "neutral": 2, "bad": 3}
    items.sort(key=lambda x: priority.get(x["tone"], 2))
    items = items[:6]

    # Legacy string for backward compat
    legacy = "; ".join(i["text"] for i in items[:3])
    return items, legacy


def get_waiver_recommendations(league, my_team, size=500, recent_adds=None, recent_drops=None):
    rostered = {p.name for t in league.teams for p in t.roster}
    # Accept pre-fetched adds/drops to avoid extra ESPN API calls when the caller
    # already retrieved recent activity (e.g. build_payload).
    if recent_adds is None:
        adds, drops, _ = get_recent_activity(league, size=50)
    else:
        adds  = recent_adds
        drops = recent_drops or {}
    clear_closer_alert_cache()   # reset per-run closer alert cache

    try:
        fa_pool = league.free_agents(size=size)
    except Exception:
        fa_pool = []

    available = [p for p in fa_pool if p.name not in rostered]

    scored = []
    for player in available:
        fs = fit_score(player, my_team)
        bs = base_score(player)
        scored.append((fs, bs, player))

    scored.sort(key=lambda x: x[0], reverse=True)

    results     = []
    pitcher_cnt = 0
    hitter_cnt  = 0
    pos_counts  = {}

    # Increased limits: up to 15 hitters + 15 pitchers = 30 total
    MAX_TOTAL   = 30
    MAX_PITCHERS = 15
    MAX_HITTERS  = 15
    MAX_PER_POS  = 4   # max per primary position (was 3)

    for fs, bs, player in scored:
        if len(results) >= MAX_TOTAL:
            break

        if is_pitcher(player):
            if pitcher_cnt >= MAX_PITCHERS:
                continue
        else:
            if hitter_cnt >= MAX_HITTERS:
                continue

        primary_pos = get_player_slots(player)[0]
        if pos_counts.get(primary_pos, 0) >= MAX_PER_POS:
            continue

        reason_items, reason_str = _pickup_reason(player, my_team, adds, drops_counter=drops)

        results.append({
            "player":        player,
            "fit":           fs,
            "base":          bs,
            "var":           max(0.0, get_projected_pts(player) - get_replacement_level(player)),
            "proj_pts":      get_projected_pts(player),
            "repl_pts":      get_replacement_level(player),
            "drop":          _suggest_drop(my_team, player),
            "reason":        reason_str,        # legacy string
            "reason_items":  reason_items,      # structured bullet list
        })

        if is_pitcher(player): pitcher_cnt += 1
        else:                  hitter_cnt  += 1
        pos_counts[primary_pos] = pos_counts.get(primary_pos, 0) + 1

    return results


# ══════════════════════════════════════════════════════════════════════════════
# MATCHUP & WIN PROBABILITY
# ══════════════════════════════════════════════════════════════════════════════

def best_lineup_pts(team, weekly=False):
    """
    Best achievable lineup score for the team.

    weekly=False (default): uses season projections (_proj_pts) — backward-compat.
    weekly=True: uses weekly projections (_weekly_proj_pts); skips IL/injured players
      and weights SPs by their weekly start count.  Use for matchup/power-ranking
      comparisons where what matters is what the team can score THIS week.
    """
    proj_fn = get_weekly_projected_pts if weekly else get_projected_pts
    remaining = list(team.roster)
    total     = 0.0
    for slot in ["C", "1B", "2B", "3B", "SS", "OF", "OF", "OF", "UTIL",
                 "P", "P", "P", "P", "P", "P", "P"]:
        if slot == "UTIL":
            candidates = [p for p in remaining if is_hitter(p)]
        elif slot == "P":
            candidates = [p for p in remaining if is_pitcher(p)]
        else:
            candidates = [p for p in remaining if slot in get_player_slots(p)]
        if weekly:
            # Only players who can actually contribute this week
            candidates = [p for p in candidates if proj_fn(p) > 0]
        if not candidates:
            continue
        best   = max(candidates, key=proj_fn)
        total += proj_fn(best)
        remaining.remove(best)
    return total


def win_probability(league, my_team):
    matchup, me, opp = get_matchup(league, my_team)
    if not matchup:
        return {
            "my_score": 0, "opp_score": 0, "my_proj": 0, "opp_proj": 0,
            "prob": 0.5, "opp_name": "Unknown",
        }

    if matchup.home_team.team_name == me.team_name:
        my_live  = as_float(safe_get(matchup, "home_score", default=0))
        opp_live = as_float(safe_get(matchup, "away_score", default=0))
    else:
        my_live  = as_float(safe_get(matchup, "away_score", default=0))
        opp_live = as_float(safe_get(matchup, "home_score", default=0))

    my_proj  = best_lineup_pts(me, weekly=True) or 0.0
    opp_proj = best_lineup_pts(opp, weekly=True) or 0.0

    my_inj = sum(
        1 for p in me.roster
        if is_active_slot(get_lineup_slot(p))
        and get_player_status(p) not in ("ACTIVE", "NORMAL", "")
    )
    opp_inj = sum(
        1 for p in opp.roster
        if is_active_slot(get_lineup_slot(p))
        and get_player_status(p) not in ("ACTIVE", "NORMAL", "")
    )

    score_margin = my_live - opp_live
    proj_margin  = my_proj - opp_proj
    inj_margin   = (opp_inj - my_inj) * 8.0

    blended  = (0.80 * score_margin) + (0.20 * proj_margin) + inj_margin
    # Cap the exponent to prevent math overflow with extreme margins
    exp_input = max(-100.0, min(100.0, -blended / 12.0))
    raw_prob = 1.0 / (1.0 + math.exp(exp_input))
    prob     = 0.07 + 0.86 * raw_prob

    return {
        "my_score":  my_live,
        "opp_score": opp_live,
        "my_proj":   my_proj,
        "opp_proj":  opp_proj,
        "prob":      prob,
        "opp_name":  opp.team_name,
    }


# ══════════════════════════════════════════════════════════════════════════════
# TEAM SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def team_summary(team):
    base_tot = fit_tot = active_base = active_fit = h_base = p_base = 0.0
    inj_cnt  = 0

    for p in team.roster:
        bs   = base_score(p)
        fs   = fit_score(p, team)
        slot = get_lineup_slot(p)

        base_tot += bs
        fit_tot  += fs

        if is_active_slot(slot):
            active_base += bs
            active_fit  += fs

        if is_pitcher(p): p_base += bs
        else:             h_base += bs

        if get_player_status(p) not in ("ACTIVE", "NORMAL", ""):
            inj_cnt += 1

    lineup_pts        = best_lineup_pts(team)
    weekly_lineup_pts = best_lineup_pts(team, weekly=True)

    return {
        "team_name":         team.team_name,
        "base_total":        base_tot,
        "fit_total":         fit_tot,
        "active_base":       active_base,
        "active_fit":        active_fit,
        "lineup_pts":        lineup_pts,        # season-projection best lineup
        "weekly_lineup_pts": weekly_lineup_pts, # this-week best lineup (primary display)
        "hitter_base":       h_base,
        "pitcher_base":      p_base,
        "injury_count":      inj_cnt,
    }


# ══════════════════════════════════════════════════════════════════════════════
# POWER RANKINGS
# ══════════════════════════════════════════════════════════════════════════════

def compute_power_rankings(league) -> dict:
    """
    Composite power ranking for every team in the league.

    Returns {team_name: rank} where rank=1 is the strongest team.

    ┌─────────────────────────────────────────────────────────────────────────┐
    │ FORMULA                                                                 │
    │                                                                         │
    │  40%  Weekly ceiling                                                    │
    │       best_lineup_pts(weekly=True) — best lineup using per-period projected │
    │       pts, honouring the two-start multiplier for SPs and scoring 0    │
    │       for IL / injured players.  This is what the team can actually     │
    │       score THIS week.                                                  │
    │                                                                         │
    │  35%  Healthy roster depth                                              │
    │       Sum of VAR above replacement for every active (non-IL) rostered  │
    │       player.  Captures bench quality and long-term outlook.           │
    │                                                                         │
    │  25%  IL / stash value                                                  │
    │       Sum of get_stash_score() for every injured or IL-slotted player, │
    │       discounted by a return-timeline factor:                           │
    │         • in IL slot (60-day DL or hard-placed): 0.50×                 │
    │         • non-active status but not in IL slot (DL/DTD):  0.70×        │
    │       This rewards teams that have quality players who will return, but │
    │       penalises holding dead-weight roster spots.                       │
    │                                                                         │
    │  All three components are normalised 0–100 across the league before    │
    │  being combined, so no single component dominates on raw-value scale.  │
    └─────────────────────────────────────────────────────────────────────────┘
    """

    def _normalize(vals: list) -> list:
        if not vals:
            return []
        mn, mx = min(vals), max(vals)
        if mx == mn:
            return [50.0] * len(vals)
        return [(v - mn) / (mx - mn) * 100.0 for v in vals]

    teams = league.teams
    names = [t.team_name for t in teams]

    weekly_scores: list = []
    depth_scores:  list = []
    stash_scores:  list = []

    for team in teams:
        # ── Component 1: weekly ceiling ─────────────────────────────────────
        weekly_scores.append(best_lineup_pts(team, weekly=True))

        # ── Component 2: healthy roster depth (VAR above replacement) ──────
        depth = 0.0
        stash = 0.0
        for p in team.roster:
            slot   = get_lineup_slot(p)
            status = get_player_status(p)
            on_il  = slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", "")

            if not on_il:
                # Active player: add their season VAR
                var = max(0.0, get_projected_pts(p) - get_replacement_level(p))
                depth += var
            else:
                # ── Component 3: stash (injured / IL) value ─────────────────
                # Discount depends on severity:
                #   IL/IR slot (formally placed):  0.50× — longer absence expected
                #   Active-roster injured (DL/DTD): 0.70× — likely closer to return
                discount = 0.50 if slot in ("IL", "IR") else 0.70
                stash   += get_stash_score(p) * discount

        depth_scores.append(depth)
        stash_scores.append(stash)

    # ── Normalise each component 0–100 ──────────────────────────────────────
    w_norm = _normalize(weekly_scores)
    d_norm = _normalize(depth_scores)
    s_norm = _normalize(stash_scores)

    # ── Combine into composite score ────────────────────────────────────────
    composites = {}
    for i, name in enumerate(names):
        composites[name] = (
            0.40 * w_norm[i]
            + 0.35 * d_norm[i]
            + 0.25 * s_norm[i]
        )

    # ── Assign ranks (1 = best) ──────────────────────────────────────────────
    ranked = sorted(composites.items(), key=lambda x: -x[1])
    return {name: rank + 1 for rank, (name, _) in enumerate(ranked)}


# ══════════════════════════════════════════════════════════════════════════════
# DATA ASSEMBLY FOR HTML RENDERER
# ══════════════════════════════════════════════════════════════════════════════

# ── Phase 6: Aging curve flags ────────────────────────────────────────────────

_AGE_CACHE: dict = {}          # espn_id → age (int) — in-process cache


def _fetch_player_age(player) -> int:
    """
    Return player age in years using MLB Stats API people endpoint.
    Falls back to -1 on any error.  Results cached per process run.
    """
    eid = get_espn_id(player)
    if eid in _AGE_CACHE:
        return _AGE_CACHE[eid]

    mlbam = get_mlbam_id(player)
    if not mlbam:
        mlbam = _mlbam_from_name(getattr(player, "name", ""))

    age = -1
    if mlbam:
        try:
            url  = f"https://statsapi.mlb.com/api/v1/people/{mlbam}?fields=people,currentAge"
            data = _mlb_get(url, timeout=6)
            ppl  = data.get("people", [{}])
            age  = int(ppl[0].get("currentAge", -1)) if ppl else -1
        except Exception:
            age = -1

    if eid:
        _AGE_CACHE[eid] = age
    return age


def age_tier(age: int) -> dict:
    """
    Return an aging-curve classification for a player.

    Windows (research-based):
      24–27  → Peak / Prime window (upside asset, buy)
      28–30  → Established peak (stable — slight decline possible)
      31–33  → Early decline (watch for speed-dependent skills)
      34+    → Late decline (sell speed-dependent / FA signings carefully)
      <24    → Pre-peak (breakout potential, high variance)

    Returns {tier, label, flag, color} or all-empty if age unknown.
    """
    if age < 0:
        return {"tier": 0, "label": "", "flag": "", "color": ""}
    if age < 24:
        return {"tier": 1, "label": "Pre-Peak", "flag": "⬆ Pre-Peak",   "color": "good"}
    if age <= 27:
        return {"tier": 2, "label": "Prime",    "flag": "🔥 Prime Age", "color": "accent"}
    if age <= 30:
        return {"tier": 3, "label": "Peak",     "flag": "✅ Peak",      "color": "good"}
    if age <= 33:
        return {"tier": 4, "label": "Decline",  "flag": "⚠ Aging",     "color": "warn"}
    return     {"tier": 5, "label": "Late",     "flag": "🔻 Late Career","color": "bad"}


# ── Phase 5: Velocity alerts ──────────────────────────────────────────────────

def _velocity_alert(player) -> str:
    """
    Check Statcast cache for velocity-derived signals on pitchers.
    Returns a concise alert string (empty string = no alert).
    Phase 5 note: full rolling-window velocity tracking requires live-season
    Statcast data (once 2026 games begin).  For now, this surfaces the xERA
    signal from the Phase 2 Statcast cache as a proxy for quality-of-stuff.
    """
    if not is_pitcher(player):
        return ""
    sc = get_statcast_metrics(player)
    if not sc:
        return ""
    signal = sc.get("signal", "")
    xera   = sc.get("xERA", 0.0)
    era    = sc.get("ERA", 0.0)
    gap    = sc.get("xERA_gap", 0.0)     # positive = xERA > ERA (sell/regression risk)
    stale_note = " [2025 data]" if STATCAST_DB.get("season") and STATCAST_DB["season"] < YEAR else ""
    if signal == "BUY_LOW" and gap <= -0.75:
        return f"Buy-Low: ERA {era:.2f} but xERA {xera:.2f} ({gap:.2f}){stale_note}"
    if signal == "SELL_HIGH" and gap >= 0.75:
        return f"Sell-High: ERA {era:.2f} but xERA {xera:.2f} (+{gap:.2f}){stale_note}"
    return ""


def _player_row(player, team_ctx):
    status = get_player_status(player)
    slot   = get_lineup_slot(player)   # resolve once; used in "pos" and "on_il"
    # Compute age once — avoids double network call (even with caching, two
    # separate calls are wasteful; the batch prefetch means this is usually free)
    _age = _fetch_player_age(player)
    return {
        "pos":          slot,
        "player":       player.name,
        "mlb":          get_player_team(player),
        "proj_pts":     fmt(get_projected_pts(player), 1),
        "repl_pts":     fmt(get_replacement_level(player), 1),
        "var":          fmt(max(0.0, get_projected_pts(player) - get_replacement_level(player)), 1),
        "base":         fmt(base_score(player)),
        "fit":          fmt(fit_score(player, team_ctx)),
        "tier":         get_value_tier(base_score(player)),
        "status":       status,
        "status_class": "warn" if status not in ("ACTIVE", "NORMAL", "") else "ok",
        "headshot":     get_player_headshot_url(player),
        "headshot2":    get_player_headshot_url_mlb(player),
        "initials":     get_initials(player.name),
        "avatar_seed":  avatar_seed(player.name),
        "mlbam_id":     get_mlbam_id(player),
        "espn_id":      get_espn_id(player),
        "is_pitcher":   "true" if is_pitcher(player) else "false",
        # -1 = not a starter; 0/1/2 = probable starts this week
        "weekly_starts": get_weekly_start_count(player) if is_starter_role(player) else -1,
        # Stash score = what this player is worth when healthy (injury_factor=1.0).
        # For healthy players this ≈ base. For IL players it shows true value
        # before the injury discount — useful to see alongside current base.
        "stash_score":   fmt(get_stash_score(player)),
        "healthy_proj":  fmt(get_healthy_projected_pts(player), 1),
        # Season stats for the pts-duo display on player cards
        "avg_pts":       fmt(as_float(safe_get(player, "avg_points", default=0)), 1),
        # Actual FP scored this season (ESPN stats dict → total_points)
        "actual_pts":    fmt(get_actual_season_pts(player), 1),
        # True if player is in IL/IR slot OR has a non-active injury status —
        # used by the card renderer to choose STASH+VAL vs FIT+VAL display.
        "on_il":         slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", ""),
        # ── Phase 1+2 advanced metrics (embedded as JSON for player modal) ────
        # Pulled from FanGraphs reference cache + Statcast cache.
        # Serialized here so the HTML renderer can drop them into data-adv attr.
        "adv":           _build_adv_json(player),
        # ── Phase 5+6: velocity alert & aging tier ───────────────────────────
        "velo_alert":    _velocity_alert(player),
        "age":           _age,
        "age_tier":      age_tier(_age),
        # True when this pitcher is a probable starter in today's MLB schedule.
        # Powered by _TODAY_STARTER_IDS, populated early in build_payload().
        "starts_today":  (
            is_pitcher(player)
            and bool(get_mlbam_id(player))
            and str(get_mlbam_id(player)) in _TODAY_STARTER_IDS
        ),
    }


def _build_adv_json(player):
    """
    Build a compact JSON string of all advanced metrics for a player.
    This is embedded as data-adv='...' on every player element so the JS
    modal can render charts without any additional network calls.
    Token-optimized: only non-zero values are included in the output.
    """
    ref  = get_reference_metrics(player)   # FanGraphs Phase 1 metrics
    sc   = get_statcast_metrics(player)    # Statcast Phase 2 metrics
    isp  = is_pitcher(player)

    # Value breakdown components (for the waterfall chart)
    proj  = get_projected_pts(player)
    repl  = get_replacement_level(player)
    var   = max(0.0, proj - repl)
    bs    = base_score(player)

    def _f(v, d=3):
        """Format float for compact JSON — drop trailing zeros."""
        try:
            f = round(float(v), d)
            return f if f != 0.0 else 0
        except Exception:
            return 0

    if isp:
        _swstp = _f(ref.get("SwStp", 0), 4)
        _k9    = _f(ref.get("K9",    0))
        adv = {
            # ERA estimators
            "ERA":   _f(ref.get("ERA",   0)),
            "FIP":   _f(ref.get("FIP",   0)),
            "xFIP":  _f(ref.get("xFIP",  0)),
            "SIERA": _f(ref.get("SIERA", 0)),
            "WHIP":  _f(ref.get("WHIP",  0)),
            # Stuff / swing — internal abbreviated keys
            "SwStp": _swstp,
            "CSWp":  _f(ref.get("CSWp",  0), 4),
            # ── Display-format aliases used by html.py stat pills ──────────────
            "SwStr%": _swstp,   # html.py: adv.get("SwStr%")
            # Component rates — internal abbreviated keys
            "K9":    _k9,
            "BB9":   _f(ref.get("BB9",   0)),
            "KBBp":  _f(ref.get("KBBp",  0), 4),
            # ── Display-format aliases used by html.py stat pills ──────────────
            "K/9":   _k9,       # html.py: adv.get("K/9")
            # Batted ball
            "GBp":   _f(ref.get("GBp",   0), 4),
            "FBp":   _f(ref.get("FBp",   0), 4),
            "LDp":   _f(ref.get("LDp",   0), 4),
            # Regression signals
            "HRFBp": _f(ref.get("HRFBp", 0), 4),
            "LOBp":  _f(ref.get("LOBp",  0), 4),
            "BABIPp":_f(ref.get("BABIPp",0), 4),
            "WAR":   _f(ref.get("WAR",   0)),
            # Statcast (Phase 2 — may be 0 if cache not built)
            "xERA":     _f(sc.get("xERA",    0)),
            "xERA_gap": _f(sc.get("xERA_gap",0)),
            "xwOBA_a":  _f(sc.get("xwOBA_a", 0), 4),
            "Brlp_a":   _f(sc.get("Brlp_a",  0), 4),
            "HHp_a":    _f(sc.get("HHp_a",   0), 4),
            "EV_a":     _f(sc.get("EV_a",    0)),
            "signal":   sc.get("signal", ""),
            # Value breakdown
            "proj":  _f(proj, 1),
            "repl":  _f(repl, 1),
            "var":   _f(var,  1),
            "val":   _f(bs,   1),
        }
    else:
        _wrcp = _f(ref.get("wRCp", 0))
        _kp   = _f(ref.get("Kp",   0), 4)
        _brlp = _f(ref.get("Brlp", 0), 4)
        adv = {
            # Core value metrics — internal abbreviated keys
            "wRCp":  _wrcp,
            "wOBA":  _f(ref.get("wOBA",  0), 4),
            "ISO":   _f(ref.get("ISO",   0), 4),
            "OPS":   _f(ref.get("OPS",   0), 4),
            # ── Display-format aliases used by html.py stat pills ──────────────
            "wRC+":  _wrcp,     # html.py: adv.get("wRC+")
            # Plate discipline — internal abbreviated keys
            "BBp":   _f(ref.get("BBp",   0), 4),
            "Kp":    _kp,
            # ── Display-format aliases used by html.py stat pills ──────────────
            "K%":    _kp,       # html.py: adv.get("K%")
            # Batted ball / luck
            "BABIP": _f(ref.get("BABIP", 0), 4),
            "LDp":   _f(ref.get("LDp",   0), 4),
            "GBp":   _f(ref.get("GBp",   0), 4),
            "FBp":   _f(ref.get("FBp",   0), 4),
            "Hardp": _f(ref.get("Hardp", 0), 4),
            # Barrel — internal key + both aliases html.py tries
            "Brlp":    _brlp,
            "Barrel%": _brlp,   # html.py: adv.get("Barrel%")
            "Brl%":    _brlp,   # html.py: adv.get("Brl%")
            "Spd":   _f(ref.get("Spd",   0)),
            "WAR":   _f(ref.get("WAR",   0)),
            # Statcast (Phase 2)
            "xwOBA":     _f(sc.get("xwOBA",    0), 4),
            "xwOBA_gap": _f(sc.get("xwOBA_gap",0), 4),
            "xBA":       _f(sc.get("xBA",      0), 4),
            "xSLG":      _f(sc.get("xSLG",     0), 4),
            "EV":        _f(sc.get("EV",       0)),
            "EV90":      _f(sc.get("EV90",     0)),
            # HHp: Statcast hard-hit% (EV≥95mph) if available, otherwise FanGraphs Hard%
            # Both sources store the value as a decimal fraction (0.456 = 45.6%)
            # Statcast HHp is 0 when the Baseball Savant leaderboard endpoint doesn't
            # include hard_hit_percent (it's on a different Savant endpoint), so we
            # fall back to ref Hardp from FanGraphs batting_stats() which is always populated.
            "HHp": _f(sc.get("HHp", 0), 4) or _f(ref.get("Hardp", 0), 4),
            "SprintSpd": _f(sc.get("Spd",      0)),
            "signal":    sc.get("signal", ""),
            # Value breakdown
            "proj":  _f(proj, 1),
            "repl":  _f(repl, 1),
            "var":   _f(var,  1),
            "val":   _f(bs,   1),
        }

    # ── Phase 5+6: velocity alert + aging tier (always include) ─────────────
    velo_alert = _velocity_alert(player)
    age        = _fetch_player_age(player)
    at         = age_tier(age)
    adv["velo_alert"] = velo_alert
    adv["age"]        = age if age > 0 else 0
    adv["age_label"]  = at.get("label", "")
    adv["age_flag"]   = at.get("flag",  "")
    adv["age_color"]  = at.get("color", "")

    # Strip zero values to keep JSON compact (token-optimization)
    compact = {k: v for k, v in adv.items() if v != 0 and v != "" and v != 0.0}
    return json.dumps(compact, separators=(",", ":"))

# ══════════════════════════════════════════════════════════════════════════════
# MLB SCHEDULE INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

def _parse_game_time(utc_str):
    """'2026-03-24T23:10:00Z' → '7:10 PM ET'  (EDT = UTC-4, active during season)."""
    try:
        from datetime import timezone, timedelta
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        et = timezone(timedelta(hours=-4))   # EDT; change to -5 for winter months
        return dt.astimezone(et).strftime("%-I:%M %p ET")
    except Exception:
        return "TBD"


def _mlb_get(url: str, timeout: int = 10) -> dict:
    """
    GET a MLB Stats API URL and return parsed JSON.
    Uses `requests` + certifi (both present in the venv) so macOS certificate
    verification works correctly — urllib.request.urlopen fails on macOS because
    Python's bundled SSL doesn't use the system keychain.
    Raises on any network / HTTP error.
    """
    import requests, certifi
    resp = requests.get(url, timeout=timeout, verify=certifi.where())
    resp.raise_for_status()
    return resp.json()


def fetch_todays_mlb_schedule():
    """Hit the free MLB Stats API and return today's schedule as a list of dicts.
    Now hydrates probablePitcher so matchup intelligence can grade hitter matchups.
    Falls back silently to [] on any network or parse error.
    """
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        url = (
            "https://statsapi.mlb.com/api/v1/schedule"
            f"?sportId=1&date={today}&hydrate=team,probablePitcher,lineups"
        )
        raw = _mlb_get(url, timeout=8)

        games = []
        for date_block in raw.get("dates", []):
            for g in date_block.get("games", []):
                teams_data = g.get("teams", {})
                away_data  = teams_data.get("away", {})
                home_data  = teams_data.get("home", {})
                away_t  = away_data.get("team", {})
                home_t  = home_data.get("team", {})
                status  = g.get("status", {}).get("detailedState", "Scheduled")
                utc_str = g.get("gameDate", "")
                away_pp = away_data.get("probablePitcher", {})
                home_pp = home_data.get("probablePitcher", {})

                # Extract confirmed lineup player IDs (empty if lineups not posted yet)
                def _extract_lineup_ids(team_data):
                    entries = team_data.get("lineupEntry", []) or team_data.get("lineup", {}).get("lineupEntry", []) or []
                    return [str(e.get("person", {}).get("id", "")) for e in entries if e.get("person", {}).get("id")]

                away_lineup_ids = _extract_lineup_ids(away_data)
                home_lineup_ids = _extract_lineup_ids(home_data)
                lineups_posted  = bool(away_lineup_ids or home_lineup_ids)

                games.append({
                    "time_str":          _parse_game_time(utc_str),
                    "time_utc":          utc_str,
                    "away_abbr":         away_t.get("abbreviation", ""),
                    "home_abbr":         home_t.get("abbreviation", ""),
                    "away_name":         away_t.get("name", ""),
                    "home_name":         home_t.get("name", ""),
                    "status":            status,
                    "my_players":        [],
                    "opp_players":       [],
                    # Phase 4 — probable pitchers for matchup grading
                    "away_pitcher_name": away_pp.get("fullName", "TBD"),
                    "away_pitcher_id":   str(away_pp.get("id", "")),
                    "home_pitcher_name": home_pp.get("fullName", "TBD"),
                    "home_pitcher_id":   str(home_pp.get("id", "")),
                    "away_lineup_ids":   away_lineup_ids,
                    "home_lineup_ids":   home_lineup_ids,
                    "lineups_posted":    lineups_posted,
                })
        games.sort(key=lambda g: g["time_utc"])
        return games
    except Exception as e:
        print(f"  Warning: MLB schedule fetch failed (non-fatal): {e}")
        return []


def _current_week_range():
    """Return (YYYY-MM-DD, YYYY-MM-DD) for the Mon–Sun fantasy week containing today."""
    from datetime import timedelta
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())      # weekday() 0 = Monday
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def fetch_weekly_probable_starts(week_start: str, week_end: str) -> dict:
    """
    Pull MLB Stats API probable-pitcher data for the full Mon-Sun fantasy week.
    Returns {mlbam_id_str: start_count} and caches result in WEEKLY_STARTS.
    Falls back silently to {} on any error so scoring is never blocked.

    NOTE: Probable pitchers are typically posted 1-2 days ahead; earlier in the
    week the dict will be sparse — that is expected and handled by the multiplier.
    """
    if WEEKLY_STARTS["loaded"] and WEEKLY_STARTS["week_start"] == week_start:
        return WEEKLY_STARTS["starts"]

    starts: dict = {}
    try:
        url = (
            "https://statsapi.mlb.com/api/v1/schedule"
            f"?sportId=1&startDate={week_start}&endDate={week_end}"
            "&hydrate=probablePitcher,team&gameType=R"
        )
        raw = _mlb_get(url, timeout=10)

        for date_block in raw.get("dates", []):
            for game in date_block.get("games", []):
                teams_data = game.get("teams", {})
                for side in ("home", "away"):
                    pp = teams_data.get(side, {}).get("probablePitcher", {})
                    pid = str(pp.get("id", ""))
                    if pid:
                        starts[pid] = starts.get(pid, 0) + 1

        WEEKLY_STARTS.update({
            "starts":     starts,
            "loaded":     True,
            "week_start": week_start,
            "week_end":   week_end,
        })
        print(f"  Weekly probable starters: {len(starts)} pitchers found ({week_start} → {week_end})")
    except Exception as exc:
        print(f"  Weekly probable starters: fetch failed ({exc}) — multiplier skipped")
        WEEKLY_STARTS.update({"starts": {}, "loaded": True,
                               "week_start": week_start, "week_end": week_end})

    return WEEKLY_STARTS["starts"]


def get_weekly_start_count(player) -> int:
    """Probable start count for a pitcher this week (0 if not scheduled or not found)."""
    return WEEKLY_STARTS["starts"].get(get_mlbam_id(player), 0)


def get_two_start_multiplier(player) -> float:
    """
    Weekly value multiplier for starting pitchers based on scheduled starts.

    Two-start week  → 1.75× (roughly the empirically observed added value)
    One-start week  → 1.00× (baseline; no change)
    Zero-start week → 0.30× (dead roster weight this week)

    Guards:
    - Only applied to starters (is_starter_role); RPs always return 1.0.
    - Requires ≥ 60 pitchers posted as probable (preseason / early week returns 1.0).
    """
    if not is_starter_role(player):
        return 1.0
    if not WEEKLY_STARTS["loaded"] or len(WEEKLY_STARTS["starts"]) < 60:
        return 1.0   # preseason or probables not yet posted
    count = get_weekly_start_count(player)
    if count >= 2:
        return 1.75
    if count == 1:
        return 1.0
    return 0.30      # no start this week — minimal weekly contribution



def annotate_games_with_players(games, my_rows, opp_rows):
    """For each game, find players from either roster whose mlb team is playing."""
    def _abbr(s):
        return str(s).upper().strip()

    for game in games:
        away = _abbr(game["away_abbr"])
        home = _abbr(game["home_abbr"])
        for row in my_rows:
            if _abbr(row.get("mlb", "")) in (away, home):
                game["my_players"].append(row)
        for row in opp_rows:
            if _abbr(row.get("mlb", "")) in (away, home):
                game["opp_players"].append(row)
    return games


# ══════════════════════════════════════════════════════════════════════════════
# MATCHUP INTELLIGENCE  —  Phase 4
# Rate each active hitter's today-game matchup vs. the opposing probable starter
# using Phase 1 FanGraphs advanced metrics (FIP, xFIP, SIERA, SwStr%).
# ══════════════════════════════════════════════════════════════════════════════

def _lookup_pitcher_metrics_by_name(pitcher_name: str) -> dict:
    """Return FanGraphs reference metrics for a pitcher by display name."""
    if not pitcher_name or pitcher_name in ("TBD", ""):
        return {}
    return REFERENCE_DB["pitchers"].get(normalize_name(pitcher_name), {})


# ── Park factor lookup by MLB team abbreviation ───────────────────────────────
# Values > 1.0 = hitter-friendly; < 1.0 = pitcher-friendly.
# Source: FanGraphs park factors 2025-2026, adjusted for 2026 ballpark changes.
# Kauffman Stadium moved walls in for 2026 → KC bumped up.
# Globe Life Field continues to suppress offense → TEX significantly below 1.0.
_PARK_FACTORS = {
    "COL": 1.16,  # Coors Field — extreme hitter park
    "BAL": 1.10,  # Camden Yards — tied 2nd in HR factor
    "LAD": 1.08,  # Dodger Stadium — best HR park in NL
    "OAK": 1.07,  # Sutter Health Park (temp home)
    "KC":  1.07,  # Kauffman — walls moved in for 2026
    "BOS": 1.05,  # Fenway — green monster
    "CIN": 1.04,  # Great American Ballpark
    "NYY": 1.03,  # Yankee Stadium
    "CHC": 1.02,  # Wrigley Field
    "PHI": 1.02,  # Citizens Bank Park
    "MIN": 1.01,  # Target Field
    "WSH": 1.00,  # Nationals Park — neutral
    "ATL": 1.00,  # Truist Park — neutral
    "DET": 0.99,  # Comerica Park
    "CLE": 0.99,  # Progressive Field
    "NYM": 0.98,  # Citi Field
    "MIL": 0.98,  # American Family Field
    "STL": 0.97,  # Busch Stadium
    "PIT": 0.97,  # PNC Park
    "ARI": 0.97,  # Chase Field
    "HOU": 0.96,  # Minute Maid Park
    "TOR": 0.96,  # Rogers Centre
    "SEA": 0.96,  # T-Mobile Park
    "TB":  0.96,  # Tropicana Field
    "SF":  0.96,  # Oracle Park
    "SD":  0.95,  # Petco Park — strong pitcher's park
    "MIA": 0.95,  # loanDepot Park
    "CWS": 0.95,  # Guaranteed Rate Field
    "LAA": 0.95,  # Angel Stadium
    "TEX": 0.92,  # Globe Life Field — one of MLB's toughest for hitters
}

def get_park_factor(team_abbr: str) -> float:
    """Return park factor for a team's home ballpark (1.0 = neutral)."""
    return _PARK_FACTORS.get(str(team_abbr).upper(), 1.0)

def grade_pitcher_matchup(pitcher_name: str, park_factor: float = 1.0) -> dict:
    """
    Grade a hitter's matchup against a given starting pitcher.

    Uses the Phase 1 FanGraphs metrics hierarchy:
      Best ERA estimator: SIERA → xFIP → FIP → ERA

    Returns:
      grade  : int  1–5  (5 = most favorable for hitter)
      label  : str  human-readable verdict
      color  : str  CSS token  (bad / warn / neutral / good / accent)
      reason : str  metric summary shown in the UI
      era_est: float  best available ERA estimator value
      swstr  : float  SwStr% (0–1 scale)
    """
    m = _lookup_pitcher_metrics_by_name(pitcher_name)
    if not m:
        return {
            "grade": 3, "label": "Unknown SP", "color": "neutral",
            "reason": "No prior-season data", "era_est": 0.0, "swstr": 0.0,
        }

    siera = get_metric(m, "SIERA")
    xfip  = get_metric(m, "xFIP")
    fip   = get_metric(m, "FIP")
    era   = get_metric(m, "ERA")
    swstr = get_metric(m, "SwStp")
    kbb   = get_metric(m, "KBBp")
    ip    = get_metric(m, "IP")

    # Best ERA estimator — first non-zero in priority order
    era_key = "SIERA"
    era_est = siera
    if not (0 < era_est < 90):
        era_key, era_est = "xFIP", xfip
    if not (0 < era_est < 90):
        era_key, era_est = "FIP", fip
    if not (0 < era_est < 90):
        era_key, era_est = "ERA", era
    if not (0 < era_est < 90):
        era_key, era_est = "", 0.0

    # Grade 1 = elite pitcher (tough for hitter), 5 = cream-puff (great for hitter)
    # Park factor adjusts the effective ERA: favorable park raises grade, pitcher-friendly lowers it.
    park_adj_era = 0.0
    park_note = ""
    # Validate park_factor: must be a positive float in a sane range
    if not isinstance(park_factor, (int, float)) or not (0.5 <= park_factor <= 2.0):
        park_factor = 1.0
    if era_est > 0:
        # Park-adjusted ERA estimate: hitter-friendly park makes same ERA easier to hit against
        park_adj_era = era_est / max(park_factor, 0.80)  # prevent divide-by-zero
        if park_factor >= 1.08:
            park_note = f" (park +{int((park_factor-1)*100)}% hit-friendly)"
        elif park_factor <= 0.95:
            park_note = f" (park {int((park_factor-1)*100)}% pitcher-friendly)"

        if park_adj_era <= 3.30 or swstr >= 0.13:
            grade, label, color = 1, "Elite Pitcher", "bad"
        elif park_adj_era <= 3.80 or swstr >= 0.10:
            grade, label, color = 2, "Tough Matchup", "warn"
        elif park_adj_era <= 4.30:
            grade, label, color = 3, "Average Matchup", "neutral"
        elif park_adj_era <= 4.80:
            grade, label, color = 4, "Favorable", "good"
        else:
            grade, label, color = 5, "Elite Matchup", "accent"
    else:
        park_adj_era = 0.0
        park_note = ""
        grade, label, color = 3, "Unknown Quality", "neutral"

    # Reason string — concise metrics summary
    parts = []
    if era_est > 0:
        parts.append(f"{era_key} {era_est:.2f}")
    if swstr > 0:
        parts.append(f"SwStr% {swstr * 100:.1f}%")
    if kbb > 0:
        parts.append(f"K-BB% {kbb * 100:.1f}%")
    if ip > 0:
        parts.append(f"{ip:.0f} IP")

    return {
        "grade":       grade,
        "label":       label,
        "color":       color,
        "reason":      (", ".join(parts) if parts else "Limited data") + (park_note if park_note else ""),
        "era_est":     era_est,
        "park_factor": park_factor,
        "swstr":       swstr,
    }


def build_hitter_matchups_today(my_roster_rows: list, today_games: list) -> list:
    """
    For every active hitter in my_roster_rows that has a game today,
    identify the probable opposing starter and grade the matchup.

    Returns a list of dicts sorted by matchup favorability (grade DESC, proj_pts DESC):
      player, pos, mlb, game_str, game_time, pitcher_name,
      grade, label, color, reason, era_est, swstr, proj_pts, base,
      headshot, headshot2, initials
    """
    # Build team-abbr → game map (each team appears once — home or away)
    abbr_to_game: dict = {}
    for g in today_games:
        abbr_to_game[g["away_abbr"].upper()] = g
        abbr_to_game[g["home_abbr"].upper()] = g

    results = []
    for row in my_roster_rows:
        # Active hitters only
        if row.get("is_pitcher") == "true":
            continue
        if row.get("pos", "") in ("BE", "BENCH", "IL", "IR", "NA"):
            continue

        mlb = row.get("mlb", "").upper().strip()
        game = abbr_to_game.get(mlb)
        if not game:
            continue  # not playing today

        # Who is the opposing pitcher?
        if mlb == game["away_abbr"].upper():
            opp_pitcher = game.get("home_pitcher_name", "TBD")
        else:
            opp_pitcher = game.get("away_pitcher_name", "TBD")

        game_str = f"{game['away_abbr']} @ {game['home_abbr']}"
        # Determine home team for park factor lookup
        home_abbr  = game.get("home_abbr", "").upper()
        _park_factor = get_park_factor(home_abbr)
        grade_info = grade_pitcher_matchup(opp_pitcher, park_factor=_park_factor)

        # Check if player is in confirmed lineup (if lineups are posted)
        player_mlbam = row.get("mlbam_id", "")
        lineups_posted = game.get("lineups_posted", False)
        if lineups_posted and player_mlbam:
            if mlb == game["away_abbr"].upper():
                in_lineup = player_mlbam in game.get("away_lineup_ids", [])
            else:
                in_lineup = player_mlbam in game.get("home_lineup_ids", [])
            lineup_status = "confirmed" if in_lineup else "not_in_lineup"
        else:
            lineup_status = "pending"  # lineups not posted yet

        results.append({
            "player":       row["player"],
            "pos":          row.get("pos", "?"),
            "mlb":          mlb,
            "game_str":     game_str,
            "game_time":    game.get("time_str", ""),
            "pitcher_name": opp_pitcher,
            "grade":        grade_info["grade"],
            "label":        grade_info["label"],
            "color":        grade_info["color"],
            "reason":       grade_info["reason"],
            "era_est":      grade_info["era_est"],
            "swstr":        grade_info["swstr"],
            "proj_pts":     row.get("proj_pts", "0"),
            "base":         row.get("base", "0"),
            "headshot":     row.get("headshot", ""),
            "headshot2":    row.get("headshot2", ""),
            "initials":     row.get("initials", "?"),
            "park_factor":  _park_factor,
            "lineup_status": lineup_status,
        })

    results.sort(key=lambda x: (-x["grade"], -float(x["proj_pts"] or 0)))
    return results


# ══════════════════════════════════════════════════════════════════════════════
# SEASON INTELLIGENCE — IL stash tracking, trends, long-season FA targets
# ══════════════════════════════════════════════════════════════════════════════

# ── MLB Stats API career-stats helpers ────────────────────────────────────────

# Simple in-process cache so scoring all 14 teams (Teams tab) doesn't fire
# duplicate API requests for the same player.
_CAREER_STATS_CACHE: dict = {}
_NAME_TO_MLBAM_CACHE: dict = {}  # name-search fallback cache


def _mlbam_from_name(name: str) -> str:
    """
    Look up a player's MLBAM ID by name via the MLB Stats people/search endpoint.
    Used as a fallback when the ESPN player object doesn't expose a proId.
    Results are cached to avoid repeated lookups for the same name.
    Returns '' on any error or if no result is found.
    """
    if not name:
        return ""
    key = name.strip().lower()
    if key in _NAME_TO_MLBAM_CACHE:
        return _NAME_TO_MLBAM_CACHE[key]
    try:
        import urllib.parse
        url  = (f"https://statsapi.mlb.com/api/v1/people/search"
                f"?names={urllib.parse.quote(name)}&sportId=1")
        data = _mlb_get(url, timeout=8)
        people = data.get("people", [])
        # Prefer active players; fall back to any result
        active = [p for p in people if p.get("active", False)]
        hit    = active[0] if active else (people[0] if people else None)
        result = str(hit["id"]) if hit else ""
    except Exception:
        result = ""
    _NAME_TO_MLBAM_CACHE[key] = result
    # Also add to the Statcast name index so get_mlbam_id() can use the fast
    # dict path on any subsequent call for this player within the same run.
    if result:
        _SC_NAME_TO_MLBAM[normalize_name(name)] = result
    return result

def _fetch_career_stats(mlbam_id: str, group: str = "pitching") -> list:
    """
    Fetch year-by-year career stats from the MLB Stats API for a player.
    Returns a list of stat dicts, each including a 'season' (int) key,
    sorted newest season first.  Returns [] on any network/parse error.
    MLB-only (sportId=1) — filters out minor-league appearances.
    Results are cached in _CAREER_STATS_CACHE for the lifetime of the process.
    """
    cache_key = f"{mlbam_id}_{group}"
    if cache_key in _CAREER_STATS_CACHE:
        return _CAREER_STATS_CACHE[cache_key]

    url = (
        f"https://statsapi.mlb.com/api/v1/people/{mlbam_id}/stats"
        f"?stats=yearByYear&group={group}&sportId=1"
    )
    raw    = _mlb_get(url, timeout=12)
    splits = []
    for entry in raw.get("stats", []):
        for split in entry.get("splits", []):
            yr = int(split.get("season", 0) or 0)
            if yr < 2010:
                continue
            # Only MLB (sportId=1) — the yearByYear endpoint can include MiLB
            sport_id = (split.get("sport") or {}).get("id", 1)
            if sport_id != 1:
                continue
            s = dict(split.get("stat", {}))
            s["season"] = yr
            splits.append(s)
    splits.sort(key=lambda x: x["season"], reverse=True)
    _CAREER_STATS_CACHE[cache_key] = splits
    return splits


def _pts_from_mlb_pitcher_stats(s: dict, sp_mode: bool, extrapolate: bool = True) -> float:
    """
    Convert an MLB Stats API pitcher stat dict to our league's fantasy points.

    When extrapolate=True, partial seasons (e.g. pre-TJS) are scaled up to a
    normal full-season workload:
      SP: assume 32 GS / 190 IP if the player had ≥8 GS but <150 IP
      RP: assume 65 G  / 65 IP  if the player had ≥20 G  but <55 IP
    """
    ip  = as_float(s.get("inningsPitched",  0))
    gs  = as_float(s.get("gamesStarted",    0))
    g   = as_float(s.get("gamesPlayed",     gs))
    sv  = as_float(s.get("saves",           0))
    hd  = as_float(s.get("holds",           0))
    w   = as_float(s.get("wins",            0))
    l   = as_float(s.get("losses",          0))
    so  = as_float(s.get("strikeOuts",      0))
    bb  = as_float(s.get("baseOnBalls",     0))
    h   = as_float(s.get("hits",            0))
    er  = as_float(s.get("earnedRuns",      0))
    hr  = as_float(s.get("homeRuns",        0))
    bs  = as_float(s.get("blownSaves",      0))
    qs  = as_float(s.get("qualityStarts",   0))
    if qs == 0 and gs > 0:
        qs = gs * 0.55      # estimate when not available

    if extrapolate:
        if sp_mode and gs >= 8 and ip < 150:
            # Partial SP season (e.g. Cole's 17 GS / 99 IP before TJS)
            # → scale to a typical 32-start full season
            scale = 32.0 / max(gs, 1)
            ip *= scale;  gs *= scale;  w  *= scale;  l  *= scale
            so *= scale;  bb *= scale;  h  *= scale;  er *= scale
            hr *= scale;  qs *= scale
        elif (not sp_mode) and g >= 20 and ip < 55:
            # Partial RP season → scale to a typical 65-appearance season
            scale = 65.0 / max(g, 1)
            ip *= scale;  g  *= scale;  sv *= scale;  hd *= scale
            w  *= scale;  so *= scale;  bb *= scale;  h  *= scale
            er *= scale;  hr *= scale;  bs *= scale

    score  = PITCHING_SCORING["IP"]   * ip
    score += PITCHING_SCORING["H"]    * h
    score += PITCHING_SCORING["ER"]   * er
    score += PITCHING_SCORING["HR"]   * hr
    score += PITCHING_SCORING["BB"]   * bb
    score += PITCHING_SCORING["K"]    * so
    score += PITCHING_SCORING["QS"]   * qs
    score += PITCHING_SCORING["W"]    * w
    score += PITCHING_SCORING["L"]    * l
    score += PITCHING_SCORING["SV"]   * sv
    score += PITCHING_SCORING["BS"]   * bs
    score += PITCHING_SCORING["HD"]   * hd
    score += PITCHING_SCORING["SVHD"] * (sv + hd)
    score += PITCHING_SCORING["CG"]   * (gs * 0.01)
    score += PITCHING_SCORING["SO"]   * (gs * 0.001)
    return max(0.0, score)


def _pts_from_mlb_hitter_stats(s: dict, extrapolate: bool = True) -> float:
    """
    Convert an MLB Stats API hitter stat dict to our league's fantasy points.
    Extrapolates partial seasons (PA ≥ 100 but < 450) to a 550-PA full season.
    """
    pa  = as_float(s.get("plateAppearances", 0))
    h   = as_float(s.get("hits",             0))
    d   = as_float(s.get("doubles",          0))
    t   = as_float(s.get("triples",          0))
    hr  = as_float(s.get("homeRuns",         0))
    r   = as_float(s.get("runs",             0))
    rbi = as_float(s.get("rbi",              0))
    sb  = as_float(s.get("stolenBases",      0))
    bb  = as_float(s.get("baseOnBalls",      0))
    so  = as_float(s.get("strikeOuts",       0))
    tb  = as_float(s.get("totalBases",       0))
    if tb == 0 and h > 0:
        tb = h + d + 2 * t + 3 * hr   # singles=1, 2B=2, 3B=3, HR=4

    if extrapolate and 100 <= pa < 450:
        scale = 550.0 / pa
        h  *= scale;  d  *= scale;  t   *= scale;  hr  *= scale
        r  *= scale;  rbi *= scale; sb  *= scale;  bb  *= scale
        so *= scale;  tb  *= scale; pa  *= scale

    score  = BATTING_SCORING["R"]     * r
    score += BATTING_SCORING["HR"]    * hr
    score += BATTING_SCORING["TB"]    * tb
    score += BATTING_SCORING["RBI"]   * rbi
    score += BATTING_SCORING["BB"]    * bb
    score += BATTING_SCORING["SB"]    * sb
    score += BATTING_SCORING["K"]     * so
    score += BATTING_SCORING["GWRBI"] * (rbi * 0.02)
    score += BATTING_SCORING["GSHR"]  * (pa  * 0.003)
    return max(0.0, score)


def _last_healthy_season_pts(player) -> float:
    """
    Scan the player's full MLB career (via MLB Stats API year-by-year endpoint)
    to find their most recent *healthy* season, extrapolate it to a full
    workload, then apply a recency discount based on how long they've been out.

    Healthy thresholds:
      SP:     GS ≥ 10  AND  IP ≥ 40
      RP:     G  ≥ 20  AND  IP ≥ 15
      Hitter: PA ≥ 150

    Recency discounts:
      1 year ago  → 0.93  (recently injured — strong baseline)
      2 years ago → 0.85  (missed one full season)
      3 years ago → 0.77  (missed two seasons, e.g. Cole post-TJS)
      4+ years    → 0.68  (significant uncertainty)

    Returns 0.0 if no qualifying season found or on any error.
    """
    mlbam = get_mlbam_id(player)
    if not mlbam:
        # ESPN sometimes omits proId for IL players — try a name-based MLB search
        pname = getattr(player, "name", "") or ""
        mlbam = _mlbam_from_name(pname)
        if mlbam:
            print(f"    [stash] {pname}: resolved MLBAM via name search → {mlbam}")
    if not mlbam:
        return 0.0

    is_p  = is_pitcher(player)
    is_sp = is_starter_role(player)
    group = "pitching" if is_p else "hitting"

    try:
        seasons = _fetch_career_stats(mlbam, group)
    except Exception:
        return 0.0

    for s in seasons:
        yr = s.get("season", 0)
        if yr >= YEAR:
            continue      # skip current (partial) season

        if is_p:
            ip = as_float(s.get("inningsPitched", 0))
            gs = as_float(s.get("gamesStarted",   0))
            g  = as_float(s.get("gamesPlayed",    0))
            if is_sp:
                if gs < 10 or ip < 40:
                    continue     # not enough starts to qualify
            else:
                if g < 20 or ip < 15:
                    continue     # not enough relief appearances to qualify
            pts = _pts_from_mlb_pitcher_stats(s, sp_mode=is_sp, extrapolate=True)
        else:
            pa = as_float(s.get("plateAppearances", 0))
            if pa < 150:
                continue
            pts = _pts_from_mlb_hitter_stats(s, extrapolate=True)

        if pts < 10:
            continue     # sanity floor — ignore noise

        years_ago = YEAR - yr
        discount  = {1: 0.93, 2: 0.85, 3: 0.77}.get(years_ago, 0.68)
        result    = pts * discount
        print(f"    [stash] {getattr(player,'name','?')}: "
              f"{yr} stats ({pts:.0f} pts) × {discount} discount = {result:.0f} healthy pts")
        return result

    return 0.0


def get_healthy_projected_pts(player):
    """
    Best-effort estimate of a player's FULL-SEASON healthy fantasy point total.

    Priority order for IL / injured players:
      1. Prior-season reference DB  (best when YEAR-1 was healthy)
      2. MLB Stats API career scan   (covers multi-year injuries like Cole:
           finds last healthy season → extrapolates partial workload →
           applies recency discount for years missed)
      3. ESPN prior-year stats dict  (YEAR-2 / YEAR-3 buckets)
      4. ESPN projected_total_points (partial-season, last resort)

    Priority order for healthy players:
      1. ESPN projected_total_points (current-season, most accurate)
      2. Prior-season reference DB
      3. avg_points × 26
    """
    status = get_player_status(player)
    slot   = get_lineup_slot(player)
    on_il  = slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", "")

    if on_il:
        # 1. Prior-season reference DB — full healthy-season baseline
        metrics = get_reference_metrics(player)
        if metrics:
            pts = (_pitcher_pts_from_stats(metrics) if is_pitcher(player)
                   else _hitter_pts_from_stats(metrics))
            if pts > 20:
                return pts

        # 2. MLB Stats API career scan — handles multi-year injuries (Cole, etc.)
        mlb_pts = _last_healthy_season_pts(player)
        if mlb_pts > 20:
            return mlb_pts

        # 3. ESPN season-total for the current year (integer key 0 = full season)
        try:
            pts = _espn_actual_season_pts(player)
            if pts > 20:
                return pts
        except Exception:
            pass

        # 4. ESPN partial-season projection (last resort for IL)
        espn_proj = as_float(safe_get(player, "projected_total_points", default=0))
        if espn_proj > 5:
            return espn_proj

    else:
        # Healthy path — ESPN projection is most accurate
        espn_proj = as_float(safe_get(player, "projected_total_points", default=0))
        if espn_proj > 5:
            return espn_proj

        metrics = get_reference_metrics(player)
        if metrics:
            pts = (_pitcher_pts_from_stats(metrics) if is_pitcher(player)
                   else _hitter_pts_from_stats(metrics))
            if pts > 5:
                return pts

    # Universal fallback
    avg = as_float(safe_get(player, "avg_points", default=0))
    if avg > 0:
        return avg * 26
    return 0.0


def get_stash_score(player):
    """
    Like base_score() but with injury_factor forced to 1.0.
    Answers: "What is this player worth when healthy over a full season?"
    Use this to evaluate whether an injured player is worth keeping on your IL.

    NOTE: the two-start weekly multiplier is intentionally NOT applied here.
    Stash score is a season-long assessment — applying a 0.30× 'no-start-this-week'
    penalty to an IL player would make the metric meaningless for long-term decisions.
    """
    var = max(0.0, get_healthy_projected_pts(player) - get_replacement_level(player))
    # No weekly_mult: season value, not this-week value
    raw = var * get_scarcity_multiplier(player)
    if not SCALING["ready"]:
        return raw
    if is_pitcher(player):
        return _scale(raw, SCALING["p_base_min"], SCALING["p_base_max"])
    return _scale(raw, SCALING["h_base_min"], SCALING["h_base_max"])


def is_worth_stashing(player):
    """True if player is on IL/IR and their healthy stash score clears the threshold."""
    slot   = get_lineup_slot(player)
    status = get_player_status(player)
    on_il  = slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", "")
    if not on_il:
        return False
    return get_stash_score(player) >= STASH_SCORE_THRESHOLD


def _get_player_game_log_stats(mlbam_id: str, season: int,
                                lookback_days: int = 45,
                                is_pitcher_p: bool = False) -> list:
    """
    Fetch recent game-log entries for a player from the MLB Stats API.
    Returns a list of per-game stat dicts (last lookback_days days), or [] on any error.
    """
    if not mlbam_id:
        return []
    group = "pitching" if is_pitcher_p else "hitting"
    try:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        url = (
            f"https://statsapi.mlb.com/api/v1/people/{mlbam_id}/stats"
            f"?stats=gameLog&season={season}&group={group}"
        )
        raw = _mlb_get(url, timeout=10)
        games = []
        for stats_entry in raw.get("stats", []):
            for split in stats_entry.get("splits", []):
                game_date = split.get("date", "")
                if game_date >= cutoff:
                    games.append(split.get("stat", {}))
        return games
    except Exception:
        return []


def get_season_trend(player) -> dict:
    """
    Analyse a player's current-season performance trend vs. prior-season baseline.
    Returns a dict:
        trend:        "hot" | "cold" | "stable" | "insufficient_data"
        games_recent: int
        summary:      human-readable one-liner
    """
    mlbam = get_mlbam_id(player)
    if not mlbam:
        return {"trend": "insufficient_data", "games_recent": 0, "summary": "No MLBAM ID"}

    is_p  = is_pitcher(player)
    games = _get_player_game_log_stats(mlbam, YEAR, SEASON_TREND_LOOKBACK, is_pitcher_p=is_p)

    if len(games) < SEASON_TREND_MIN_GAMES:
        return {
            "trend": "insufficient_data",
            "games_recent": len(games),
            "summary": f"Only {len(games)} game{'s' if len(games)!=1 else ''} tracked so far",
        }

    ref = get_reference_metrics(player)

    if is_p:
        total_ip = sum(as_float(g.get("inningsPitched", 0)) for g in games)
        total_er = sum(as_float(g.get("earnedRuns",     0)) for g in games)
        recent_era = (total_er / total_ip * 9.0) if total_ip > 0 else 99.0

        baseline_era = get_metric(ref, "ERA") if ref else 4.50
        if baseline_era <= 0:
            baseline_era = 4.50

        if recent_era < baseline_era * 0.80:
            trend   = "hot"
        elif recent_era > baseline_era * 1.25:
            trend   = "cold"
        else:
            trend   = "stable"
        summary = (
            f"ERA {recent_era:.2f} vs {baseline_era:.2f} baseline"
            f" ({len(games)} G, {total_ip:.1f} IP)"
        )
    else:
        # Use per-game OPS where at-bats ≥ 1
        ops_list = [as_float(g.get("ops", 0)) for g in games
                    if as_float(g.get("atBats", 0)) >= 1]
        if not ops_list:
            return {
                "trend": "insufficient_data",
                "games_recent": len(games),
                "summary": "No plate appearance data yet",
            }
        recent_ops = sum(ops_list) / len(ops_list)

        baseline_ops = get_metric(ref, "OPS") if ref else 0.720
        if baseline_ops <= 0:
            baseline_ops = 0.720

        if recent_ops > baseline_ops * 1.15:
            trend   = "hot"
        elif recent_ops < baseline_ops * 0.80:
            trend   = "cold"
        else:
            trend   = "stable"
        summary = (
            f"OPS {recent_ops:.3f} vs {baseline_ops:.3f} baseline"
            f" ({len(ops_list)} games)"
        )

    return {"trend": trend, "games_recent": len(games), "summary": summary}


def _get_season_intel_my_il(my_team) -> list:
    """
    Analyse your IL / injured roster players.
    Returns list of dicts sorted by stash score descending, each with a KEEP /
    CONSIDER DROPPING verdict so you can make informed hold decisions.
    """
    results = []
    for p in my_team.roster:
        slot   = get_lineup_slot(p)
        status = get_player_status(p)
        # Include anyone on IL/IR slot OR with an active injury flag
        if slot not in ("IL", "IR") and status in ("ACTIVE", "NORMAL", ""):
            continue

        stash   = get_stash_score(p)
        current = base_score(p)
        proj    = get_healthy_projected_pts(p)
        verdict = "KEEP" if stash >= STASH_SCORE_THRESHOLD else "CONSIDER DROPPING"
        trend   = get_season_trend(p)

        results.append({
            "name":          p.name,
            "pos":           ", ".join(get_player_slots(p)[:2]),
            "mlb":           get_player_team(p),
            "status":        status,
            "stash_score":   fmt(stash),
            "current_val":   fmt(current),
            "healthy_proj":  fmt(proj, 1),
            "verdict":       verdict,
            "trend":         trend["trend"],
            "trend_summary": trend["summary"],
            "headshot":      get_player_headshot_url(p),
            "headshot2":     get_player_headshot_url_mlb(p),
            "initials":      get_initials(p.name),
        })

    results.sort(key=lambda x: -float(x["stash_score"]))
    return results


def _get_season_intel_il_stash(league, my_team) -> list:
    """
    Find stash-worthy IL players rostered on OTHER teams.
    These are players you might want to trade for, or monitor for waiver cuts.
    """
    my_names = {p.name for p in my_team.roster}
    targets  = []

    for team in league.teams:
        if team.team_name == my_team.team_name:
            continue
        for p in team.roster:
            slot   = get_lineup_slot(p)
            status = get_player_status(p)
            if slot not in ("IL", "IR") and status in ("ACTIVE", "NORMAL", ""):
                continue
            if p.name in my_names:
                continue
            stash = get_stash_score(p)
            if stash < STASH_SCORE_THRESHOLD:
                continue
            targets.append({
                "name":         p.name,
                "pos":          ", ".join(get_player_slots(p)[:2]),
                "mlb":          get_player_team(p),
                "status":       status,
                "owned_by":     team.team_name,
                "stash_score":  fmt(stash),
                "healthy_proj": fmt(get_healthy_projected_pts(p), 1),
                "headshot":     get_player_headshot_url(p),
                "headshot2":    get_player_headshot_url_mlb(p),
                "initials":     get_initials(p.name),
            })

    targets.sort(key=lambda x: -float(x["stash_score"]))
    return targets[:8]


def _get_season_intel_fa_targets(league, my_team) -> list:
    """
    Find free agents with high healthy base scores that are worth rostering
    now for long-season value (e.g. a closer whose team is about to fire the
    incumbent, or a SP returning from injury).
    """
    rostered = {p.name for t in league.teams for p in t.roster}
    try:
        fa_pool = league.free_agents(size=300)
    except Exception:
        fa_pool = []

    targets = []
    for p in fa_pool:
        if p.name in rostered:
            continue
        stash  = get_stash_score(p)
        status = get_player_status(p)
        if stash < SEASON_INTEL_FA_THRESHOLD:
            continue
        targets.append({
            "name":         p.name,
            "pos":          ", ".join(get_player_slots(p)[:2]),
            "mlb":          get_player_team(p),
            "status":       status,
            "stash_score":  fmt(stash),
            "healthy_proj": fmt(get_healthy_projected_pts(p), 1),
            "headshot":     get_player_headshot_url(p),
            "headshot2":    get_player_headshot_url_mlb(p),
            "initials":     get_initials(p.name),
        })

    targets.sort(key=lambda x: -float(x["stash_score"]))
    return targets[:10]


def _prefetch_all_ages(league):
    """
    Batch-fetch player ages for every player across all league teams.

    Two tiers:
      Tier 1 — MLBAM ID known (via Statcast name index): batch-fetched in ≤2
               round-trips via /api/v1/people?personIds=...
      Tier 2 — MLBAM ID unknown (rookies / players not in Statcast cache):
               looked up individually by name via /api/v1/people/search
               (also cached per process run so re-runs are free)

    Without this prefetch, _player_row() fires one HTTP call per uncached
    player — 14 teams × ~25 players = ~350 serial requests.
    """
    tier1: list[tuple[str, str]] = []   # [(espn_id, mlbam_id)]
    tier2: list[tuple[str, str]] = []   # [(espn_id, player_name)]

    for team in league.teams:
        for player in team.roster:
            eid = get_espn_id(player)
            if eid and eid in _AGE_CACHE:
                continue
            mlbam = get_mlbam_id(player)   # now resolves via SC name index
            if mlbam:
                tier1.append((eid, mlbam))
            else:
                tier2.append((eid, getattr(player, "name", "")))

    # ── Tier 1: batch MLBAM lookup ─────────────────────────────────────────
    chunk_size = 200
    total_t1 = 0
    for i in range(0, len(tier1), chunk_size):
        chunk   = tier1[i : i + chunk_size]
        ids_str = ",".join(m for _, m in chunk)
        try:
            url     = (f"https://statsapi.mlb.com/api/v1/people"
                       f"?personIds={ids_str}&fields=people,id,currentAge")
            data    = _mlb_get(url, timeout=15)
            age_map = {str(p.get("id", "")): int(p.get("currentAge", -1))
                       for p in data.get("people", []) if p.get("id")}
            for eid, mlbam in chunk:
                if eid:
                    _AGE_CACHE[eid] = age_map.get(mlbam, -1)
            total_t1 += len(chunk)
        except Exception as exc:
            print(f"  [age prefetch t1] chunk failed: {exc}")

    # ── Tier 2: name-search fallback (individual, cached) ──────────────────
    # _mlbam_from_name is already cached in _NAME_TO_MLBAM_CACHE; calling it
    # for each player serialises the lookups but benefits from the cache
    # so each unique name is only ever resolved once across runs.
    total_t2 = 0
    for eid, name in tier2:
        if not name or (eid and eid in _AGE_CACHE):
            continue
        mlbam = _mlbam_from_name(name)
        age   = -1
        if mlbam:
            try:
                url  = (f"https://statsapi.mlb.com/api/v1/people/{mlbam}"
                        f"?fields=people,currentAge")
                data = _mlb_get(url, timeout=6)
                ppl  = data.get("people", [{}])
                age  = int(ppl[0].get("currentAge", -1)) if ppl else -1
            except Exception:
                pass
        if eid:
            _AGE_CACHE[eid] = age
        total_t2 += 1

    n_chunks = max(1, (len(tier1) + chunk_size - 1) // chunk_size)
    print(f"  Age prefetch: {total_t1} via MLBAM index ({n_chunks} req) + "
          f"{total_t2} via name search")


def get_model_projected_pts(player) -> float:
    """
    Our analytical projection for a player — independent of ESPN's own estimate.

    Uses Steamer+ZiPS consensus (Phase 3) → FanGraphs prior-season (Phase 1)
    → ESPN avg×26 as a last resort.  Deliberately skips ESPN's projected_total_points
    so we can compare our external-data estimate against ESPN's internal number.
    """
    # Phase 3: Steamer/ZiPS consensus
    proj_m = get_projection_metrics(player)
    if proj_m:
        consensus = as_float(proj_m.get("consensus_pts", 0))
        if consensus > 5:
            return consensus

    # Phase 1 fallback: prior-season FanGraphs counting stats
    metrics = get_reference_metrics(player)
    if metrics:
        pts = _pitcher_pts_from_stats(metrics) if is_pitcher(player) \
              else _hitter_pts_from_stats(metrics)
        if pts > 5:
            return pts

    # Last resort: ESPN per-game average × 26 scoring periods
    avg = as_float(safe_get(player, "avg_points", default=0))
    if avg > 0:
        return avg * 26
    return 0.0


def build_lineup_lab(league, my_team) -> dict:
    """
    Lineup Lab: optimal lineup construction + per-position impact analysis
    + team-by-team comparison to identify trade targets.

    Returns
    -------
    {
        "optimal"      : list of slot dicts (unique-player optimal lineup)
        "pos_metrics"  : dict keyed by position with depth/impact stats
        "team_lineups" : dict keyed by team_name with slot-level gap data
        "all_team_names": list[str] (sorted, my team first)
        "my_team_name" : str
        "error"        : str or None
    }
    """
    # ── Slot definitions ────────────────────────────────────────────────────────
    # (slot_name, count, family)
    SLOT_ORDER = [
        ("C",    1, "hitter"),
        ("1B",   1, "hitter"),
        ("2B",   1, "hitter"),
        ("3B",   1, "hitter"),
        ("SS",   1, "hitter"),
        ("OF",   3, "hitter"),
        ("UTIL", 1, "hitter"),
        ("SP",   4, "pitcher"),
        ("RP",   3, "pitcher"),
    ]

    try:
        # ── 1. Collect all players ───────────────────────────────────────────────
        # Build ownership map: player_name → fantasy_team_name
        ownership: dict[str, str] = {}
        for team in league.teams:
            for p in team.roster:
                ownership[p.name] = team.team_name

        # Gather all players: rostered + free agents (top 300)
        all_players: dict[str, object] = {}
        for team in league.teams:
            for p in team.roster:
                all_players[p.name] = p
        try:
            for p in league.free_agents(size=300):
                all_players.setdefault(p.name, p)
        except Exception:
            pass

        # ── 2. Per-position pool: eligibility + projected pts ────────────────────
        # Canonical position set (excluding utility/bench/IL)
        SCORING_POSITIONS = {"C", "1B", "2B", "3B", "SS", "OF", "SP", "RP", "P"}

        def _eligible_slots(player) -> list[str]:
            return [
                s for s in get_player_slots(player)
                if s in SCORING_POSITIONS
            ]

        pos_pool: dict[str, list] = {pos: [] for pos in SCORING_POSITIONS}
        pos_pool["UTIL"] = []   # hitters eligible for UTIL

        for name, player in all_players.items():
            proj = get_projected_pts(player)
            repl = get_replacement_level(player)
            var  = max(0.0, proj - repl)
            bs   = base_score(player)
            slots = _eligible_slots(player)
            owner = ownership.get(name, "FA")
            is_fa = (owner == "FA")
            status = get_player_status(player)
            slot   = get_lineup_slot(player)
            on_il  = slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", "")

            entry = {
                "name":    name,
                "mlb":     get_player_team(player),
                "owner":   owner,
                "is_fa":   is_fa,
                "proj":    proj,
                "var":     var,
                "base":    bs,
                "repl":    repl,
                "on_il":   on_il,
                "is_p":    is_pitcher(player),
                "is_sp":   is_starter_role(player),
                "is_rp":   is_reliever_role(player),
                "slots":   slots,
                "initials":get_initials(name),
            }

            for s in slots:
                pos_pool[s].append(entry)

            # UTIL: any non-pitcher
            if not is_pitcher(player) and slots:
                pos_pool["UTIL"].append(entry)

        # Sort each pool by projected pts desc
        for pool in pos_pool.values():
            pool.sort(key=lambda e: -e["proj"])

        # ── 3. Build optimal lineup (unique player assignment) ───────────────────
        # Greedy in scarcity order: C, SS, 2B, 3B, 1B, OF×3, UTIL, SP×4, RP×3
        GREEDY_ORDER = ["C", "SS", "2B", "3B", "1B", "OF", "OF", "OF",
                        "UTIL", "SP", "SP", "SP", "SP", "RP", "RP", "RP"]
        used: set[str] = set()
        optimal_slots: list[dict] = []

        slot_group_count: dict[str, int] = {}
        for s in GREEDY_ORDER:
            # Pick best unassigned eligible player
            pool = pos_pool.get(s, [])
            chosen = None
            for e in pool:
                if e["name"] not in used:
                    # For UTIL: must not have been used as hitter already
                    chosen = e
                    break
            if chosen:
                used.add(chosen["name"])
            else:
                chosen = {"name": "—", "mlb": "", "owner": "", "is_fa": False,
                          "proj": 0.0, "var": 0.0, "base": 0.0, "repl": 0.0,
                          "on_il": False, "is_p": False, "is_sp": False,
                          "is_rp": False, "slots": [], "initials": "?"}

            slot_group_count[s] = slot_group_count.get(s, 0) + 1
            label = s if slot_group_count[s] == 1 else f"{s}{slot_group_count[s]}"
            optimal_slots.append({
                "slot":    label,
                "pos":     s,
                **chosen,
            })

        # ── 4. Position impact metrics ────────────────────────────────────────────
        METRIC_POSITIONS = ["C", "1B", "2B", "3B", "SS", "OF", "SP", "RP"]
        pos_metrics: dict[str, dict] = {}

        for pos in METRIC_POSITIONS:
            pool  = pos_pool.get(pos, [])
            repl  = MARKET["replacement_levels"].get(pos, 0.0)
            if pos == "SP" and MARKET["sp_repl"] > 0:
                repl = MARKET["sp_repl"]
            elif pos == "RP" and MARKET["rp_repl"] > 0:
                repl = MARKET["rp_repl"]

            n_above   = sum(1 for e in pool if e["proj"] > repl and not e["on_il"])
            n_rostered= sum(1 for e in pool if not e["is_fa"])
            top_pts   = pool[0]["proj"] if pool else 0.0
            top_var   = max(0.0, top_pts - repl)
            # Median pts of starters (starter = within N_TEAMS × slots slots)
            n_starters = SLOTS_PER_TEAM.get(pos, 1) * N_TEAMS
            starter_tier = [e["proj"] for e in pool[:n_starters] if not e["on_il"]]
            avg_starter  = sum(starter_tier) / len(starter_tier) if starter_tier else 0.0
            # Impact score = how much the best player outperforms the average starter
            impact = round(100 * (top_pts - avg_starter) / (top_pts + 1), 1) if top_pts > 0 else 0.0
            scarcity_mult = get_scarcity_multiplier(
                all_players.get(pool[0]["name"])
            ) if pool else 1.0

            # Top 6 for the dropdown display
            top_n = []
            for e in pool[:8]:
                if not e["on_il"]:
                    top_n.append({
                        "name":  e["name"],
                        "mlb":   e["mlb"],
                        "owner": e["owner"],
                        "is_fa": e["is_fa"],
                        "proj":  round(e["proj"], 0),
                        "var":   round(e["var"], 0),
                        "base":  round(e["base"], 1),
                    })

            # Positional grade (scarcity-adjusted)
            # A = rare premium position (C, SS), B = moderate (2B, 3B), C = deep (OF, 1B)
            grade_score = n_above
            if grade_score <= 14:
                pos_grade = "A"
            elif grade_score <= 22:
                pos_grade = "B"
            elif grade_score <= 35:
                pos_grade = "C"
            else:
                pos_grade = "D"

            pos_metrics[pos] = {
                "repl":         round(repl, 1),
                "n_above_repl": n_above,
                "n_rostered":   n_rostered,
                "top_pts":      round(top_pts, 0),
                "top_var":      round(top_var, 0),
                "avg_starter":  round(avg_starter, 0),
                "impact":       impact,
                "grade":        pos_grade,
                "top_players":  top_n,
            }

        # ── 5. Per-team lineup data ───────────────────────────────────────────────
        # For each team × each position slot, find their best active player
        # and compute the gap to the league-optimal at that slot.

        # Build optimal pts at each position for gap calculation
        optimal_by_pos: dict[str, float] = {
            pos: pos_pool[pos][0]["proj"] if pos_pool.get(pos) else 0.0
            for pos in METRIC_POSITIONS
        }
        # Add OF optimal (average of top 3)
        of_top3 = [e["proj"] for e in pos_pool.get("OF", [])[:3]]
        optimal_by_pos["OF_avg"] = sum(of_top3) / len(of_top3) if of_top3 else 0.0

        team_lineups: dict[str, dict] = {}
        all_team_names_raw = []

        for team in league.teams:
            tname = team.team_name

            # Best active player per position slot on this team
            team_by_pos: dict[str, list] = {pos: [] for pos in METRIC_POSITIONS}
            team_by_pos["UTIL"] = []

            for p in team.roster:
                status = get_player_status(p)
                slot   = get_lineup_slot(p)
                on_il  = slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", "")
                if on_il:
                    continue
                proj = get_projected_pts(p)
                var  = max(0.0, proj - get_replacement_level(p))
                bs   = base_score(p)
                slots_eligible = _eligible_slots(p)
                entry = {
                    "name":  p.name,
                    "mlb":   get_player_team(p),
                    "proj":  proj,
                    "var":   var,
                    "base":  bs,
                    "on_il": on_il,
                }
                for s in slots_eligible:
                    team_by_pos.setdefault(s, []).append(entry)
                if not is_pitcher(p) and slots_eligible:
                    team_by_pos["UTIL"].append(entry)

            # Sort each team slot by proj pts
            for pos in team_by_pos:
                team_by_pos[pos].sort(key=lambda e: -e["proj"])

            # Build slot-level gap to optimal
            def _gap_entry(pos: str) -> dict:
                opts     = team_by_pos.get(pos, [])
                best     = opts[0] if opts else None
                opt_pts  = optimal_by_pos.get(pos, 0.0)
                if best:
                    gap_pts  = opt_pts - best["proj"]
                    gap_pct  = round(100 * gap_pts / (opt_pts + 1), 1)
                    grade    = ("A" if gap_pct <= 8 else
                                "B" if gap_pct <= 20 else
                                "C" if gap_pct <= 35 else "D")
                else:
                    gap_pts  = opt_pts
                    gap_pct  = 100.0
                    grade    = "F"

                return {
                    "name":    best["name"] if best else "—",
                    "mlb":     best["mlb"]  if best else "",
                    "proj":    round(best["proj"], 0) if best else 0,
                    "var":     round(best["var"],  0) if best else 0,
                    "base":    round(best["base"],  1) if best else 0,
                    "gap_pts": round(gap_pts, 0),
                    "gap_pct": gap_pct,
                    "grade":   grade,
                    # Who is the league-optimal player at this slot?
                    # Use pos_pool (league-wide), NOT opts (team-specific — may be empty)
                    "opt_name": pos_pool[pos][0]["name"] if pos_pool.get(pos) else "—",
                    "opt_pts": round(opt_pts, 0),
                }

            slots_data: dict[str, dict] = {}
            for pos in METRIC_POSITIONS:
                slots_data[pos] = _gap_entry(pos)

            # Add 3 OF instead of 1 (total_proj_full accounts for all 3 OF slots)
            of_pts = sum(e["proj"] for e in team_by_pos.get("OF", [])[:3])
            total_proj_full = (
                (team_by_pos.get("C",  [{}])[0].get("proj", 0) if team_by_pos.get("C")  else 0) +
                (team_by_pos.get("1B", [{}])[0].get("proj", 0) if team_by_pos.get("1B") else 0) +
                (team_by_pos.get("2B", [{}])[0].get("proj", 0) if team_by_pos.get("2B") else 0) +
                (team_by_pos.get("3B", [{}])[0].get("proj", 0) if team_by_pos.get("3B") else 0) +
                (team_by_pos.get("SS", [{}])[0].get("proj", 0) if team_by_pos.get("SS") else 0) +
                of_pts +
                (team_by_pos.get("SP", [{}])[0].get("proj", 0) if team_by_pos.get("SP") else 0) +
                (team_by_pos.get("RP", [{}])[0].get("proj", 0) if team_by_pos.get("RP") else 0)
            )

            # Overall team grade = weighted avg of slot grades
            grade_map = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
            grade_scores = [grade_map.get(slots_data[p]["grade"], 0) for p in METRIC_POSITIONS]
            avg_grade_score = sum(grade_scores) / len(grade_scores) if grade_scores else 0
            if avg_grade_score >= 3.5:
                overall_grade = "A"
            elif avg_grade_score >= 2.8:
                overall_grade = "B"
            elif avg_grade_score >= 2.0:
                overall_grade = "C"
            elif avg_grade_score >= 1.2:
                overall_grade = "D"
            else:
                overall_grade = "F"

            team_lineups[tname] = {
                "slots":         slots_data,
                "total_proj":    round(total_proj_full, 0),
                "overall_grade": overall_grade,
                "is_mine":       MY_TEAM_NAME.lower() in tname.lower(),
            }
            all_team_names_raw.append(tname)

        # Sort team names: my team first, then alphabetical
        all_team_names = sorted(
            all_team_names_raw,
            key=lambda n: (0 if MY_TEAM_NAME.lower() in n.lower() else 1, n)
        )

        # League-wide above-replacement summary per position
        league_above_repl = {
            pos: pos_metrics[pos]["n_above_repl"]
            for pos in METRIC_POSITIONS
        }

        # ── Format-edge trade targets ──────────────────────────────────────────
        # Standard ESPN scoring assumptions used for comparison:
        #   Hitters: K = 0 (neutral), TB not scored separately, SB = 2
        #   Pitchers: HD = 1, IP = 1, ER = -1
        # This league advantages vs standard:
        #   K = -1 (batters penalised — low-K hitters undervalued externally)
        #   HD = 7 (5+2 SVHD) vs 1 → setup men massively undervalued
        #   IP = 3 vs 1 → workhouse SPs undervalued
        #   ER = -2 vs -1 → clean ERA SPs worth more here
        #   TB = 1 → contact hitters / high-AVG players gain vs sluggers
        ESPN_STD_K_HITTER   = 0    # standard ESPN: K is neutral for hitters
        ESPN_STD_HD         = 1    # standard ESPN: 1 pt per hold
        ESPN_STD_IP         = 1    # standard ESPN: ~1 pt per IP
        ESPN_STD_ER         = -1   # standard ESPN: -1 per ER
        LEAGUE_K_HITTER     = PITCHING_SCORING.get("K",  1)  # K=1 for pitchers
        LEAGUE_BATTER_K     = BATTING_SCORING.get("K", -1)   # K=-1 for batters
        LEAGUE_HD           = PITCHING_SCORING.get("HD", 5) + PITCHING_SCORING.get("SVHD", 2)
        LEAGUE_IP           = PITCHING_SCORING.get("IP", 3)
        LEAGUE_ER           = PITCHING_SCORING.get("ER", -2)
        TYPICAL_HD_PER_FULL_SEASON  = 30   # benchmark: high-hold setup man
        TYPICAL_IP_PER_GS_ELITE     = 6.5  # benchmark: elite workhorse
        TYPICAL_IP_PER_GS_AVERAGE   = 5.5  # benchmark: average SP
        TYPICAL_PA_PER_SEASON       = 520

        def _format_advantage(player) -> dict:
            """
            Return this-league format-edge pts + reason for a player.
            Positive = undervalued by managers using standard ESPN thinking.
            """
            ref  = get_reference_metrics(player)
            sc   = get_statcast_metrics(player)
            adv_pts  = 0.0
            reasons  = []
            category = "STANDARD"

            if is_pitcher(player):
                hd  = get_metric(ref, "HD", "HLD")
                ip  = get_metric(ref, "IP")
                gs  = get_metric(ref, "GS")
                er  = get_metric(ref, "ER")
                avg_ip_per_start = ip / gs if gs > 0 else 0.0

                # HOLDS EDGE — the single biggest format advantage
                if hd >= 10 and is_reliever_role(player):
                    adv_pts += hd * (LEAGUE_HD - ESPN_STD_HD)  # 6 extra pts/hold
                    reasons.append(
                        f"{int(hd)} holds/yr × {LEAGUE_HD - ESPN_STD_HD} "
                        f"extra pts/hold vs standard ESPN = +{round(hd * (LEAGUE_HD - ESPN_STD_HD)):,} pts"
                    )
                    category = "HOLDS_EDGE"

                # WORKHORSE SP — extra IP pts vs standard
                if is_starter_role(player) and gs >= 10 and avg_ip_per_start > TYPICAL_IP_PER_GS_AVERAGE:
                    extra_ip_per_start = avg_ip_per_start - TYPICAL_IP_PER_GS_AVERAGE
                    ip_adv = extra_ip_per_start * (LEAGUE_IP - ESPN_STD_IP) * gs
                    adv_pts += ip_adv
                    reasons.append(
                        f"{avg_ip_per_start:.1f} IP/GS vs {TYPICAL_IP_PER_GS_AVERAGE} avg "
                        f"× {LEAGUE_IP - ESPN_STD_IP} extra pts/IP × {int(gs)} GS = +{round(ip_adv):,} pts"
                    )
                    if category == "STANDARD":
                        category = "WORKHORSE_SP"

                # CLEAN ERA — ER=-2 here vs -1 standard, so low-ER pitchers gain
                if er > 0 and ip > 0:
                    era = er / ip * 9
                    if era < 3.30:
                        er_adv = er * abs(LEAGUE_ER - ESPN_STD_ER)   # 1 extra pt per ER saved
                        adv_pts += er_adv * 0.3  # partial credit (most managers price ERA somewhat)
                        reasons.append(
                            f"ERA {era:.2f} — each ER costs {abs(LEAGUE_ER)} pts here "
                            f"vs {abs(ESPN_STD_ER)} standard, doubling the ERA penalty"
                        )
                        if category == "STANDARD":
                            category = "CLEAN_ERA_SP"

            else:  # hitter
                kpct = get_metric(ref, "Kp", "K%")   # cache key is "Kp"; "K%" alias for safety
                pa   = get_metric(ref, "PA") or TYPICAL_PA_PER_SEASON
                so   = get_metric(ref, "SO", "K")
                h    = get_metric(ref, "H")
                avg  = get_metric(ref, "AVG")
                iso  = get_metric(ref, "ISO")
                tb   = get_metric(ref, "TB")
                bb   = get_metric(ref, "BBp", "BB%")  # cache key is "BBp"; "BB%" alias for safety

                # LOW-K HITTER — other managers don't price K=-1
                if kpct > 0 and kpct < 0.18 and so >= 20:
                    # League avg K% ≈ 22%. This player's K saving vs avg:
                    avg_kpct   = 0.22
                    saved_ks   = max(0.0, (avg_kpct - kpct) * pa)
                    k_adv      = saved_ks * abs(LEAGUE_BATTER_K - ESPN_STD_K_HITTER)
                    adv_pts   += k_adv
                    reasons.append(
                        f"{kpct*100:.0f}% K-rate vs 22% avg → saves ~{int(saved_ks)} "
                        f"Ks/yr × 1pt = +{round(k_adv):,} pts vs ESPN valuation"
                    )
                    category = "LOW_K_HITTER"
                elif kpct >= 0.28 and so >= 50:
                    # High-K hitter — DISADVANTAGE (I want to sell these)
                    avg_kpct  = 0.22
                    extra_ks  = max(0.0, (kpct - avg_kpct) * pa)
                    k_penalty = extra_ks * abs(LEAGUE_BATTER_K - ESPN_STD_K_HITTER)
                    adv_pts  -= k_penalty
                    reasons.append(
                        f"{kpct*100:.0f}% K-rate → {int(extra_ks)} extra Ks/yr "
                        f"× 1pt penalty = −{round(k_penalty):,} pts vs ESPN valuation"
                    )
                    category = "HIGH_K_AVOID"

                # CONTACT / TB BONUS — singles score here via TB=1
                # Compare to a pure HR hitter: in standard ESPN a single=1pt (R+RBI opportunity)
                # Here, a single also = 1 TB. High-AVG low-K hitters benefit.
                if avg >= 0.285 and iso <= 0.180 and kpct < 0.20:
                    # Estimate TB advantage: singles are valued at TB=1 here but
                    # standard ESPN doesn't have a separate TB column (uses 1B=1, 2B=2 etc)
                    # Rough: contact hitters with high AVG earn ~20-40 extra pts from
                    # base TB pts vs pure counting (R/HR/RBI) formats
                    singles_est = max(0.0, h - tb * 0.5) if tb > 0 else 0
                    if singles_est > 40:
                        tb_adv = singles_est * 0.3   # conservative estimate
                        adv_pts += tb_adv
                        reasons.append(
                            f".{int(avg*1000)} AVG, {iso:.3f} ISO — "
                            f"contact hitter gains from TB=1 scoring (singles count)"
                        )
                        if category == "STANDARD":
                            category = "CONTACT_TB"

            return {
                "adv_pts":  round(adv_pts, 0),
                "reasons":  reasons,
                "category": category,
            }

        # ── My team's weakest slots (need multiplier) ──────────────────────────
        my_lineup = team_lineups.get(MY_TEAM_NAME, {})
        # Fall back: search for team name match
        if not my_lineup:
            for tname, tdata in team_lineups.items():
                if tdata.get("is_mine"):
                    my_lineup = tdata
                    break
        my_slots_data = my_lineup.get("slots", {})

        # Position urgency: gap_pct of my weakest slot at each position
        def _pos_urgency(pos: str) -> float:
            slot = my_slots_data.get(pos, {})
            return slot.get("gap_pct", 0.0)

        # ── My sell-high players (to suggest as trade bait) ──────────────────
        my_sell_candidates = []
        for p in my_team.roster:
            slot_s = get_lineup_slot(p)
            if slot_s in ("IL", "IR"):
                continue
            espn_p = as_float(safe_get(p, "projected_total_points", default=0))
            our_p  = get_model_projected_pts(p)
            if espn_p < 20 or our_p < 20:
                continue
            gap_s  = espn_p - our_p   # positive = ESPN overvalues = I can sell
            fa_s   = _format_advantage(p)
            # Add to sell list if ESPN overvalues OR format disadvantages them
            if gap_s >= 15 or fa_s["adv_pts"] <= -30:
                my_sell_candidates.append({
                    "name":    p.name,
                    "pos":    ", ".join(get_player_slots(p)[:2]),
                    "pts":    round(our_p, 0),
                    "espn_pts": round(espn_p, 0),
                    "gap":    round(gap_s, 0),   # how much ESPN overvalues them
                    "category": fa_s["category"],
                    "sell_reason": (
                        "ESPN overvalues vs our model" if gap_s >= 15
                        else f"Format disadvantage ({fa_s['category']})"
                    ),
                })
        my_sell_candidates.sort(key=lambda r: -(r["gap"] + max(0, -_format_advantage(
            next((p for p in my_team.roster if p.name == r["name"]), type('_', (), {'name': r['name']})())
        )["adv_pts"])))

        # ── Build trade target list ────────────────────────────────────────────
        trade_targets_raw: list = []
        for team in league.teams:
            if MY_TEAM_NAME.lower() in team.team_name.lower():
                continue
            for player in team.roster:
                pslot  = get_lineup_slot(player)
                if pslot in ("IL", "IR"):
                    continue
                status = get_player_status(player)
                if status not in ("ACTIVE", "NORMAL", ""):
                    continue

                our_proj  = get_model_projected_pts(player)
                espn_proj = as_float(safe_get(player, "projected_total_points", default=0))
                if our_proj < 30 and espn_proj < 30:
                    continue

                fa = _format_advantage(player)
                if fa["adv_pts"] == 0 and fa["category"] == "STANDARD":
                    continue   # no format edge — skip

                # Position need: how much does my team need this position?
                eligible = [
                    s for s in get_player_slots(player)
                    if s in METRIC_POSITIONS
                ]
                need_score = max((_pos_urgency(pos) for pos in eligible), default=0.0)

                # Overall priority = format_adv + weighted position need
                priority = fa["adv_pts"] + need_score * 0.5

                # Suggest a trade offer: match sell candidates by similar pts
                target_pts = our_proj
                offer = sorted(
                    my_sell_candidates,
                    key=lambda s: abs(s["pts"] - target_pts)
                )[:2]

                trade_targets_raw.append({
                    "player":       player.name,
                    "fantasy_team": team.team_name,
                    "pos":          ", ".join(get_player_slots(player)[:2]),
                    "mlb":          get_player_team(player),
                    "our_proj":     round(our_proj, 0),
                    "espn_proj":    round(espn_proj, 0),
                    "model_gap":    round(our_proj - espn_proj, 0),
                    "format_adv":   int(fa["adv_pts"]),
                    "category":     fa["category"],
                    "reasons":      fa["reasons"],
                    "need_score":   round(need_score, 1),
                    "priority":     round(priority, 1),
                    "offer":        offer,
                    "headshot":     get_player_headshot_url(player),
                    "initials":     get_initials(player.name),
                })

        trade_targets_raw.sort(key=lambda r: -r["priority"])
        # Separate by category for display
        holds_targets   = [t for t in trade_targets_raw if t["category"] == "HOLDS_EDGE"][:6]
        lowk_targets    = [t for t in trade_targets_raw if t["category"] == "LOW_K_HITTER"][:5]
        workhorse_targets=[t for t in trade_targets_raw if t["category"] == "WORKHORSE_SP"][:4]
        other_targets   = [t for t in trade_targets_raw
                           if t["category"] not in ("HOLDS_EDGE","LOW_K_HITTER",
                                                     "WORKHORSE_SP","HIGH_K_AVOID")][:3]
        avoid_targets   = [t for t in trade_targets_raw if t["category"] == "HIGH_K_AVOID"][:4]

        lab_trade_data = {
            "holds_targets":    holds_targets,
            "lowk_targets":     lowk_targets,
            "workhorse_targets":workhorse_targets,
            "other_targets":    other_targets,
            "avoid_targets":    avoid_targets,
            "sell_candidates":  my_sell_candidates[:8],
            "category_explainers": {
                "HOLDS_EDGE":   f"Hold = {LEAGUE_HD} pts here vs ~{ESPN_STD_HD} pts in standard ESPN. "
                                f"Other managers price setup men as if holds are worthless.",
                "LOW_K_HITTER": f"K = −1 pt here vs 0 in standard ESPN. "
                                f"Each avoided strikeout saves a real point. "
                                f"Power sluggers with 28%+ K rates are disasters in this format.",
                "WORKHORSE_SP": f"IP = {LEAGUE_IP} pts here vs ~{ESPN_STD_IP} in standard ESPN. "
                                f"A pitcher who averages 7 IP/start earns {round((7-5.5)*(LEAGUE_IP-ESPN_STD_IP)*30):,} "
                                f"extra pts/season vs a 5.5-IP guy. Other managers value W/ERA, not IP.",
                "CONTACT_TB":   f"TB = 1 pt per base. Singles count. "
                                f"High-AVG contact hitters outperform their ESPN ranking in this format.",
                "CLEAN_ERA_SP": f"ER = {abs(LEAGUE_ER)} pts here vs {abs(ESPN_STD_ER)} in standard. "
                                f"Doubly penalised — clean-ERA SPs are worth more than their record suggests.",
            },
        }

        return {
            "optimal":          optimal_slots,
            "pos_metrics":      pos_metrics,
            "team_lineups":     team_lineups,
            "all_team_names":   all_team_names,
            "my_team_name":     MY_TEAM_NAME,
            "league_above_repl":league_above_repl,
            "lab_trades":       lab_trade_data,
            "error":            None,
        }

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {
            "optimal":          [],
            "pos_metrics":      {},
            "team_lineups":     {},
            "all_team_names":   [],
            "my_team_name":     MY_TEAM_NAME,
            "league_above_repl":{},
            "lab_trades":       {},
            "error":            str(exc),
        }


def build_trade_value_comparison(league, my_team) -> dict:
    """
    Compare our analytical projection vs ESPN's projection for every rostered player.

    Returns a dict with two lists:
      buy_targets  – players on OTHER teams our model values significantly more than ESPN.
                     ESPN owners underestimate them → cheap acquisition target.
      sell_high    – players on MY TEAM ESPN values significantly more than our model.
                     ESPN owners overvalue them → trade while their perceived value is high.

    Each row dict contains:
      player, fantasy_team, pos, mlb, our_proj, espn_proj, gap, gap_pct,
      pct_owned, age, age_tier, headshot, headshot2, initials,
      is_pitcher, adv, mlbam_id, espn_id
    """
    MIN_PROJ        = 20.0   # skip players with too-low projections (small sample)
    BUY_THRESHOLD   = 20.0   # our model values the player 20+ pts more than ESPN
    SELL_THRESHOLD  = 20.0   # ESPN values the player 20+ pts more than our model
    MAX_BUY         = 25     # return top N buy targets
    MAX_SELL        = 15     # return top N sell-high candidates

    my_name_lc = MY_TEAM_NAME.lower()
    buy_targets: list = []
    sell_high:   list = []

    for team in league.teams:
        is_mine = my_name_lc in team.team_name.lower()
        for player in team.roster:
            slot = get_lineup_slot(player)
            if slot in ("IL", "IR"):
                continue                      # skip injured players — distorts projection

            espn_proj = as_float(safe_get(player, "projected_total_points", default=0))
            our_proj  = get_model_projected_pts(player)

            # Only compare when both sides have meaningful data
            if espn_proj < MIN_PROJ or our_proj < MIN_PROJ:
                continue

            gap     = round(our_proj  - espn_proj, 1)   # positive = we value more
            gap_pct = round(gap / espn_proj * 100, 1) if espn_proj else 0.0

            _age = _fetch_player_age(player)
            _at  = age_tier(_age)

            row = {
                "player":       player.name,
                "fantasy_team": team.team_name,
                "is_mine":      is_mine,
                "pos":          ", ".join(get_player_slots(player)[:2]),
                "mlb":          get_player_team(player),
                "our_proj":     round(our_proj,  1),
                "espn_proj":    round(espn_proj, 1),
                "gap":          gap,
                "gap_pct":      gap_pct,
                "pct_owned":    round(as_float(safe_get(player, "percent_owned", default=0)), 1),
                "age":          _age,
                "age_tier":     _at,
                "headshot":     get_player_headshot_url(player),
                "headshot2":    get_player_headshot_url_mlb(player),
                "initials":     get_initials(player.name),
                "avatar_seed":  avatar_seed(player.name),
                "is_pitcher":   "true" if is_pitcher(player) else "false",
                "adv":          _build_adv_json(player),
                "mlbam_id":     get_mlbam_id(player),
                "espn_id":      get_espn_id(player),
                "base":         fmt(base_score(player)),
                "fit":          fmt(fit_score(player, team)),
            }

            if not is_mine and gap >= BUY_THRESHOLD:
                buy_targets.append(row)
            elif is_mine and gap <= -SELL_THRESHOLD:
                sell_high.append(row)

    buy_targets.sort(key=lambda r: -r["gap"])
    sell_high.sort(key=lambda r:  r["gap"])   # most-negative = ESPN overvalues most

    print(f"  Trade targets: {len(buy_targets[:MAX_BUY])} buys, "
          f"{len(sell_high[:MAX_SELL])} sell-highs")
    return {
        "buy_targets": buy_targets[:MAX_BUY],
        "sell_high":   sell_high[:MAX_SELL],
    }


def _load_fp_actual_cache() -> None:
    """
    Load fp_actual_cache.json into _FP_ACTUAL_CACHE if it exists and is < 30 min old.
    Called once at the start of build_fp_actual_cache().
    """
    import time as _time
    global _FP_ACTUAL_CACHE
    if not os.path.exists(_FP_ACTUAL_CACHE_PATH):
        return
    try:
        age_m = (_time.time() - os.path.getmtime(_FP_ACTUAL_CACHE_PATH)) / 60
        if age_m > 30:
            return  # stale — recompute from stats
        with open(_FP_ACTUAL_CACHE_PATH) as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("season") == YEAR:
            _FP_ACTUAL_CACHE.update(data.get("players", {}))
            print(f"  FP Actual Cache: loaded {len(_FP_ACTUAL_CACHE)} players ({age_m:.0f}m old)")
    except Exception:
        pass


def _save_fp_actual_cache() -> None:
    """Persist _FP_ACTUAL_CACHE to disk — only non-zero values are saved.
    Zero means 'no data yet this run'; it should be retried on the next run,
    not treated as a confirmed 0-point player."""
    try:
        nonzero = {k: v for k, v in _FP_ACTUAL_CACHE.items() if v > 0}
        with open(_FP_ACTUAL_CACHE_PATH, "w") as f:
            json.dump({"season": YEAR, "players": nonzero}, f, separators=(",", ":"))
    except Exception:
        pass


def _espn_actual_season_pts(player) -> float:
    """
    Read actual season FP directly from the ESPN player object.

    ESPN API (espn_api.baseball.Player) stores stats keyed by INTEGER scoring
    period IDs — NOT by string keys like "002026".  Period 0 = full-season
    cumulative.  The library also exposes this as player.total_points directly.

    This is the correct and only ESPN source for season-to-date actual FP.
    """
    try:
        # Primary: direct attribute set by espn_api (stats.get(0).get('points'))
        pts = as_float(safe_get(player, "total_points", default=0))
        if pts > 0:
            return pts
        # Secondary: dig into stats dict with correct integer key
        stats_dict = getattr(player, "stats", {}) or {}
        pts = as_float((stats_dict.get(0) or {}).get("points") or 0)
        if pts > 0:
            return pts
    except Exception:
        pass
    return 0.0


def _compute_fp_for_player(player) -> float:
    """
    Compute actual fantasy points scored this season for *player*.

    Source priority:
      1. In-memory cache hit — O(1), no recompute (only for values > 0)
      2. _CURRENT_SEASON_DB → _hitter/pitcher_pts_from_stats()
         Most accurate: sums raw H, HR, RBI, SB, K, IP … against scoring weights.
         Available once pybaseball has fetched live 2026 stats (current_season_cache.json).
      3. ESPN player.total_points
         The ESPN API sets this from stats[0]['points'] — the full-season actual.
         Keyed by INTEGER period ID (0 = season total), NOT the broken "002026" string.
      4. ESPN avg_points × weeks_elapsed
         Least precise, but available from day 1 of the season.

    NOTE: 0.0 is never stored in the persistent cache — a zero just means no
    data is available yet and should be retried next run.
    """
    name_key = normalize_name(getattr(player, "name", ""))

    # 1 — memory cache (only trust cached values > 0)
    cached = _FP_ACTUAL_CACHE.get(name_key, -1)
    if cached > 0:
        return cached

    pts = 0.0

    # 2 — compute from live 2026 stat line (most accurate when available)
    cs = get_current_season_metrics(player)
    if cs:
        try:
            pts = (_pitcher_pts_from_stats(cs) if is_pitcher(player)
                   else _hitter_pts_from_stats(cs))
        except Exception:
            pts = 0.0

    # 3 — ESPN total_points (correct integer-keyed API attribute)
    if pts <= 0:
        pts = _espn_actual_season_pts(player)

    # 4 — avg_points × estimated weeks as rough proxy
    if pts <= 0:
        avg = as_float(safe_get(player, "avg_points", default=0))
        if avg > 0:
            try:
                season_start = datetime(YEAR, 3, 27)
                weeks_elapsed = max(1, (datetime.now() - season_start).days // 7)
            except Exception:
                weeks_elapsed = 1
            pts = round(avg * weeks_elapsed, 1)

    # Only cache non-zero values — zero means "no data yet", retry next run
    if pts > 0:
        _FP_ACTUAL_CACHE[name_key] = round(pts, 1)
    return round(pts, 1)


def build_fp_actual_cache(players) -> None:
    """
    Batch-compute actual FP for all players and persist to fp_actual_cache.json.

    Called once per build_payload() run.  Players already in cache with a
    non-zero value are skipped.  Players with cached 0.0 (or absent) are always
    retried so stale "no data yet" entries don't persist forever.

    The cache file has a 30-minute TTL — older files are ignored and rebuilt.
    """
    global _FP_ACTUAL_CACHE

    # Load existing cache (only if fresh and non-trivially populated)
    _load_fp_actual_cache()

    # Always compute any player whose cached value is 0 or missing — 0 means
    # "had no data last run" and should be retried now that ESPN/pybaseball
    # may have updated.
    need_compute = [
        p for p in players
        if _FP_ACTUAL_CACHE.get(normalize_name(getattr(p, "name", "")), 0) <= 0
    ]

    if need_compute:
        print(f"  FP Actual Cache: computing for {len(need_compute)} players…")
        for p in need_compute:
            _compute_fp_for_player(p)

    nonzero = sum(1 for v in _FP_ACTUAL_CACHE.values() if v > 0)
    print(f"  FP Actual Cache: {nonzero}/{len(_FP_ACTUAL_CACHE)} players with actual FP data")
    _save_fp_actual_cache()


def get_actual_season_pts(player) -> float:
    """
    Return actual fantasy points scored so far this season for *player*.

    Delegates to _compute_fp_for_player() which uses the current-season stat
    cache (_CURRENT_SEASON_DB) to calculate FP from raw stat lines (H, HR,
    RBI, SB, K, IP, …) via the same scoring weights used everywhere else in
    the model.  Falls back to ESPN total_points → avg_points if no stat data
    is available yet.

    The result is memoised in _FP_ACTUAL_CACHE so repeated calls within the
    same session are O(1).
    """
    return _compute_fp_for_player(player)


_HITTER_SEASON_GP   = 162   # full MLB schedule
_SP_SEASON_GS       = 32    # typical SP: 30-34 starts
_RP_SEASON_G        = 65    # typical RP: 60-70 appearances
_PA_PER_GAME        = 3.85  # MLB avg PA per game per hitter
_AB_PER_GAME        = 3.28  # MLB avg AB per game per hitter (excludes walks/HBP/sacs)


def _projected_total_gp(player) -> float:
    """
    Return projected full-season games/starts for *player* from the projection
    cache, reference cache, or positional defaults.

    Hitters  → projected PA ÷ 3.85  (FanGraphs PA per game)
    SP       → projected GS
    RP       → projected G (appearances) via IP ÷ 1.05
    """
    proj = get_projection_metrics(player)
    ref  = get_reference_metrics(player)

    if is_pitcher(player):
        sp_role = is_starter_role(player)
        if sp_role:
            # SP: use projected GS from projection cache → ref cache → default
            gs = as_float((proj or {}).get("GS") or (ref or {}).get("GS") or 0)
            return gs if gs >= 5 else _SP_SEASON_GS
        else:
            # RP: projected appearances ≈ IP / 1.05
            ip = as_float((proj or {}).get("IP") or (ref or {}).get("IP") or 0)
            g  = round(ip / 1.05) if ip >= 10 else 0
            return g if g >= 20 else _RP_SEASON_G
    else:
        # Hitter: PA ÷ PA-per-game
        pa = as_float((proj or {}).get("PA") or (ref or {}).get("PA") or 0)
        g  = round(pa / _PA_PER_GAME) if pa >= 50 else 0
        return g if g >= 50 else _HITTER_SEASON_GP


def _espn_breakdown(player) -> dict:
    """
    Return the full-season stat breakdown dict from ESPN's stats[0].
    Keys are stat names from STATS_MAP (e.g. 'AB', 'G', 'GP', 'GS', 'H', etc.)
    Returns an empty dict if unavailable.
    """
    try:
        stats_dict = getattr(player, "stats", {}) or {}
        season_bucket = stats_dict.get(0) or {}
        return season_bucket.get("breakdown") or {}
    except Exception:
        return {}


def _games_played_so_far(player, current_week: int) -> float:
    """
    Return the number of games (with actual participation) a player has logged
    so far in 2026, sourced directly from ESPN's season stat breakdown.

    Hitters  — uses ESPN 'AB' (at-bats).  AB ÷ _AB_PER_GAME gives games where
               the player actually batted, excluding pinch-run / defensive-only
               appearances with zero at-bats.  Falls back to ESPN 'G' if AB=0.

    SP       — uses ESPN 'GS' (games started).

    RP       — uses ESPN 'GP' (games pitched / appearances).

    Priority
    --------
      Hitters:  ESPN AB  →  ESPN G  →  pybaseball AB  →  pybaseball PA  →  calendar
      SP:       ESPN GS  →  pybaseball GS  →  calendar
      RP:       ESPN GP  →  pybaseball G   →  calendar
    """
    bd = _espn_breakdown(player)

    if not is_pitcher(player):
        # --- Hitters: games with ≥1 AB ---
        ab = as_float(bd.get("AB") or 0)
        if ab >= 1:
            return max(1.0, round(ab / _AB_PER_GAME))
        g = as_float(bd.get("G") or 0)
        if g >= 1:
            return g
        # Pybaseball fallback
        cs = get_current_season_metrics(player)
        if cs:
            ab_cs = as_float(cs.get("AB") or 0)
            if ab_cs >= 1:
                return max(1.0, round(ab_cs / _AB_PER_GAME))
            pa_cs = as_float(cs.get("PA") or 0)
            if pa_cs >= 1:
                return max(1.0, round(pa_cs / _PA_PER_GAME))
    else:
        if is_starter_role(player):
            # SP: games started
            gs = as_float(bd.get("GS") or 0)
            if gs >= 1:
                return gs
            cs = get_current_season_metrics(player)
            if cs:
                gs_cs = as_float(cs.get("GS") or 0)
                if gs_cs >= 1:
                    return gs_cs
        else:
            # RP: games pitched (any appearance)
            gp = as_float(bd.get("GP") or 0)
            if gp >= 1:
                return gp
            cs = get_current_season_metrics(player)
            if cs:
                g_cs = as_float(cs.get("G") or 0)
                if g_cs >= 1:
                    return g_cs

    # Calendar fallback — estimate from current_week
    weeks = max(1, current_week - 1)
    if is_pitcher(player) and is_starter_role(player):
        return float(weeks)          # ~1 start per week
    elif is_pitcher(player):
        return float(weeks * 3)      # ~3 appearances per week for RP
    else:
        return float(weeks * 6)      # ~6 games per week for hitters


def get_season_pace_data(player, current_week: int, total_weeks: int = 26) -> dict:
    """
    Build a per-player season pace payload.

    Pace formula
    ─────────────
      pace_pts = (actual_pts / games_played) * projected_total_gp

      actual_pts       – FP scored to date (ESPN total_points or pybaseball stats)
      games_played     – games/starts logged so far (_games_played_so_far)
      projected_total  – full-season games/starts from projection/reference cache
                         or positional default (hitter=162, SP=32, RP=65)

    This is more stable than avg×weeks because it accounts for how many games
    a player has left: a hitter in 50 games projects differently from one in 155.
    """
    slot   = get_lineup_slot(player)
    status = get_player_status(player)
    on_il  = slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", "")

    actual_pts   = _compute_fp_for_player(player)
    avg_per_week = as_float(safe_get(player, "avg_points", default=0))

    # If actual_pts is still 0 reconstruct from avg × calendar weeks as proxy
    if actual_pts <= 0 and avg_per_week > 0:
        weeks_elapsed = max(1, current_week - 1)
        actual_pts = round(avg_per_week * weeks_elapsed, 1)

    # Games played and projected total — the core of the new pace formula
    gp_so_far   = _games_played_so_far(player, current_week)
    proj_total_gp = _projected_total_gp(player)

    # pace = (FP per game so far) × (projected total games)
    if actual_pts > 0 and gp_so_far > 0:
        fp_per_gp = actual_pts / gp_so_far
        pace_pts  = round(fp_per_gp * proj_total_gp, 1)
    elif avg_per_week > 0:
        # Fall back to avg × weeks if we have no game-level data at all
        pace_pts = round(avg_per_week * total_weeks, 1)
    else:
        pace_pts = 0.0

    fdb_proj  = round(get_projected_pts(player), 1)
    espn_proj = round(as_float(safe_get(player, "projected_total_points", default=0)), 1)
    pos       = ", ".join(get_player_slots(player)[:2])
    is_p      = is_pitcher(player)

    return {
        "player":         player.name,
        "pos":            pos,
        "is_pitcher":     is_p,
        "on_il":          on_il,
        "status":         status,
        "actual_pts":     round(actual_pts, 1),
        "pace_pts":       pace_pts,
        "fdb_proj":       fdb_proj,
        "espn_proj":      espn_proj,
        "avg_per_week":   round(avg_per_week, 2),
        "gp_so_far":      round(gp_so_far, 0),
        "proj_total_gp":  round(proj_total_gp, 0),
        "fp_per_gp":      round(actual_pts / gp_so_far, 2) if gp_so_far > 0 and actual_pts > 0 else 0.0,
        "vs_fdb":         round(pace_pts - fdb_proj, 1),
        "vs_espn":        round(pace_pts - espn_proj, 1),
        "headshot":       get_player_headshot_url(player),
        "headshot2":      get_player_headshot_url_mlb(player),
        "initials":       get_initials(player.name),
        "mlb_team":       get_player_team(player),
    }


def build_season_pace_payload(league, current_week: int, total_weeks: int = 26) -> dict:
    """
    Build the full season-pace payload for all rostered teams.

    Returns {
        current_week, total_weeks, weeks_remaining,
        my_team_rows:   [pace dict per player on my team],
        all_teams:      [{team_name, is_mine, total_actual, total_pace,
                          total_fdb, players:[...]}],
        generated_at:   ISO timestamp string,
    }
    """
    from datetime import datetime as _dt

    weeks_remaining = max(0, total_weeks - current_week + 1)
    my_team_name    = MY_TEAM_NAME.lower()
    my_rows         = []
    all_teams       = []

    for team in league.teams:
        is_mine = my_team_name in team.team_name.lower()
        rows    = []
        for p in team.roster:
            row = get_season_pace_data(p, current_week, total_weeks)
            rows.append(row)
        # Sort: active players by pace_pts desc, then IL
        rows.sort(key=lambda r: (r["on_il"], -r["pace_pts"]))
        team_actual = round(sum(r["actual_pts"] for r in rows if not r["on_il"]), 1)
        team_pace   = round(sum(r["pace_pts"]   for r in rows if not r["on_il"]), 1)
        team_fdb    = round(sum(r["fdb_proj"]   for r in rows if not r["on_il"]), 1)
        all_teams.append({
            "team_name":     team.team_name,
            "is_mine":       is_mine,
            "total_actual":  team_actual,
            "total_pace":    team_pace,
            "total_fdb":     team_fdb,
            "players":       rows,
        })
        if is_mine:
            my_rows = rows

    all_teams.sort(key=lambda t: -t["total_pace"])

    return {
        "current_week":    current_week,
        "total_weeks":     total_weeks,
        "weeks_remaining": weeks_remaining,
        "my_team_rows":    my_rows,
        "all_teams":       all_teams,
        "generated_at":    _dt.now().strftime("%Y-%m-%dT%H:%M"),
    }


# ═══════════════════════════════════════════════════════════════════
# P1 — FULL-WEEK DAY-BY-DAY SCORING CACHE
# ═══════════════════════════════════════════════════════════════════

_DAILY_SCORES_PATH = os.path.join(SCRIPT_DIR, "daily_matchup_cache.json")

def _load_daily_scores_cache() -> dict:
    """Load the persisted day-by-day scoring cache. {week_str: {player_name: {day_abbr: pts}}}"""
    if not os.path.exists(_DAILY_SCORES_PATH):
        return {}
    try:
        with open(_DAILY_SCORES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_daily_scores_cache(data: dict) -> None:
    try:
        with open(_DAILY_SCORES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
    except Exception as e:
        print(f"  Warning: daily scores cache save failed: {e}")

def get_week_scoring_by_day(league, my_team) -> dict:
    """
    Build the full-week day-by-day scoring breakdown for the current matchup.

    Strategy: each run we snapshot cumulative weekly totals from ESPN. We diff
    today's total against the sum of all previously cached days to get today's
    contribution. This accumulates over the week without needing per-day API calls.

    Returns:
      {
        "my_players":  [{name, pos, is_bench, days:{Mon:pts,...}, total:pts, weekly_proj:pts}, ...],
        "opp_players": [...],
        "days":        ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
        "today_day":   "Wed",
        "week":        N,
        "my_total":    float,
        "opp_total":   float,
      }
    or {} on failure.
    """
    try:
        matchup, me, opp = get_matchup(league, my_team)
        if not matchup:
            return {}

        week = league.current_week
        today = datetime.now()
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        today_idx = today.weekday()          # 0 = Mon
        today_day = day_names[today_idx]

        is_home   = (me.team_name == getattr(matchup.home_team, "team_name", ""))
        my_lineup  = getattr(matchup, "home_lineup"  if is_home else "away_lineup",  [])
        opp_lineup = getattr(matchup, "away_lineup"  if is_home else "home_lineup",  [])

        cache     = _load_daily_scores_cache()
        week_key  = str(week)
        week_cache = cache.get(week_key, {})

        def _build_rows(lineup, side_cache):
            rows = []
            for bp in lineup:
                slot      = getattr(bp, "slot_position", "") or ""
                pts_total = as_float(getattr(bp, "points", 0))
                proj      = as_float(getattr(bp, "projected_points", 0))
                # player name
                _pl = getattr(bp, "player", None)
                name = (getattr(_pl, "name", "") if _pl else "") or getattr(bp, "name", "") or ""
                if not name:
                    continue

                player_cache = side_cache.get(name, {})
                # today's pts = cumulative minus all previously cached days
                prev_total = sum(player_cache.get(d, 0.0) for d in day_names[:today_idx])
                today_pts  = max(0.0, round(pts_total - prev_total, 2))

                days = {}
                for i, d in enumerate(day_names):
                    if i < today_idx:
                        days[d] = round(player_cache.get(d, 0.0), 2)
                    elif i == today_idx:
                        days[d] = today_pts
                    else:
                        days[d] = None   # not yet played

                # Update today in the cache dict
                if name not in side_cache:
                    side_cache[name] = {}
                side_cache[name][today_day] = today_pts

                rows.append({
                    "name":        name,
                    "pos":         slot,
                    "is_bench":    slot in ("BE", "IL", "BN", "IR"),
                    "days":        days,
                    "total":       round(pts_total, 2),
                    "weekly_proj": round(proj, 2),
                })
            rows.sort(key=lambda r: (r["is_bench"], -r["total"]))
            return rows

        # We store my/opp separately under "my"/"opp" sub-keys
        my_cache  = week_cache.get("my",  {})
        opp_cache = week_cache.get("opp", {})
        my_rows   = _build_rows(my_lineup,  my_cache)
        opp_rows  = _build_rows(opp_lineup, opp_cache)

        # Persist
        cache[week_key] = {"my": my_cache, "opp": opp_cache}
        for k in [w for w in cache if int(w) < week - 3]:
            del cache[k]
        _save_daily_scores_cache(cache)

        my_total  = round(sum(r["total"] for r in my_rows  if not r["is_bench"]), 2)
        opp_total = round(sum(r["total"] for r in opp_rows if not r["is_bench"]), 2)

        return {
            "my_players":  my_rows,
            "opp_players": opp_rows,
            "days":        day_names,
            "today_day":   today_day,
            "week":        week,
            "my_total":    my_total,
            "opp_total":   opp_total,
        }
    except Exception as e:
        print(f"  Week scoring by day failed (non-fatal): {e}")
        return {}


# ═══════════════════════════════════════════════════════════════════
# P2 — OPTIMAL ROSTER BLUEPRINT
# ═══════════════════════════════════════════════════════════════════

def compute_optimal_roster_blueprint(league, my_team) -> dict:
    """
    Calculate the mathematically optimal 26-man roster construction
    based on this league's scoring system and the current FA pool.

    Determines how many of each archetype maximises expected weekly points:
      - Elite closers vs high-hold setup men
      - SP count vs RP count
      - Positional hitter priority (C/SS scarcity vs raw value)

    Returns:
      {
        "slots": {
          "C":  {"target": 1, "current": 1, "gap": 0},
          "SP": {"target": 4, "current": 3, "gap": 1},
          ...
        },
        "archetypes": {
          "elite_closer": {"target": 1, "current": 1, "gap": 0},
          "high_hold_rp": {"target": 2, "current": 1, "gap": 1},
          ...
        },
        "summary": "Roster is 2 moves from optimal: need 1 more SP, 1 more high-hold RP",
        "priority_adds": ["SP", "high_hold_rp"],
      }
    """
    try:
        # Count current roster composition
        my_roster = list(my_team.roster)
        current = {
            "C": 0, "1B": 0, "2B": 0, "3B": 0, "SS": 0, "OF": 0,
            "SP": 0, "RP": 0, "elite_closer": 0, "high_hold_rp": 0,
            "UTIL": 0, "BE": 0, "IL": 0,
        }
        # Count by eligible positions, not lineup slot.
        # This correctly handles bench players (slot="BE") who still fill real roster roles.
        # Cap each position at its SLOTS_PER_TEAM target to avoid multi-eligible over-counting.
        _pos_caps = {k: SLOTS_PER_TEAM.get(k, 1) for k in
                     ("C", "1B", "2B", "3B", "SS", "OF", "SP", "RP")}
        for p in my_roster:
            slot  = get_lineup_slot(p)
            slots = get_player_slots(p)
            if slot in ("IL", "IR"):
                current["IL"] += 1
                continue
            status = get_player_status(p)
            if status not in ("ACTIVE", "NORMAL", ""):
                current["IL"] += 1
                continue
            if slot in ("BE", "BENCH"):
                current["BE"] += 1
                # Still count toward eligible positions below (bench ≠ useless)
            elif slot == "UTIL":
                current["UTIL"] += 1

            # Count toward eligible positions (capped at slot target)
            for k in ("C", "1B", "2B", "3B", "SS", "OF"):
                if k in slots and current[k] < _pos_caps[k]:
                    current[k] += 1
                    break  # count toward most specific position only

            if is_starter_role(p):
                if current["SP"] < _pos_caps["SP"]:
                    current["SP"] += 1
            elif is_reliever_role(p):
                if current["RP"] < _pos_caps["RP"]:
                    current["RP"] += 1
                    ref = get_reference_metrics(p)
                    sv  = get_metric(ref, "SV") if ref else 0
                    hd  = get_metric(ref, "HD", "HLD") if ref else 0
                    if sv >= 20:
                        current["elite_closer"] += 1
                    elif hd >= 15 or sv >= 5:
                        current["high_hold_rp"] += 1

        # Target construction (evidence-based for this scoring system)
        # From memory doc: holds massively undervalued, K-rate the biggest drag,
        # 2-start SP multiplier is highest leverage
        targets = {
            "C":    1, "1B": 1, "2B": 1, "3B": 1, "SS": 1, "OF": 3,
            "SP":   SLOTS_PER_TEAM.get("SP", 4),
            "RP":   SLOTS_PER_TEAM.get("RP", 3),
            # Ideal bullpen mix: 1 elite closer + 2 high-hold setup men
            "elite_closer":  1,
            "high_hold_rp":  2,
        }

        slots_gap = {}
        for pos in ("C", "1B", "2B", "3B", "SS", "OF", "SP", "RP"):
            t = targets.get(pos, 1)
            c = current.get(pos, 0)
            slots_gap[pos] = {"target": t, "current": c, "gap": max(0, t - c)}

        arch_gap = {}
        for arch in ("elite_closer", "high_hold_rp"):
            t = targets[arch]
            c = current[arch]
            arch_gap[arch] = {"target": t, "current": c, "gap": max(0, t - c)}

        # Build priority adds list (biggest gaps first)
        all_gaps = [(k, v["gap"]) for k, v in {**slots_gap, **arch_gap}.items() if v["gap"] > 0]
        all_gaps.sort(key=lambda x: -x[1])
        priority_adds = [k for k, _ in all_gaps]

        if not priority_adds:
            summary = "✅ Roster construction is at or near optimal"
        else:
            parts = []
            for k, gap in all_gaps[:3]:
                label = {
                    "SP": "starting pitcher", "RP": "reliever",
                    "elite_closer": "elite closer", "high_hold_rp": "high-hold RP",
                    "C": "catcher", "SS": "shortstop", "OF": "outfielder",
                }.get(k, k)
                parts.append(f"{gap} more {label}" if gap > 1 else f"1 more {label}")
            summary = f"Roster needs: {', '.join(parts)}"

        return {
            "slots":         slots_gap,
            "archetypes":    arch_gap,
            "summary":       summary,
            "priority_adds": priority_adds,
        }
    except Exception as e:
        print(f"  Blueprint calculation failed (non-fatal): {e}")
        return {"slots": {}, "archetypes": {}, "summary": "", "priority_adds": []}


# ═══════════════════════════════════════════════════════════════════
# P3 — DAILY SP STREAMING RANKED LIST
# ═══════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# WEEKLY PITCHER STREAMING PLAN
# Builds the full-week pitching slate: per-start matchup scores, IP tracking,
# slot conflict detection, and combined ratio-risk flags.
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_weekly_game_details(week_start: str, week_end: str) -> dict:
    """
    Pull per-game context for every probable starter this week.

    Returns:
        {mlbam_id_str: [{"date": "YYYY-MM-DD", "opp_abbr": str,
                          "home_abbr": str, "is_home": bool}]}
    Falls back to {} on any error.
    """
    details: dict = {}
    try:
        url = (
            "https://statsapi.mlb.com/api/v1/schedule"
            f"?sportId=1&startDate={week_start}&endDate={week_end}"
            "&hydrate=probablePitcher,team&gameType=R"
        )
        raw = _mlb_get(url, timeout=10)
        for date_block in raw.get("dates", []):
            game_date = date_block.get("date", "")
            for game in date_block.get("games", []):
                teams_data = game.get("teams", {})
                home_abbr  = teams_data.get("home", {}).get("team", {}).get("abbreviation", "")
                away_abbr  = teams_data.get("away", {}).get("team", {}).get("abbreviation", "")
                for side, is_home in (("home", True), ("away", False)):
                    pp  = teams_data.get(side, {}).get("probablePitcher", {})
                    pid = str(pp.get("id", ""))
                    if not pid:
                        continue
                    opp_abbr = away_abbr if is_home else home_abbr
                    entry = {
                        "date":      game_date,
                        "opp_abbr":  opp_abbr,
                        "home_abbr": home_abbr,
                        "is_home":   is_home,
                    }
                    details.setdefault(pid, []).append(entry)
    except Exception as exc:
        print(f"  Weekly game details fetch failed (non-fatal): {exc}")
    return details


def _get_team_batting_profiles() -> dict:
    """
    Aggregate opponent batting quality from REFERENCE_DB hitters, grouped by MLB team.

    Returns:
        {team_abbr: {"k_pct": float, "woba": float, "ops": float, "n": int}}
    Falls back gracefully if REFERENCE_DB is not loaded.
    """
    profiles: dict = {}
    hitters_db = REFERENCE_DB.get("hitters", {})
    if not hitters_db:
        return profiles

    accum: dict = {}
    for _name, row in hitters_db.items():
        team = str(row.get("Team", row.get("team", ""))).upper()
        if not team or len(team) > 4:
            continue
        k_pct = get_metric(row, "K%", "Kp")
        woba  = get_metric(row, "wOBA")
        ops   = get_metric(row, "OPS")
        pa    = get_metric(row, "PA", default=1.0)
        if pa < 50:  # skip tiny samples
            continue
        if team not in accum:
            accum[team] = {"k_pct_sum": 0.0, "woba_sum": 0.0, "ops_sum": 0.0,
                           "pa_sum": 0.0, "n": 0}
        w = pa  # weight by PA
        accum[team]["k_pct_sum"] += k_pct * w
        accum[team]["woba_sum"]  += woba  * w
        accum[team]["ops_sum"]   += ops   * w
        accum[team]["pa_sum"]    += w
        accum[team]["n"]         += 1

    for team, a in accum.items():
        pa_sum = max(a["pa_sum"], 1)
        profiles[team] = {
            "k_pct": round(a["k_pct_sum"] / pa_sum, 4),
            "woba":  round(a["woba_sum"]  / pa_sum, 4),
            "ops":   round(a["ops_sum"]   / pa_sum, 4),
            "n":     a["n"],
        }
    return profiles


# Lazy-loaded team batting profiles (populated on first call)
_TEAM_BATTING_PROFILES: dict = {}


def score_start_matchup(opp_abbr: str, home_abbr: str, is_home: bool) -> dict:
    """
    Score a single start's matchup quality on a 0-100 scale.

    Components:
        Opponent K%   (higher = easier for pitcher)  -> up to 30 pts
        Opponent wOBA (lower  = easier for pitcher)  -> up to 35 pts
        Park factor   (lower  = pitcher-friendly)    -> up to 20 pts
        Home advantage                                -> 5 pts
    Grade: A (>=80), B (65-79), C (50-64), D (35-49), F (<35)

    Returns:
        {"score": int, "grade": str, "opp_abbr": str, "park_factor": float,
         "is_home": bool, "opp_woba": float, "opp_k_pct": float, "note": str}
    """
    global _TEAM_BATTING_PROFILES
    if not _TEAM_BATTING_PROFILES:
        _TEAM_BATTING_PROFILES = _get_team_batting_profiles()

    park_factor  = get_park_factor(home_abbr)
    opp_profile  = _TEAM_BATTING_PROFILES.get(opp_abbr.upper(), {})
    opp_k_pct    = opp_profile.get("k_pct", 0.220)   # fallback: league-avg ~22%
    opp_woba     = opp_profile.get("woba",  0.318)   # fallback: league-avg ~.318

    # K% component: 30 pts at 28%+ K rate (elite), 0 pts at 15% or below
    k_pts   = max(0.0, min(30.0, (opp_k_pct - 0.15) / (0.28 - 0.15) * 30.0))
    # wOBA component: 35 pts at .280 wOBA or below, 0 pts at .360 or above
    w_pts   = max(0.0, min(35.0, (.360 - opp_woba)  / (.360 - .280) * 35.0))
    # Park factor component: 20 pts at pf=0.85, 0 pts at pf=1.15
    pf_pts  = max(0.0, min(20.0, (1.15 - park_factor) / (1.15 - 0.85) * 20.0))
    # Home advantage
    home_pts = 5.0 if is_home else 0.0

    raw_score = k_pts + w_pts + pf_pts + home_pts
    score     = int(round(min(100.0, raw_score)))

    if score >= 80:
        grade, color = "A", "var(--accent)"
    elif score >= 65:
        grade, color = "B", "#4caf50"
    elif score >= 50:
        grade, color = "C", "var(--amber)"
    elif score >= 35:
        grade, color = "D", "var(--red)"
    else:
        grade, color = "F", "var(--red)"

    notes = []
    if opp_woba < 0.295:
        notes.append(f"weak lineup ({opp_woba:.3f} wOBA)")
    elif opp_woba > 0.340:
        notes.append(f"dangerous lineup ({opp_woba:.3f} wOBA)")
    if opp_k_pct > 0.255:
        notes.append(f"high-K% opp ({opp_k_pct*100:.0f}% K)")
    if park_factor >= 1.08:
        notes.append(f"hitter-friendly park (+{int((park_factor-1)*100)}%)")
    elif park_factor <= 0.94:
        notes.append(f"pitcher-friendly park ({int((park_factor-1)*100)}%)")
    if is_home:
        notes.append("home start")

    return {
        "score":       score,
        "grade":       grade,
        "color":       color,
        "opp_abbr":    opp_abbr,
        "home_abbr":   home_abbr,
        "park_factor": round(park_factor, 3),
        "is_home":     is_home,
        "opp_woba":    round(opp_woba, 3),
        "opp_k_pct":   round(opp_k_pct, 4),
        "note":        "; ".join(notes) if notes else "",
    }


def build_weekly_streaming_plan(league, my_team, week_start: str, week_end: str) -> dict:
    """
    Build the full weekly pitching plan for my_team.

    Returns a dict consumed by html._streaming_plan_section():
    {
      "week_label":  "Apr 27 - May 3",
      "pitchers":    [ {per-pitcher details} ],
      "totals":      { proj_ip, proj_k, ip_limit, ip_flag, ratio_risk, ratio_risk_names },
      "conflicts":   [ {"type": str, "message": str, "severity": "warn"|"danger"} ],
    }
    """
    try:
        # Per-start game context for the whole week
        game_details = _fetch_weekly_game_details(week_start, week_end)

        # Format week label
        try:
            from datetime import datetime as _dt2
            ws_d = _dt2.strptime(week_start, "%Y-%m-%d")
            we_d = _dt2.strptime(week_end,   "%Y-%m-%d")
            week_label = f"{ws_d.strftime('%b %-d')} – {we_d.strftime('%b %-d')}"
        except Exception:
            week_label = f"{week_start} – {week_end}"

        pitchers_out = []
        total_proj_ip = 0.0
        total_proj_k  = 0.0
        ratio_risk_names = []

        for player in sorted(my_team.roster, key=lambda p: -get_projected_pts(p)):
            if not is_pitcher(player):
                continue

            mlbam = get_mlbam_id(player)
            ref   = get_reference_metrics(player)
            sc    = get_statcast_metrics(player)
            slots = get_player_slots(player)
            pos   = get_lineup_slot(player)

            # --- Per-pitcher metrics ---
            siera = get_metric(ref, "SIERA") if ref else 0.0
            xfip  = get_metric(ref, "xFIP")  if ref else 0.0
            era   = get_metric(ref, "ERA")    if ref else 0.0
            whip  = get_metric(ref, "WHIP")   if ref else 0.0
            ip_ref = get_metric(ref, "IP")    if ref else 0.0
            k9    = get_metric(ref, "K/9", "SO9") if ref else 0.0
            era_est = siera or xfip or era or 0.0
            xfip_val = xfip or siera or era or 0.0

            # Projected pts (per week, not season)
            weekly_proj = get_weekly_projected_pts(player)

            # --- Starts this week with per-start matchup scores ---
            pitcher_starts = game_details.get(str(mlbam), [])
            starts_out = []
            for start in pitcher_starts:
                mq = score_start_matchup(
                    opp_abbr  = start["opp_abbr"],
                    home_abbr = start["home_abbr"],
                    is_home   = start["is_home"],
                )
                # Per-start projected IP (reference IP / 30 starts as per-start rate)
                per_start_ip = (ip_ref / 30.0) if ip_ref > 0 else 5.5
                per_start_k  = per_start_ip * (k9 / 9.0) if k9 > 0 else per_start_ip * 0.9
                starts_out.append({
                    "date":          start["date"],
                    "opp_abbr":      start["opp_abbr"],
                    "home_abbr":     start["home_abbr"],
                    "is_home":       start["is_home"],
                    "matchup_score": mq["score"],
                    "matchup_grade": mq["grade"],
                    "matchup_color": mq["color"],
                    "matchup_note":  mq["note"],
                    "park_factor":   mq["park_factor"],
                    "opp_woba":      mq["opp_woba"],
                    "proj_ip":       round(per_start_ip, 1),
                    "proj_k":        round(per_start_k, 1),
                })

            n_starts = len(starts_out)

            # Combined matchup flag across all starts
            if n_starts == 0:
                combined_flag  = "no-starts"
                combined_label = "No starts"
            elif n_starts == 1:
                g = starts_out[0]["matchup_grade"]
                combined_flag  = "single"
                combined_label = f"1 start · {g}"
            else:
                grades = [s["matchup_grade"] for s in starts_out]
                best   = min(grades, key=lambda g: "ABCDF".index(g))
                worst  = max(grades, key=lambda g: "ABCDF".index(g))
                if worst in ("A", "B"):
                    combined_flag = "both-strong"
                elif best in ("D", "F"):
                    combined_flag = "both-risky"
                else:
                    combined_flag = "mixed"
                combined_label = f"2 starts · {'/'.join(grades)}"

            # IP and K projections
            pitcher_proj_ip = sum(s["proj_ip"] for s in starts_out)
            pitcher_proj_k  = sum(s["proj_k"]  for s in starts_out)
            total_proj_ip  += pitcher_proj_ip
            total_proj_k   += pitcher_proj_k

            # Ratio risk: xFIP > 4.80 or WHIP > 1.45
            has_ratio_risk = (0 < xfip_val > 4.80) or (0 < whip > 1.45)
            if has_ratio_risk and n_starts > 0:
                ratio_risk_names.append(player.name)

            pitchers_out.append({
                "name":           player.name,
                "team":           get_player_team(player),
                "slots":          slots,
                "lineup_pos":     pos,
                "is_on_bench":    pos in ("BE", "BN", "IL", "IR"),
                "n_starts":       n_starts,
                "starts":         starts_out,
                "combined_flag":  combined_flag,
                "combined_label": combined_label,
                "weekly_proj":    round(weekly_proj, 1),
                "proj_ip":        round(pitcher_proj_ip, 1),
                "proj_k":         round(pitcher_proj_k, 1),
                "era_est":        round(era_est, 2),
                "xfip":           round(xfip_val, 2),
                "whip":           round(whip, 2),
                "siera":          round(siera, 2),
                "has_ratio_risk": has_ratio_risk,
                "headshot":       get_player_headshot_url(player),
                "headshot2":      get_player_headshot_url_mlb(player),
                "initials":       get_initials(player.name),
            })

        # Sort: 2-start first, then by weekly_proj desc, then 1-start, then 0-start
        pitchers_out.sort(key=lambda p: (-p["n_starts"], -p["weekly_proj"]))

        # Conflict detection
        conflicts = []
        if total_proj_ip > WEEKLY_IP_LIMIT * 0.90:
            severity = "danger" if total_proj_ip > WEEKLY_IP_LIMIT else "warn"
            conflicts.append({
                "type":     "ip_limit",
                "severity": severity,
                "message":  (
                    f"Projected {total_proj_ip:.0f} IP this week "
                    f"({'exceeds' if total_proj_ip > WEEKLY_IP_LIMIT else 'approaching'} "
                    f"{WEEKLY_IP_LIMIT}-IP cap). "
                    f"Adding another streamer risks hitting the limit."
                ),
            })
        if ratio_risk_names:
            conflicts.append({
                "type":     "ratio_risk",
                "severity": "warn",
                "message":  (
                    f"{', '.join(ratio_risk_names[:3])} "
                    f"{'has' if len(ratio_risk_names) == 1 else 'have'} "
                    f"elevated xFIP/WHIP — streaming them risks ERA/WHIP."
                ),
            })

        # Count open streaming slots (bench pitchers or empty slots)
        bench_pitchers  = sum(1 for p in pitchers_out if p["is_on_bench"] and p["n_starts"] > 0)
        streaming_slots = max(0, bench_pitchers)

        return {
            "week_label":      week_label,
            "week_start":      week_start,
            "week_end":        week_end,
            "pitchers":        pitchers_out,
            "totals": {
                "proj_ip":           round(total_proj_ip, 1),
                "proj_k":            round(total_proj_k, 1),
                "ip_limit":          WEEKLY_IP_LIMIT,
                "ip_flag":           total_proj_ip > WEEKLY_IP_LIMIT * 0.90,
                "ratio_risk":        bool(ratio_risk_names),
                "ratio_risk_names":  ratio_risk_names,
            },
            "conflicts":       conflicts,
            "streaming_slots": streaming_slots,
        }

    except Exception as exc:
        import traceback as _tb
        print(f"  Weekly streaming plan failed (non-fatal): {exc}")
        _tb.print_exc()
        return {
            "week_label": "", "week_start": week_start, "week_end": week_end,
            "pitchers": [], "totals": {"proj_ip": 0, "proj_k": 0, "ip_limit": 50,
                                        "ip_flag": False, "ratio_risk": False,
                                        "ratio_risk_names": []},
            "conflicts": [], "streaming_slots": 0,
        }



def build_streaming_sp_list(league, my_team, today_games: list) -> list:
    """
    Rank all available (unrostered) starting pitchers for streaming consideration.

    Scoring formula per SP:
      matchup_grade (1-5, where 5 = easiest)   → 0-40 pts
      park_factor_bonus                          → 0-15 pts
      two_start_bonus (2 starts this week)       → +20 pts
      floor_bonus (low SIERA / high K-BB%)       → 0-15 pts
      ownership_penalty (highly owned = less value) → -5 to 0

    Returns list of dicts, sorted by streaming_score desc, max 15.
    """
    try:
        rostered = {p.name for t in league.teams for p in t.roster}

        # Get today's game map: {team_abbr: {pitcher_name, park_factor, ...}}
        today_map = {}
        for g in today_games:
            pf = _PARK_FACTORS.get(g.get("home_abbr", ""), 1.0)
            today_map[g.get("away_abbr", "")] = {
                "opp_abbr":     g.get("home_abbr", ""),
                "pitcher_name": g.get("home_pitcher_name", "TBD"),
                "park_factor":  pf,
                "game_time":    g.get("time_str", ""),
            }
            today_map[g.get("home_abbr", "")] = {
                "opp_abbr":     g.get("away_abbr", ""),
                "pitcher_name": g.get("away_pitcher_name", "TBD"),
                "park_factor":  pf,
                "game_time":    g.get("time_str", ""),
            }

        try:
            fa_pool = league.free_agents(size=300)
        except Exception:
            fa_pool = []

        results = []
        for player in fa_pool:
            if player.name in rostered:
                continue
            if not is_pitcher(player):
                continue
            # Require at least some starter eligibility
            if not is_starter_role(player):
                continue

            team_abbr = get_player_team(player)
            game_info = today_map.get(team_abbr, {})
            if not game_info:
                # No game today — still useful for weekly 2-start, but rank lower
                game_today = False
                pitcher_name = ""
                park_factor  = 1.0
                game_time    = ""
            else:
                game_today   = True
                pitcher_name = game_info.get("pitcher_name", "TBD")
                park_factor  = game_info.get("park_factor", 1.0)
                game_time    = game_info.get("game_time", "")

            # Grade the opposing pitcher (for hitter matchup — same logic inverted)
            if game_today and pitcher_name and pitcher_name != "TBD":
                matchup = grade_pitcher_matchup(pitcher_name, park_factor)
                opp_grade = matchup.get("grade", 3)      # 5 = favourable for hitter = bad for streaming SP
                # We want the SP to face a WEAK lineup, not the other way round
                # Grade 1 SP = hard to hit = great to stream; Grade 5 = easy to hit = bad to stream
                # But we're scoring the SP to stream, not the hitter to start
                # A SP with great metrics (grade 1) is good to stream
                sp_metrics = get_reference_metrics(player)
                sp_grade_info = {"grade": 3, "era_est": 0.0, "swstr": 0.0}
                if sp_metrics:
                    siera = get_metric(sp_metrics, "SIERA")
                    xfip  = get_metric(sp_metrics, "xFIP")
                    fip   = get_metric(sp_metrics, "FIP")
                    era   = get_metric(sp_metrics, "ERA")
                    swstr = get_metric(sp_metrics, "SwStp")
                    era_est = siera or xfip or fip or era or 0
                    sp_grade_info = {"era_est": era_est, "swstr": swstr}
                    if 0 < era_est <= 3.30 or swstr >= 0.13:
                        sp_grade_info["grade"] = 5   # elite — stream with confidence
                    elif era_est <= 3.80 or swstr >= 0.10:
                        sp_grade_info["grade"] = 4
                    elif era_est <= 4.30:
                        sp_grade_info["grade"] = 3
                    elif era_est <= 5.00:
                        sp_grade_info["grade"] = 2
                    else:
                        sp_grade_info["grade"] = 1   # risky — avoid
            else:
                sp_grade_info = {"grade": 2, "era_est": 0.0, "swstr": 0.0}

            # Two-start bonus
            two_start = get_two_start_multiplier(player) >= 1.75

            # Ownership / add-frequency penalty (highly added = everyone knows)
            ownership = as_float(safe_get(player, "percent_owned", default=0))

            # Composite streaming score
            score  = sp_grade_info.get("grade", 2) * 8.0      # 0-40 pts
            score += (park_factor - 1.0) * -15.0               # pitcher-friendly park bonus
            score += 20.0 if two_start else (10.0 if game_today else 0.0)
            era_est = sp_grade_info.get("era_est", 0)
            swstr   = sp_grade_info.get("swstr", 0)
            if 0 < era_est < 3.50:
                score += 15.0
            elif 0 < era_est < 4.00:
                score += 8.0
            if swstr >= 0.12:
                score += 10.0
            elif swstr >= 0.10:
                score += 5.0
            score -= min(5.0, ownership * 0.05)

            results.append({
                "player":        player.name,
                "pos":           "SP",
                "team":          team_abbr,
                "game_today":    game_today,
                "game_time":     game_time,
                "two_start":     two_start,
                "sp_grade":      sp_grade_info.get("grade", 2),
                "era_est":       round(era_est, 2),
                "swstr":         round(swstr, 4),
                "park_factor":   round(park_factor, 3),
                "streaming_score": round(score, 1),
                "headshot":      get_player_headshot_url(player),
                "headshot2":     get_player_headshot_url_mlb(player),
                "initials":      get_initials(player.name),
                "proj_pts":      round(get_projected_pts(player), 1),
                "mlbam_id":      get_mlbam_id(player),
                "espn_id":       get_espn_id(player),
                "is_pitcher":    "true",
            })

        results.sort(key=lambda x: -x["streaming_score"])
        return results[:15]

    except Exception as e:
        print(f"  Streaming SP list failed (non-fatal): {e}")
        return []


def build_payload(league):
    # Fetch this week's probable-starter counts first — they feed the two-start
    # multiplier used in every subsequent score calculation.
    print("Fetching weekly probable starters...")
    try:
        ws, we = _current_week_range()
        fetch_weekly_probable_starts(ws, we)
    except Exception as exc:
        print(f"  Weekly starters fetch failed (non-fatal): {exc}")

    my_team = get_my_team(league)
    if not my_team:
        raise RuntimeError(f"Cannot find '{MY_TEAM_NAME}' in league.")

    try:
        _, _, opp_team = get_matchup(league, my_team)
    except Exception as exc:
        print(f"  Matchup fetch failed (non-fatal): {exc}")
        opp_team = None

    # Fetch at size=50 — covers both the activity feed (16 shown) and waiver
    # add-frequency counting (50 needed) in a single ESPN API call.
    try:
        adds, drops, moves = get_recent_activity(league, size=50)
    except Exception as exc:
        print(f"  Recent activity fetch failed (non-fatal): {exc}")
        adds, drops, moves = {}, {}, []

    # Roster is already correct at this point.
    #
    # How ESPN roster data flows into this script:
    #   1. League() constructor calls _fetch_league() → _fetch_teams()
    #      which reads data['teams'][n]['roster']['entries'] and calls
    #      team._fetch_roster() for every team.  Roster MEMBERSHIP is
    #      set correctly here — who is on each team — based on ESPN's
    #      live ownership data.
    #
    #   2. _reload_rosters_today() (called inside connect()) re-fetches the
    #      same mRoster view with today's scoringPeriodId so that each
    #      player's lineupSlot reflects today's active/bench assignment
    #      rather than the week-start default.
    #
    # By the time build_payload() runs, both roster membership and lineup
    # slots are authoritative.  No further patching is needed or safe.
    #
    # Historical note: _reconcile_roster() and _sync_my_team_roster() were
    # removed because they modified an already-correct roster using unreliable
    # heuristics (activity-log inference and a misused filterTeamIds filter
    # that actually filters by MLB pro team, not fantasy team).  Those
    # functions remain in the file for reference but are NOT called.

    try:
        wp = win_probability(league, my_team)
    except Exception as exc:
        print(f"  Win probability failed (non-fatal): {exc}")
        wp = None

    my_sum  = team_summary(my_team)
    opp_sum = team_summary(opp_team) if opp_team else None

    try:
        # Pass pre-fetched adds to avoid a redundant get_recent_activity call
        waiver_recs = get_waiver_recommendations(league, my_team, size=200, recent_adds=adds, recent_drops=drops)
    except Exception as exc:
        print(f"  Waiver recommendations failed (non-fatal): {exc}")
        waiver_recs = []

    all_rostered = []
    for team in league.teams:
        for p in team.roster:
            all_rostered.append((base_score(p), p, team.team_name))
    all_rostered.sort(key=lambda x: x[0], reverse=True)

    # ── FP Actual Cache — batch-compute & persist before any _player_row calls ──
    # Collects all rostered players + waiver recommendation targets so every
    # player card, waiver card, and season-pace row gets an O(1) cache hit.
    print("Building actual FP cache (stat-based)...")
    try:
        _all_players_for_fp = [p for _, p, _ in all_rostered]
        _all_players_for_fp += [r["player"] for r in waiver_recs if isinstance(r.get("player"), object)]
        build_fp_actual_cache(_all_players_for_fp)
    except Exception as _fp_exc:
        print(f"  FP Actual Cache build failed (non-fatal): {_fp_exc}")

    ref = REFERENCE_DB
    ref_text = (
        f"Loaded {ref['season']} Baseball Reference data ({ref['source']})"
        if ref.get("loaded")
        else f"Reference data unavailable ({ref.get('source', 'none')})"
    )

    standings = [
        {
            "rank":   t.standing,
            "team":   t.team_name + (" ◄ YOU" if MY_TEAM_NAME.lower() in t.team_name.lower() else ""),
            "record": f"{getattr(t, 'wins', '?')}W – {getattr(t, 'losses', '?')}L",
            "_row_class": "highlight" if MY_TEAM_NAME.lower() in t.team_name.lower() else "",
        }
        for t in sorted(league.teams, key=lambda t: t.standing)
    ]

    matchup_data = None
    if wp:
        m, me, opp = get_matchup(league, my_team)
        if m:
            hs  = as_float(safe_get(m, "home_score", default=0))
            as_ = as_float(safe_get(m, "away_score", default=0))
            if me.team_name == m.home_team.team_name:
                my_s, opp_s = hs, as_
            else:
                my_s, opp_s = as_, hs
            margin = abs(my_s - opp_s)
            matchup_data = {
                "week":       league.current_week,
                "home":       m.home_team.team_name,
                "away":       m.away_team.team_name,
                "home_score": hs,
                "away_score": as_,
                "my_score":   my_s,
                "opp_score":  opp_s,
                "status": (
                    f"Leading by {margin:.1f} pts" if my_s > opp_s else
                    f"Trailing by {margin:.1f} pts" if my_s < opp_s else
                    "Tied"
                ),
                "status_class": (
                    "good" if my_s > opp_s else "bad" if my_s < opp_s else "warn"
                ),
                "my_scoring":  [],
                "opp_scoring": [],
            }
            # Player-level weekly scoring breakdown
            try:
                my_sc, opp_sc = get_matchup_scoring_breakdown(league, my_team)
                matchup_data["my_scoring"]  = my_sc
                matchup_data["opp_scoring"] = opp_sc
            except Exception:
                pass  # graceful degradation — scoring breakdown optional

    comparison = []
    if opp_sum:
        for label, my_val, opp_val in [
            ("Active base",   my_sum["active_base"],  opp_sum["active_base"]),
            ("Active fit",    my_sum["active_fit"],   opp_sum["active_fit"]),
            ("Best lineup",   my_sum["lineup_pts"],   opp_sum["lineup_pts"]),
            ("Hitter base",   my_sum["hitter_base"],  opp_sum["hitter_base"]),
            ("Pitcher base",  my_sum["pitcher_base"], opp_sum["pitcher_base"]),
            ("Injuries",      my_sum["injury_count"], opp_sum["injury_count"]),
        ]:
            edge = my_val - opp_val
            comparison.append({
                "metric": label,
                "mine":   fmt(my_val),
                "opp":    fmt(opp_val),
                "edge": {
                    "text":  fmt(edge),
                    "class": "good" if edge > 0 else ("bad" if edge < 0 else "warn"),
                },
            })
        if comparison:
            last = comparison[-1]
            last["edge"]["class"] = "bad" if float(last["edge"]["text"]) > 0 else (
                "good" if float(last["edge"]["text"]) < 0 else "warn"
            )

    injuries = [
        f"{p.name} ({get_player_team(p)}) — {get_player_status(p)}"
        for p in my_team.roster
        if get_player_status(p) not in ("ACTIVE", "NORMAL", "")
    ]

    top_rostered = []
    for rank, (bs, p, tname) in enumerate(all_rostered[:10], 1):
        top_rostered.append({
            "rank":       rank,
            "player":     p.name,
            "pos":        ", ".join(get_player_slots(p)[:2]),
            "mlb":        get_player_team(p),
            "proj_pts":   fmt(get_projected_pts(p), 1),
            "var":        fmt(max(0.0, get_projected_pts(p) - get_replacement_level(p)), 1),
            "base":       fmt(bs),
            "team":       tname,
            "headshot":   get_player_headshot_url(p),
            "headshot2":  get_player_headshot_url_mlb(p),
            "initials":   get_initials(p.name),
            "avatar_seed": avatar_seed(p.name),
        })

    global _TODAY_STARTER_IDS

    my_roster_rows  = sorted(
        [_player_row(p, my_team)  for p in my_team.roster],
        key=lambda r: (r["pos"] in ("BE", "BENCH", "IL", "IR"), r["pos"], -float(r["base"]))
    )
    opp_roster_rows = (
        sorted(
            [_player_row(p, opp_team) for p in opp_team.roster],
            key=lambda r: (r["pos"] in ("BE", "BENCH", "IL", "IR"), r["pos"], -float(r["base"]))
        ) if opp_team else []
    )

    # ── Today's MLB schedule (annotated with roster players) ─────────────
    # Also populates _TODAY_STARTER_IDS so _player_row() starts_today flag is correct.
    print("Fetching today's MLB schedule...")
    try:
        today_games = fetch_todays_mlb_schedule()
        _TODAY_STARTER_IDS = set()
        for _g in today_games:
            if _g.get("away_pitcher_id"):
                _TODAY_STARTER_IDS.add(str(_g["away_pitcher_id"]))
            if _g.get("home_pitcher_id"):
                _TODAY_STARTER_IDS.add(str(_g["home_pitcher_id"]))
        _TODAY_STARTER_IDS.discard("")
        print(f"  Found {len(_TODAY_STARTER_IDS)} probable starters today")
        today_games = annotate_games_with_players(today_games, my_roster_rows, opp_roster_rows)
    except Exception as exc:
        print(f"  MLB schedule fetch failed (non-fatal): {exc}")
        today_games = []

    # ── Phase 4: Hitter matchup intelligence ──────────────────────────────
    print("Grading today's hitter matchups...")
    try:
        hitter_matchups = build_hitter_matchups_today(my_roster_rows, today_games)
        favorable = sum(1 for m in hitter_matchups if m["grade"] >= 4)
        tough     = sum(1 for m in hitter_matchups if m["grade"] <= 2)
        print(f"  Matchup grades: {len(hitter_matchups)} hitters playing — "
              f"{favorable} favorable, {tough} tough")
    except Exception as exc:
        print(f"  Hitter matchups failed (non-fatal): {exc}")
        hitter_matchups = []

    # ── P1: Full-week day-by-day scoring ──────────────────────────────────
    print("Building full-week day-by-day scoring...")
    try:
        week_scoring = get_week_scoring_by_day(league, my_team)
    except Exception as exc:
        print(f"  Week scoring by day failed (non-fatal): {exc}")
        week_scoring = {}

    # ── P2: Optimal roster blueprint ──────────────────────────────────────
    print("Computing optimal roster blueprint...")
    try:
        roster_blueprint = compute_optimal_roster_blueprint(league, my_team)
    except Exception as exc:
        print(f"  Roster blueprint failed (non-fatal): {exc}")
        roster_blueprint = {"slots": {}, "archetypes": {}, "summary": "", "priority_adds": []}

    # ── P3: Daily SP streaming list ────────────────────────────────────────
    print("Building daily SP streaming list...")
    try:
        streaming_sps = build_streaming_sp_list(league, my_team, today_games)
        print(f"  SP streaming: {len(streaming_sps)} candidates ranked")
    except Exception as exc:
        print(f"  SP streaming list failed (non-fatal): {exc}")
        streaming_sps = []

    print("Building weekly streaming plan...")
    try:
        stream_plan = build_weekly_streaming_plan(league, my_team, ws, we)
        print(f"  Streaming plan: {len(stream_plan['pitchers'])} pitchers, "
              f"{stream_plan['totals']['proj_ip']:.0f} proj IP")
    except Exception as exc:
        print(f"  Weekly streaming plan failed (non-fatal): {exc}")
        stream_plan = {
            "week_label": "", "week_start": ws, "week_end": we,
            "pitchers": [], "totals": {"proj_ip": 0, "proj_k": 0, "ip_limit": 50,
                                        "ip_flag": False, "ratio_risk": False,
                                        "ratio_risk_names": []},
            "conflicts": [], "streaming_slots": 0,
        }

    # ── All-team rosters (for the Teams tab) ─────────────────────────────────
    # Pre-warm the age cache for all league players in one batch request
    # so the _player_row loop doesn't fire ~350 serial HTTP calls.
    print("Building all-team rosters...")
    _prefetch_all_ages(league)
    all_team_rosters = {}
    for team in league.teams:
        rows = sorted(
            [_player_row(p, team) for p in team.roster],
            key=lambda r: (r["pos"] in ("BE", "BENCH", "IL", "IR"), r["pos"], -float(r["base"]))
        )
        all_team_rosters[team.team_name] = {
            "rows":    rows,
            "summary": team_summary(team),
            "is_mine": MY_TEAM_NAME.lower() in team.team_name.lower(),
        }
    print(f"  All-team rosters built: {len(all_team_rosters)} teams")

    # ── Power rankings ────────────────────────────────────────────────────────
    print("Computing power rankings...")
    try:
        power_ranks = compute_power_rankings(league)
        for tname, tdata in all_team_rosters.items():
            tdata["power_rank"] = power_ranks.get(tname, "?")
        ranked_display = sorted(power_ranks.items(), key=lambda x: x[1])
        for name, rank in ranked_display:
            print(f"  #{rank:2d}  {name}")
    except Exception as exc:
        print(f"  Power rankings failed: {exc}")
        for tdata in all_team_rosters.values():
            tdata["power_rank"] = "?"

    # ── Season Intelligence ───────────────────────────────────────────────────
    print("Building season intelligence...")
    try:
        season_intel = {
            "my_il":      _get_season_intel_my_il(my_team),
            "il_watch":   _get_season_intel_il_stash(league, my_team),
            "fa_targets": _get_season_intel_fa_targets(league, my_team),
        }
        print(f"  Season intel: {len(season_intel['my_il'])} IL players, "
              f"{len(season_intel['il_watch'])} stash targets, "
              f"{len(season_intel['fa_targets'])} FA targets")
    except Exception as e:
        print(f"  Season intelligence: failed ({e})")
        season_intel = {"my_il": [], "il_watch": [], "fa_targets": []}

    waiver_rows = []
    for r in waiver_recs:
        p = r["player"]
        _age  = _fetch_player_age(p)
        _at   = age_tier(_age)
        waiver_rows.append({
            "player":       p.name,
            "pos":          ", ".join(get_player_slots(p)[:2]),
            "team":         get_player_team(p),
            "proj_pts":     fmt(r["proj_pts"], 1),
            "repl_pts":     fmt(r["repl_pts"], 1),
            "var":          fmt(r["var"], 1),
            "fit":          fmt(r["fit"]),
            "base":         fmt(r["base"]),
            "actual_pts":   fmt(get_actual_season_pts(p), 1),
            "avg_pts":      fmt(as_float(safe_get(p, "avg_points", default=0)), 1),
            "drop":         r["drop"],
            "reason":       r["reason"],
            "reason_items": json.dumps(r.get("reason_items", []), separators=(",", ":")),
            "adv":          _build_adv_json(p),
            "age":          _age,
            "age_tier":     _at,
            "headshot":     get_player_headshot_url(p),
            "headshot2":    get_player_headshot_url_mlb(p),
            "initials":     get_initials(p.name),
            "avatar_seed":  avatar_seed(p.name),
            "mlbam_id":     get_mlbam_id(p),
            "espn_id":      get_espn_id(p),
            "is_pitcher":   "true" if is_pitcher(p) else "false",
        })

    # ── Trade target value comparison ─────────────────────────────────────────
    print("Building trade value comparison...")
    try:
        trade_targets = build_trade_value_comparison(league, my_team)
    except Exception as exc:
        print(f"  Trade targets failed (non-fatal): {exc}")
        trade_targets = {"buy_targets": [], "sell_high": []}

    # ── Lineup Lab ────────────────────────────────────────────────────────────
    print("Building Lineup Lab (optimal lineup + position impact)...")
    try:
        lineup_lab = build_lineup_lab(league, my_team)
        if lineup_lab.get("error"):
            print(f"  Lineup Lab error (non-fatal): {lineup_lab['error']}")
        else:
            n_slots = len(lineup_lab.get("optimal", []))
            n_teams = len(lineup_lab.get("all_team_names", []))
            print(f"  Lineup Lab: {n_slots} optimal slots, {n_teams} teams indexed")
    except Exception as exc:
        print(f"  Lineup Lab failed (non-fatal): {exc}")
        lineup_lab = {"error": str(exc)}

    # ── Season Simulation (Monte Carlo) ──────────────────────────────────────
    print("Running season simulation (Monte Carlo)...")
    try:
        from fdb.simulate import run_season_simulation
        season_sim = run_season_simulation(league)
        if season_sim.get("error"):
            print(f"  Season sim error (non-fatal): {season_sim['error']}")
        else:
            cw = season_sim.get("current_week", "?")
            wr = season_sim.get("weeks_remaining", "?")
            ns = season_sim.get("n_sims", 0)
            print(f"  Season sim complete: {ns} sims, week {cw}, {wr} weeks remaining")
    except Exception as exc:
        print(f"  Season simulation failed (non-fatal): {exc}")
        season_sim = {"error": str(exc)}

    return {
        "title":        f"Fantasy Baseball Daily Briefing — {datetime.now().strftime('%A, %B %d %Y')}",
        "generated":    datetime.now().strftime("%A, %B %d %Y at %I:%M %p"),
        "ref_text":     ref_text,
        "standings":    standings,
        "matchup":      matchup_data,
        "win_prob":     wp,
        "my_summary":   my_sum,
        "opp_summary":  opp_sum,
        "comparison":   comparison,
        "injuries":     injuries,
        "my_roster":    my_roster_rows,
        "opp_roster":   opp_roster_rows,
        "waiver_recs":  waiver_rows,
        "top_rostered": top_rostered,
        "recent_moves": moves,
        "waiver_rank":  safe_get(my_team, "waiver_rank", "waiverRank", default="?"),
        "today_games":      today_games,
        "hitter_matchups":  hitter_matchups,
        "season_intel":     season_intel,
        "all_team_rosters": all_team_rosters,
        "trade_targets":    trade_targets,
        "season_sim":       season_sim,
        "lineup_lab":       lineup_lab,
        "season_pace":      _safe_season_pace(league, season_sim),
        "week_scoring":     week_scoring,
        "roster_blueprint": roster_blueprint,
        "streaming_sps":    streaming_sps,
        "stream_plan":      stream_plan,
    }


def _safe_season_pace(league, season_sim: dict) -> dict:
    """Run build_season_pace_payload; return empty dict on any failure."""
    try:
        # currentMatchupPeriod = fantasy matchup week (weekly).
        # current_week / scoringPeriodId = daily counter in baseball — NOT the week.
        # Prefer season_sim value (already corrected), then league attribute directly.
        cw_sim = (season_sim or {}).get("current_week", 0)
        cw_league = int(as_float(
            safe_get(league, "currentMatchupPeriod", "current_week", default=1)
        ))
        cw = cw_sim if cw_sim >= 1 else cw_league
        tw = (season_sim or {}).get("total_weeks", 26) or 26
        print(f"  Building season pace payload… (matchup week {cw}/{tw})")
        return build_season_pace_payload(league, current_week=cw, total_weeks=tw)
    except Exception as exc:
        print(f"  Season pace payload failed (non-fatal): {exc}")
        return {"error": str(exc), "my_team_rows": [], "all_teams": []}
