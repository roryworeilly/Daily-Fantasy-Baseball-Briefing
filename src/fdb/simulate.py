"""
Season Simulation Engine — Fantasy Baseball Daily Briefing
==========================================================

Monte Carlo season simulation that projects final standings, playoff odds,
schedule-strength, player win contributions, and the RP value edge for this
scoring system.

Public API (called from model.py / run.py):
    run_season_simulation(league) -> dict
        Returns all simulation data needed by the HTML renderer.

Design notes
------------
• Pure-Python random module — no numpy/scipy dependency required.
• 500 simulations × 26 weeks × N_TEAMS ≈ 91 k matchup draws — finishes in
  < 2 s on a modern laptop.
• Weekly score model:
    team_score_week_i = Normal(mu, mu * CV)  where CV ≈ 0.18
    This matches observed fantasy-baseball weekly score distributions.
• Past weeks (week < current_week) are locked: actual W/L preserved.
• Relief-pitcher value analysis surfaces the holds advantage specific to
  this league's scoring (HD=5, SVHD=2 ⟹ one hold = 7 pts, same as a save).
"""
from __future__ import annotations

import math
import random
import traceback
from collections import defaultdict
from datetime import datetime

from fdb.settings import (
    MY_TEAM_NAME, N_TEAMS,
    BATTING_SCORING, PITCHING_SCORING,
)
from fdb.model import (
    get_projected_pts,
    get_weekly_projected_pts,
    is_pitcher,
    is_starter_role,
    is_reliever_role,
    get_player_slots,
    get_lineup_slot,
    get_player_status,
    as_float,
    safe_get,
    fmt,
    best_lineup_pts,
)

# ── Simulation constants ──────────────────────────────────────────────────────
TOTAL_WEEKS       = 26          # standard ESPN fantasy baseball season length
N_SIMS            = 500         # Monte Carlo iterations
WEEKLY_CV         = 0.18        # coefficient of variation for weekly score
PLAYOFF_SPOTS     = 6           # top N teams make playoffs (adjust if needed)
MIN_WEEKLY_SCORE  = 0.0         # floor for weekly score draws


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _my_team_name_matches(name: str) -> bool:
    return MY_TEAM_NAME.lower() in name.lower()


def _draw_weekly_score(mu: float, rng: random.Random) -> float:
    """Sample one team's weekly score from a truncated normal distribution."""
    if mu <= 0:
        return 0.0
    sigma = mu * WEEKLY_CV
    score = rng.gauss(mu, sigma)
    return max(MIN_WEEKLY_SCORE, score)


# ══════════════════════════════════════════════════════════════════════════════
# TEAM DATA EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def _get_team_weekly_mu(team) -> float:
    """
    Mean weekly score for a team — the simulation baseline.

    Uses best_weekly_lineup_pts() which honours IL, two-start multipliers,
    and per-player projections.  Falls back to sum of get_weekly_projected_pts
    if the primary call fails.
    """
    try:
        return max(0.0, best_lineup_pts(team, weekly=True))
    except Exception:
        pass
    # Fallback: simple sum across active roster
    total = 0.0
    for p in team.roster:
        slot   = get_lineup_slot(p)
        status = get_player_status(p)
        on_il  = slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", "")
        if not on_il:
            total += get_weekly_projected_pts(p)
    return max(0.0, total)


def _build_team_profiles(league) -> dict:
    """
    Compute per-team scoring profiles used in simulation.

    Returns {team_name: {
        "mu":         float,   # mean weekly pts
        "wins":       int,     # current wins
        "losses":     int,     # current losses
        "tid":        int,     # ESPN team ID
        "season_pts": float,   # total projected season pts (all rostered players)
        "rp_pts":     float,   # projected pts from relief pitchers
        "sp_pts":     float,   # projected pts from starters
        "hit_pts":    float,   # projected pts from hitters
        "n_closers":  int,     # closers on roster (SV-eligible RPs)
        "n_holds":    int,     # setup men on roster (HD-eligible RPs)
        "is_mine":    bool,
    }}
    """
    profiles = {}
    for team in league.teams:
        mu       = _get_team_weekly_mu(team)
        wins     = int(as_float(safe_get(team, "wins",   default=0)))
        losses   = int(as_float(safe_get(team, "losses", default=0)))
        tid      = int(as_float(safe_get(team, "team_id", default=0)))

        sp_pts   = 0.0
        rp_pts   = 0.0
        hit_pts  = 0.0
        n_closers = 0
        n_holds   = 0

        for p in team.roster:
            pts  = get_projected_pts(p)
            slot = get_lineup_slot(p)
            on_il = slot in ("IL", "IR") or \
                    get_player_status(p) not in ("ACTIVE", "NORMAL", "")
            if on_il:
                continue

            if is_pitcher(p):
                if is_starter_role(p):
                    sp_pts += pts
                elif is_reliever_role(p):
                    rp_pts += pts
                    # Rough closer/setup classification: if name appears in
                    # bullpen hierarchy data they'd be a closer; otherwise
                    # treat high-proj RPs (> 200 pts) as potential closers.
                    if pts >= 220:
                        n_closers += 1
                    elif pts >= 130:
                        n_holds += 1
                else:
                    # Mixed SP/RP
                    sp_pts += pts * 0.6
                    rp_pts += pts * 0.4
            else:
                hit_pts += pts

        profiles[team.team_name] = {
            "mu":         mu,
            "wins":       wins,
            "losses":     losses,
            "tid":        tid,
            "season_pts": sp_pts + rp_pts + hit_pts,
            "rp_pts":     rp_pts,
            "sp_pts":     sp_pts,
            "hit_pts":    hit_pts,
            "n_closers":  n_closers,
            "n_holds":    n_holds,
            "is_mine":    _my_team_name_matches(team.team_name),
        }
    return profiles


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULE EXTRACTION / GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_schedule(league) -> dict[int, list[tuple[str, str]]]:
    """
    Attempt to fetch the full season schedule from the ESPN API.

    Returns {week_num: [(team_a_name, team_b_name), ...]}

    Strategy:
      - Pull box_scores for weeks 1..TOTAL_WEEKS.
      - ESPN returns matchup pairs even for future (unplayed) weeks.
      - If a week call fails, skip it; missing weeks get filled by
        round-robin in _build_round_robin_schedule().
    """
    schedule: dict[int, list[tuple[str, str]]] = {}
    for w in range(1, TOTAL_WEEKS + 1):
        try:
            boxes = league.box_scores(w)
            pairs: list[tuple[str, str]] = []
            for b in boxes:
                h = getattr(b, "home_team", None)
                a = getattr(b, "away_team", None)
                if h and a:
                    pairs.append((h.team_name, a.team_name))
            if pairs:
                schedule[w] = pairs
        except Exception:
            pass
    return schedule


def _build_round_robin_schedule(
    team_names: list[str],
    current_week: int,
    total_weeks: int,
) -> dict[int, list[tuple[str, str]]]:
    """
    Generate a synthetic round-robin schedule for weeks that the ESPN API
    didn't return data for.

    Uses the circle-rotation algorithm to produce a balanced schedule.
    If N is odd, one team gets a bye each round.
    """
    names  = list(team_names)
    n      = len(names)
    sched: dict[int, list[tuple[str, str]]] = {}

    # Each round produces n//2 matchups
    rounds_needed = max(n - 1, 1)
    for week in range(1, total_weeks + 1):
        rnd   = (week - 1) % rounds_needed
        fixed = names[0]
        rot   = names[1:]
        rotated = rot[rnd:] + rot[:rnd]
        participants = [fixed] + rotated

        pairs: list[tuple[str, str]] = []
        for i in range(n // 2):
            pairs.append((participants[i], participants[n - 1 - i]))
        sched[week] = pairs

    return sched


def _get_full_schedule(league) -> tuple[dict, int]:
    """
    Returns (schedule, current_week).

    schedule: {week: [(teamA, teamB), ...]}
    current_week: ESPN's current matchup period (weekly, not daily scoring period)
    """
    # currentMatchupPeriod = fantasy matchup week (1, 2, 3…)
    # current_week / scoringPeriodId = daily counter (increments every day in baseball)
    # We always want the weekly matchup period here.
    current_week = int(as_float(
        safe_get(league, "currentMatchupPeriod", "current_week", default=1)
    ))
    current_week = max(1, min(current_week, TOTAL_WEEKS))

    print("  Fetching ESPN schedule data...")
    schedule = _fetch_schedule(league)

    team_names = [t.team_name for t in league.teams]
    # Fill in any weeks the ESPN API didn't return
    rr = _build_round_robin_schedule(team_names, current_week, TOTAL_WEEKS)
    for w in range(1, TOTAL_WEEKS + 1):
        if w not in schedule:
            schedule[w] = rr.get(w, [])

    fetched_real = sum(1 for w, pairs in schedule.items()
                       if pairs and w <= TOTAL_WEEKS)
    print(f"  Schedule: {fetched_real} weeks with real ESPN pairings "
          f"(current week {current_week})")
    return schedule, current_week


# ══════════════════════════════════════════════════════════════════════════════
# SINGLE SIMULATION RUN
# ══════════════════════════════════════════════════════════════════════════════

def _simulate_once(
    profiles:      dict,
    schedule:      dict[int, list[tuple[str, str]]],
    current_week:  int,
    rng:           random.Random,
) -> dict[str, dict]:
    """
    Simulate one full season from the current week onward.

    Past weeks' actual W/L are seeded from `profiles[name]["wins/losses"]`.
    Returns {team_name: {"wins": int, "losses": int, "pts": float}}
    """
    # Initialise from actual record
    results = {
        name: {"wins": prof["wins"], "losses": prof["losses"], "pts": 0.0}
        for name, prof in profiles.items()
    }

    for week in range(current_week, TOTAL_WEEKS + 1):
        pairs = schedule.get(week, [])
        for (ta, tb) in pairs:
            if ta not in profiles or tb not in profiles:
                continue
            score_a = _draw_weekly_score(profiles[ta]["mu"], rng)
            score_b = _draw_weekly_score(profiles[tb]["mu"], rng)
            results[ta]["pts"] += score_a
            results[tb]["pts"] += score_b
            if score_a > score_b:
                results[ta]["wins"]   += 1
                results[tb]["losses"] += 1
            elif score_b > score_a:
                results[tb]["wins"]   += 1
                results[ta]["losses"] += 1
            else:
                # Exact ties are extremely rare; ESPN awards 0.5 wins, 0 losses
                results[ta]["wins"]   += 0.5
                results[tb]["wins"]   += 0.5

    return results


def _rank_teams(results: dict[str, dict]) -> dict[str, int]:
    """Rank teams by wins (then pts as tiebreaker).  Rank 1 = best."""
    ordered = sorted(results.items(), key=lambda kv: (-kv[1]["wins"], -kv[1]["pts"]))
    return {name: rank + 1 for rank, (name, _) in enumerate(ordered)}


# ══════════════════════════════════════════════════════════════════════════════
# MONTE CARLO AGGREGATION
# ══════════════════════════════════════════════════════════════════════════════

def _run_monte_carlo(
    profiles:     dict,
    schedule:     dict,
    current_week: int,
    n_sims:       int = N_SIMS,
) -> dict:
    """
    Run n_sims full-season simulations.

    Returns aggregated stats per team:
    {team_name: {
        "playoff_pct":    float,   # 0–100
        "champion_pct":   float,   # 0–100
        "avg_wins":       float,
        "avg_rank":       float,
        "wins_dist":      list[int],  # histogram: wins_dist[w] = # sims with w wins
        "proj_wins_low":  int,   # 10th-percentile
        "proj_wins_mid":  int,   # median
        "proj_wins_high": int,   # 90th-percentile
    }}
    """
    rng = random.Random(42)  # deterministic seed for reproducibility

    # Accumulators
    playoff_count  = defaultdict(int)
    champ_count    = defaultdict(int)
    total_wins     = defaultdict(float)
    total_rank     = defaultdict(float)
    wins_all       = defaultdict(list)

    for _ in range(n_sims):
        sim = _simulate_once(profiles, schedule, current_week, rng)
        ranks = _rank_teams(sim)

        for name, res in sim.items():
            w = res["wins"]
            total_wins[name] += w
            total_rank[name] += ranks[name]
            wins_all[name].append(w)
            if ranks[name] <= PLAYOFF_SPOTS:
                playoff_count[name] += 1
            if ranks[name] == 1:
                champ_count[name] += 1

    aggregated = {}
    for name in profiles:
        ws = sorted(wins_all[name])
        lo = int(ws[int(len(ws) * 0.10)])
        md = int(ws[len(ws) // 2])
        hi = int(ws[int(len(ws) * 0.90)])

        aggregated[name] = {
            "playoff_pct":    round(100.0 * playoff_count[name] / n_sims, 1),
            "champion_pct":   round(100.0 * champ_count[name]  / n_sims, 1),
            "avg_wins":       round(total_wins[name] / n_sims, 1),
            "avg_rank":       round(total_rank[name] / n_sims, 1),
            "proj_wins_low":  lo,
            "proj_wins_mid":  md,
            "proj_wins_high": hi,
        }

    return aggregated


# ══════════════════════════════════════════════════════════════════════════════
# PLAYER WIN CONTRIBUTION (MY TEAM ONLY)
# ══════════════════════════════════════════════════════════════════════════════

def _player_win_contribution(
    my_team,
    profiles:     dict,
    schedule:     dict,
    current_week: int,
    n_sims:       int = 100,
) -> list[dict]:
    """
    Estimate each rostered player's contribution to my team's win total.

    Method: compare average wins WITH player vs. WITHOUT player
    (drop their weekly projection from the team mu).
    Run n_sims mini-simulations for each comparison.

    Returns list of dicts sorted by descending win_contribution, each with:
        player, pos, is_pitcher, weekly_pts, win_contribution,
        pct_of_team_mu, age_tier_label (if available)
    """
    my_name = None
    for name in profiles:
        if _my_team_name_matches(name):
            my_name = name
            break
    if not my_name:
        return []

    base_mu = profiles[my_name]["mu"]
    rng     = random.Random(7)

    # Baseline: my team's average wins with full roster
    def _avg_wins_for_mu(mu: float) -> float:
        prof_copy = dict(profiles)
        prof_copy[my_name] = dict(profiles[my_name])
        prof_copy[my_name]["mu"] = max(0.0, mu)
        total = 0.0
        for _ in range(n_sims):
            sim   = _simulate_once(prof_copy, schedule, current_week, rng)
            ranks = _rank_teams(sim)
            total += sim[my_name]["wins"]
        return total / n_sims

    baseline_wins = _avg_wins_for_mu(base_mu)

    results = []
    for p in my_team.roster:
        slot   = get_lineup_slot(p)
        status = get_player_status(p)
        on_il  = slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", "")

        weekly = get_weekly_projected_pts(p)
        if weekly <= 0:
            weekly_show = 0.0
        else:
            weekly_show = round(weekly, 1)

        # Win contribution = how many wins we lose without this player
        mu_without  = max(0.0, base_mu - weekly)
        wins_without = _avg_wins_for_mu(mu_without)
        win_contrib = round(baseline_wins - wins_without, 2)

        slots = get_player_slots(p)
        pos   = ", ".join(slots[:2]) if slots else "?"
        pitcher = is_pitcher(p)

        results.append({
            "player":          p.name,
            "pos":             pos,
            "is_pitcher":      pitcher,
            "is_reliever":     is_reliever_role(p),
            "is_starter":      is_starter_role(p),
            "weekly_pts":      weekly_show,
            "season_proj":     round(get_projected_pts(p), 0),
            "win_contribution": win_contrib,
            "pct_of_team_mu":  round(100 * weekly / base_mu, 1) if base_mu > 0 else 0.0,
            "on_il":           on_il,
            "status":          status,
        })

    results.sort(key=lambda r: -r["win_contribution"])
    return results


# ══════════════════════════════════════════════════════════════════════════════
# RELIEF PITCHER VALUE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def _rp_value_analysis(league, profiles: dict) -> dict:
    """
    Surface the RP / holds advantage for this scoring system.

    Returns:
        league_avg_rp_pct:  avg RP pts as % of total pitching pts (all teams)
        league_avg_sp_pct:  avg SP pts as % of total pitching pts
        team_breakdowns:    [{team, rp_pts, sp_pts, hit_pts, rp_pct, n_closers, n_holds}]
        my_team_breakdown:  dict for my team
        hold_value_insight: formatted string explaining holds edge in this league
    """
    breakdowns = []
    for name, prof in profiles.items():
        total_p = prof["sp_pts"] + prof["rp_pts"]
        rp_pct  = round(100 * prof["rp_pts"] / total_p, 1) if total_p > 0 else 0.0
        sp_pct  = round(100 * prof["sp_pts"] / total_p, 1) if total_p > 0 else 0.0
        hit_pct = round(100 * prof["hit_pts"] / prof["season_pts"], 1) \
                  if prof["season_pts"] > 0 else 0.0
        breakdowns.append({
            "team":      name,
            "rp_pts":    round(prof["rp_pts"],  0),
            "sp_pts":    round(prof["sp_pts"],  0),
            "hit_pts":   round(prof["hit_pts"], 0),
            "rp_pct":    rp_pct,
            "sp_pct":    sp_pct,
            "hit_pct":   hit_pct,
            "n_closers": prof["n_closers"],
            "n_holds":   prof["n_holds"],
            "is_mine":   prof["is_mine"],
        })

    breakdowns.sort(key=lambda d: -d["rp_pts"])

    rp_pcts = [d["rp_pct"] for d in breakdowns if d["rp_pct"] > 0]
    sp_pcts = [d["sp_pct"] for d in breakdowns if d["sp_pct"] > 0]
    league_avg_rp_pct = round(sum(rp_pcts) / len(rp_pcts), 1) if rp_pcts else 0.0
    league_avg_sp_pct = round(sum(sp_pcts) / len(sp_pcts), 1) if sp_pcts else 0.0

    my_breakdown = next((d for d in breakdowns if d["is_mine"]), breakdowns[0] if breakdowns else {})

    # Holds insight (league-specific scoring)
    # HD=5, SVHD=2  ⟹  one hold = 7 pts
    # A 30-hold RP projects ~210 pts  — same as a 35-save closer
    hold_pts_per_hold = PITCHING_SCORING.get("HD", 0) + PITCHING_SCORING.get("SVHD", 0)
    save_pts_per_save = PITCHING_SCORING.get("SV", 0)
    insight = (
        f"In this league each Hold = {hold_pts_per_hold} pts "
        f"(HD+{PITCHING_SCORING.get('HD',0)} + SVHD+{PITCHING_SCORING.get('SVHD',0)}), "
        f"same as a Save = {save_pts_per_save} pts. "
        f"A 30-hold setup man projects ≈{30*hold_pts_per_hold} pts — "
        f"nearly identical to a 35-save elite closer ({35*save_pts_per_save} pts). "
        f"Teams with 2+ high-hold RPs have a structural RP edge over "
        f"closer-only bullpens."
    )

    return {
        "league_avg_rp_pct":  league_avg_rp_pct,
        "league_avg_sp_pct":  league_avg_sp_pct,
        "team_breakdowns":    breakdowns,
        "my_team_breakdown":  my_breakdown,
        "hold_pts_per_hold":  hold_pts_per_hold,
        "save_pts_per_save":  save_pts_per_save,
        "hold_value_insight": insight,
    }


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULE STRENGTH
# ══════════════════════════════════════════════════════════════════════════════

def _schedule_strength(
    profiles:     dict,
    schedule:     dict,
    current_week: int,
) -> list[dict]:
    """
    For each team, compute the average projected weekly score of remaining
    opponents as a Strength of Schedule (SOS) metric.

    Returns list sorted by sos_mu descending (hardest schedule first).
    """
    sos: dict[str, list[float]] = {name: [] for name in profiles}

    for week in range(current_week, TOTAL_WEEKS + 1):
        for (ta, tb) in schedule.get(week, []):
            if ta in profiles and tb in profiles:
                sos[ta].append(profiles[tb]["mu"])
                sos[tb].append(profiles[ta]["mu"])

    rows = []
    for name, opp_mus in sos.items():
        avg = round(sum(opp_mus) / len(opp_mus), 1) if opp_mus else 0.0
        games_remaining = len(opp_mus)
        rows.append({
            "team":             name,
            "sos_mu":           avg,
            "games_remaining":  games_remaining,
            "is_mine":          profiles[name]["is_mine"],
        })

    rows.sort(key=lambda r: -r["sos_mu"])
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def run_season_simulation(league) -> dict:
    """
    Run the full season simulation pipeline.

    Called from model.build_payload(); results passed to html.render_html().

    Returns {
        "sim_standings":    list[dict],  # per-team projected standings + playoff odds
        "player_impact":    list[dict],  # my team's per-player win contributions
        "rp_analysis":      dict,        # league-wide RP/holds value breakdown
        "schedule_strength":list[dict],  # remaining SOS per team
        "current_week":     int,
        "total_weeks":      int,
        "weeks_remaining":  int,
        "n_sims":           int,
        "playoff_spots":    int,
        "error":            str or None,
    }
    """
    try:
        print("  Building team scoring profiles...")
        profiles = _build_team_profiles(league)

        print("  Fetching full season schedule...")
        schedule, current_week = _get_full_schedule(league)

        weeks_remaining = max(0, TOTAL_WEEKS - current_week + 1)
        print(f"  Running {N_SIMS} season simulations "
              f"({weeks_remaining} weeks remaining)...")
        mc = _run_monte_carlo(profiles, schedule, current_week, N_SIMS)

        # ── Combine into a single ranked standings list ──────────────────────
        sim_standings = []
        for name, prof in profiles.items():
            m = mc.get(name, {})
            sim_standings.append({
                "team":          name,
                "current_wins":  prof["wins"],
                "current_losses":prof["losses"],
                "avg_proj_wins": m.get("avg_wins",  prof["wins"]),
                "avg_proj_losses": TOTAL_WEEKS - m.get("avg_wins", prof["wins"]),
                "proj_wins_low": m.get("proj_wins_low",  prof["wins"]),
                "proj_wins_mid": m.get("proj_wins_mid",  prof["wins"]),
                "proj_wins_high":m.get("proj_wins_high", prof["wins"]),
                "playoff_pct":   m.get("playoff_pct",  0.0),
                "champion_pct":  m.get("champion_pct", 0.0),
                "avg_rank":      m.get("avg_rank",     0.0),
                "weekly_mu":     round(prof["mu"], 1),
                "season_pts":    round(prof["season_pts"], 0),
                "is_mine":       prof["is_mine"],
            })

        sim_standings.sort(key=lambda r: -r["playoff_pct"])

        # ── Player win contribution for my team ──────────────────────────────
        my_team_obj = None
        for team in league.teams:
            if _my_team_name_matches(team.team_name):
                my_team_obj = team
                break

        print("  Computing per-player win contributions (my team)...")
        player_impact = []
        if my_team_obj:
            try:
                player_impact = _player_win_contribution(
                    my_team_obj, profiles, schedule, current_week,
                    n_sims=100,
                )
            except Exception as exc:
                print(f"    Player impact analysis failed (non-fatal): {exc}")

        # ── RP value analysis ────────────────────────────────────────────────
        print("  Analysing RP / holds value...")
        try:
            rp_analysis = _rp_value_analysis(league, profiles)
        except Exception as exc:
            print(f"    RP analysis failed (non-fatal): {exc}")
            rp_analysis = {}

        # ── Schedule strength ────────────────────────────────────────────────
        print("  Computing schedule strength...")
        try:
            sched_strength = _schedule_strength(profiles, schedule, current_week)
        except Exception as exc:
            print(f"    Schedule strength failed (non-fatal): {exc}")
            sched_strength = []

        return {
            "sim_standings":     sim_standings,
            "player_impact":     player_impact,
            "rp_analysis":       rp_analysis,
            "schedule_strength": sched_strength,
            "current_week":      current_week,
            "total_weeks":       TOTAL_WEEKS,
            "weeks_remaining":   weeks_remaining,
            "n_sims":            N_SIMS,
            "playoff_spots":     PLAYOFF_SPOTS,
            "error":             None,
        }

    except Exception as exc:
        traceback.print_exc()
        return {
            "sim_standings":     [],
            "player_impact":     [],
            "rp_analysis":       {},
            "schedule_strength": [],
            "current_week":      1,
            "total_weeks":       TOTAL_WEEKS,
            "weeks_remaining":   TOTAL_WEEKS,
            "n_sims":            N_SIMS,
            "playoff_spots":     PLAYOFF_SPOTS,
            "error":             str(exc),
        }
