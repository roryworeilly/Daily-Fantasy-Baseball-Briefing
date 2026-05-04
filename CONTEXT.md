# FDB — Context Document

> **Purpose:** Read this at the start of every new session before touching any code.
> Keep it updated whenever the architecture, public APIs, or UI structure changes.

---

## Project Overview

**Fantasy Baseball Daily Briefing (FDB)** — A Python app that generates a self-contained HTML morning briefing for a fantasy baseball team. It pulls live data from the ESPN Fantasy API, enriches it with FanGraphs projections, Statcast metrics, and MLB schedule data, then renders a full interactive HTML page.

**Owner:** Rory O'Reilly — 14-team ESPN H2H points league, team name "The Undisputed"

---

## Repository Layout

```
FB/                              ← workspace root (SCRIPT_DIR)
├── src/fdb/                     ← main Python package
│   ├── __init__.py              ← imports run.main
│   ├── assets.py                ← loads res/briefing.css + res/briefing.js from disk
│   ├── html.py                  ← HTML renderer + semantic dashboard shell (6045 lines)
│   ├── model.py                 ← all data-fetch + scoring logic (6193 lines)
│   ├── run.py                   ← CLI entry point / cache auto-rebuild
│   ├── settings.py              ← all config, scoring dicts, DB handles
│   ├── simulate.py              ← Monte Carlo season simulator
│   └── utils.py                 ← shared helpers (normalize_name, compact, etc.)
├── tools/
│   ├── build_reference_cache.py ← FanGraphs season stats → player_reference_cache.json
│   ├── build_projection_cache.py← FanGraphs/Steamer projections → projection_cache.json
│   ├── build_statcast_cache.py  ← pybaseball Statcast data → statcast_cache.json
│   ├── generate_draft_logs.py   ← draft history tool
│   └── model_comparison.py      ← ESPN vs FDB scoring comparison tool
├── res/
│   ├── briefing.css             ← all page CSS (~1865 lines, edit directly)
│   └── briefing.js              ← all page JS  (~3778 lines, edit directly)
├── test/
│   ├── conftest.py              ← pytest stubs (no ESPN credentials needed)
│   ├── test_utils.py            ← 32 tests — utils.py
│   ├── test_simulate.py         ← 13 tests — simulate.py (tie regression test)
│   ├── test_scoring.py          ← 18 tests — scoring dicts, holds/BS regression
│   └── test_model_scoring.py    ← 17 tests — _hitter_pts_from_stats, etc.
├── dep/
│   ├── requirements.txt         ← espn-api, requests, requests-cache, certifi, pybaseball
│   └── requirements-dev.txt     ← pytest, pytest-cov, flake8
├── .github/
│   ├── workflows/ci.yml         ← GitHub Actions: Python 3.10/3.11/3.12 matrix
│   ├── ISSUE_TEMPLATE/          ← bug_report.md, feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
├── doc/                         ← internal docs (roadmap, model analysis, bullpen notes)
├── config/                      ← macOS LaunchAgent plist + shell helpers
├── Run.command                  ← one-click macOS launcher
├── CHANGELOG.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── README.md
└── CONTEXT.md                   ← THIS FILE
```

**Cache files** (project root, auto-generated, gitignored):
- `player_reference_cache.json` — FanGraphs season stats
- `projection_cache.json`       — FanGraphs/Steamer projections
- `statcast_cache.json`         — Statcast xERA, xwOBA, CSW%, barrel%, exit velo
- `current_season_cache.json`   — in-season blended stats
- `daily_matchup_cache.json`    — today's matchup snapshot
- `espn_cache.sqlite`           — requests-cache ESPN API cache

---

## Settings (`src/fdb/settings.py`)

All values read from environment / `.env` file:

| Variable | Default | Notes |
|---|---|---|
| `LEAGUE_ID` | `1457877076` | ESPN league ID |
| `YEAR` | `2026` | Season year |
| `SWID` | `""` | ESPN auth cookie |
| `ESPN_S2` | `""` | ESPN auth cookie |
| `MY_TEAM_NAME` | `"The Undisputed"` | Must match ESPN exactly |
| `N_TEAMS` | `14` | Teams in league |
| `WEEKLY_IP_LIMIT` | `50` | IP cap for streaming plan |
| `REPLACEMENT_BUFFER` | `3` | Extra players above slot count for replacement level |
| `STASH_SCORE_THRESHOLD` | `50.0` | Min base score to flag stash target |
| `SEASON_INTEL_FA_THRESHOLD` | `60.0` | Min score for long-season FA watch |
| `SEASON_TREND_MIN_GAMES` | `5` | Min games for trend window |
| `SEASON_TREND_LOOKBACK` | `45` | Days lookback for current-season trend |

**Scoring dicts (H2H points league):**
```python
BATTING_SCORING  = { "R":1, "HR":1, "TB":1, "RBI":1, "BB":1, "SB":1,
                     "K":-1, "E":-1, "GWRBI":2, "GSHR":4, "CYC":15 }

PITCHING_SCORING = { "IP":3, "H":-1, "ER":-2, "HR":-1, "BB":-1, "K":1,
                     "QS":2, "CG":5, "SO":9, "NH":10, "PG":35,
                     "W":2, "L":-2, "SV":6, "BS":-3, "HD":5, "SVHD":2 }
```

**Roster slots:**
```python
SLOTS_PER_TEAM = { "C":1, "1B":1, "2B":1, "3B":1, "SS":1,
                   "OF":3, "UTIL":1, "SP":4, "RP":3, "P":7 }
```

**Cache paths** (all relative to `SCRIPT_DIR` = repo root):
```python
REFERENCE_DB_PATH  = SCRIPT_DIR / "player_reference_cache.json"
PROJECTION_DB_PATH = SCRIPT_DIR / "projection_cache.json"
STATCAST_DB_PATH   = SCRIPT_DIR / "statcast_cache.json"
```

---

## Data Flow

```
run.main()
  └─ _auto_rebuild_cache()   ← refreshes stale caches if needed
  └─ model.connect()         ← returns espn_api.baseball.League object
  └─ model.build_payload(league)
        ├─ fetch_todays_mlb_schedule()        → today_games
        ├─ get_matchup() + scoring breakdown  → matchup, win_prob
        ├─ get_waiver_recommendations()       → waiver_recs
        ├─ build_market_context()             → used for scarcity/replacement
        ├─ build_streaming_sp_list()          → streaming_sps (individual pickups)
        ├─ build_weekly_streaming_plan()      → stream_plan (full week view)
        ├─ build_lineup_lab()                 → lineup_lab
        ├─ run_season_simulation()            → season_sim
        ├─ build_season_pace_payload()        → season_pace
        └─ returns data dict (see below)
  └─ html.render_html(data)  ← returns full HTML string
  └─ write HTML to file + open in browser
```

### `build_payload()` return keys

```python
{
  "title", "generated", "ref_text",
  "standings",          # list[dict] — league standings rows
  "matchup",            # dict — live scores, week, status
  "win_prob",           # dict — prob, my_proj, opp_proj, my_score, opp_score
  "my_summary",         # dict — active_base, lineup_pts, hitter_base, pitcher_base, injury_count
  "opp_summary",        # dict — same shape
  "comparison",         # list[dict] — head-to-head player comparison rows
  "injuries",           # list[str] — injury alert strings
  "my_roster",          # list[dict] — _player_row() dicts
  "opp_roster",         # list[dict] — same shape
  "waiver_recs",        # list[dict] — waiver recommendation rows
  "top_rostered",       # list[dict] — top leaguewide players
  "recent_moves",       # list[dict] — recent adds/drops/trades
  "waiver_rank",        # str/int
  "today_games",        # list[dict] — MLB schedule for today
  "hitter_matchups",    # list[dict] — hitter vs pitcher matchup data
  "season_intel",       # dict — {my_il, il_watch, fa_targets}
  "all_team_rosters",   # dict — team_name → list[_player_row dicts]
  "trade_targets",      # list[dict]
  "season_sim",         # dict — Monte Carlo results
  "lineup_lab",         # dict — best lineup optimizer results
  "season_pace",        # dict — actual vs projected pace
  "week_scoring",       # dict — week scoring breakdown
  "roster_blueprint",   # dict — slot coverage analysis
  "streaming_sps",      # list[dict] — individual SP streaming picks
  "stream_plan",        # dict — full weekly pitcher plan (see below)
}
```

### `stream_plan` dict shape

```python
{
  "week_label":   str,
  "pitchers": [
    {
      "name": str, "team": str, "mlbam_id": str,
      "starts": [{"date", "opp_abbr", "home_abbr", "is_home",
                  "matchup": {"score","grade","color","park_factor",
                              "opp_woba","opp_k_pct","note"}}],
      "start_count": int, "is_two_start": bool,
      "proj_ip": float, "proj_k": float,
      "ratio_risk": bool, "slot": str,
    }
  ],
  "totals": {
    "proj_ip": float, "proj_k": float,
    "ip_limit": int,  "ip_flag": bool,
    "ratio_risk": bool, "ratio_risk_names": list[str],
  },
  "conflicts":      list[str],   # human-readable conflict warnings
  "streaming_slots": int,        # available SP/RP slots not used by two-start starters
}
```

---

## Key Model Functions (`src/fdb/model.py`)

### Player helpers
| Function | Purpose |
|---|---|
| `is_pitcher(player)` | Bool — ESPN player object |
| `is_starter_role(player)` | Bool — SP vs RP based on stats/position |
| `get_player_status(player)` | Returns "ACTIVE", "IL", "DTD", etc. |
| `get_mlbam_id(player)` | MLB AM ID for headshot/Statcast lookup |
| `normalize_name(name)` → (in utils) | Strips punctuation/accents, lowercase |

### Scoring
| Function | Purpose |
|---|---|
| `_hitter_pts_from_stats(m)` | Raw points from stat dict using BATTING_SCORING |
| `_pitcher_pts_from_stats(m)` | Raw points from stat dict using PITCHING_SCORING |
| `get_projected_pts(player)` | Season projection blend (projection + current season) |
| `get_weekly_projected_pts(player)` | This-week points projection |
| `base_score(player)` | Scaled 0-100 value score |
| `fit_score(player, team)` | Scaled 0-100 fit-to-roster score |
| `best_lineup_pts(team, weekly=False)` | Best achievable points (season or week) |

### Waiver / streaming
| Function | Purpose |
|---|---|
| `get_waiver_recommendations(league, my_team)` | Full waiver wire with pickup reasons |
| `build_streaming_sp_list(league, my_team, today_games)` | Individual SP streamers |
| `build_weekly_streaming_plan(league, my_team, ws, we)` | Full week pitcher plan |
| `score_start_matchup(opp_abbr, home_abbr, is_home)` | A–F matchup grade dict |
| `_get_team_batting_profiles()` | Team-level K%, wOBA, OPS from REFERENCE_DB |
| `_fetch_weekly_game_details(week_start, week_end)` | MLB API → mlbam_id: [starts] |

### Simulation / analytics
| Function | Purpose |
|---|---|
| `run_season_simulation(league)` | Monte Carlo — returns standings, player impact, playoff % |
| `build_lineup_lab(league, my_team)` | Lineup optimizer — slot-by-slot best fit |
| `build_season_pace_payload(league, cw, tw)` | Actual vs projected pace for all teams |
| `build_market_context(league)` | Scarcity/replacement level for all positions |
| `win_probability(league, my_team)` | Current matchup win probability |

---

## HTML Renderer (`src/fdb/html.py`)

### Tab structure (4 top-level tabs after restructure)

```
Today          (data-tab="today")
  ├─ Overview   [tdpane-overview]  — news banner + live matchup + schedule
  ├─ Waivers    [tdpane-waivers]   — streaming plan + waiver wire
  └─ Compare    [tdpane-compare]   — drag-and-drop player comparison

My Team        (data-tab="myteam")
  └─ Full roster + team viewer + League standings (folded in at bottom)

Tools          (data-tab="tools")
  ├─ Analytics   [tspane-analytics] — Monte Carlo model, draft history
  ├─ Season Pace [tspane-seasonpace] — actual vs projected pace
  └─ Trade       [tspane-trade]     — trade calculator (lazy-built)

⋯ More (dropdown)
  └─ How It Works  (data-tab="howitworks") — model explanation + season sim
```

### Tab switcher functions (in `res/briefing.js`)
| Function | Switches |
|---|---|
| `switchTab(tab)` | Top-level tabs (`today`, `myteam`, `tools`, `howitworks`) |
| `switchTodayTab(tab)` | Today inner tabs (`overview`, `waivers`, `compare`) |
| `switchToolsTab(tab)` | Tools inner tabs (`analytics`, `seasonpace`, `trade`) |
| `switchWaiverTab(tab)` | Waiver sub-tabs within waivers pane (`hitters`, `pitchers`) |
| `switchInnerTab(tab)` | Legacy — matchup inner tabs (kept for compatibility) |
| `toggleMoreMenu()` | Opens/closes the ⋯ More dropdown |

### localStorage keys
| Key | Default | Notes |
|---|---|---|
| `fdb_tab` | `"today"` | Last active top-level tab |
| `fdb_theme` | `"dark"` | `"dark"` or `"light"` |
| `fdb_rc_*` | `"grid"` | Roster view mode per section (grid/compact/list) |

**Legacy tab remap** (in `DOMContentLoaded`): old saved values `matchup`, `waivers`, `news` → `today`; `league` → `myteam`; `analytics`, `lineuplab`, `seasonpace`, `trade` → `tools`.

### Key HTML section builders
| Function | Renders |
|---|---|
| `_streaming_plan_section(plan_data)` | "Your Pitching Week" card (start chips, IP bar, conflicts) |
| `_streaming_sp_section(streaming_sps)` | Individual SP streamer pickup cards |
| `_waiver_section(rows)` | Full waiver wire hitter/pitcher cards |
| `_blueprint_banner(blueprint)` | Roster slot coverage analysis banner |
| `_roster_cards(rows, title)` | Ring-avatar roster grid with stat pills |
| `_compare_section_v2(my, opp, opp_name)` | Drag-and-drop player comparison panel |
| `_standings_table(rows)` | League standings table |
| `_matchup_scoring_section(my, opp, ...)` | Weekly scoring breakdown table |
| `_hitter_matchups_section(matchups)` | Hitter vs today's pitchers matchup cards |
| `_schedule_section(games, ...)` | Today's MLB schedule with player overlays |
| `_season_intel_card(season_intel)` | IL tracker + long-term FA watch |
| `_team_viewer_inner(all_team_rosters, my_pane)` | Arrow-nav team roster viewer |
| `render_html(data)` | Top-level — assembles full HTML page from data dict |

### CSS / JS assets
- **`res/briefing.css`** — edit directly; loaded at import via `assets.reload_css_js()`; owns visual tokens, layout, states, and utility classes
- **`res/briefing.js`** — edit directly; injected as inline `<script>` at page bottom; owns tabs, modal behavior, dynamic news/scoring/tools, and More menu ARIA state
- CSS variables: `--font-sans`, `--font-display`, `--font-mono`, `--card`, `--card-bg`, `--border`, `--text1`, `--text2`, `--text3`, `--accent`, `--red`, `--hover`, `--surface2`, `--z-sticky`, `--z-dropdown`, `--z-modal`
- Shared UI state classes: `.state-loading`, `.state-message`, `.state-message.error`, `.table-empty`, `.muted`, `.muted-sm`, `.muted-xs`, `.center-cell`, `.strong-cell`, `.accent-cell`, `.inline-player`, `.narrow-shell`
- The generated shell now includes `header`, `nav`, `main`, `footer`, a skip link, explicit button types, modal `role="dialog"` / `aria-modal`, meta description, Open Graph basics, and a data-URI favicon.
- Source files are canonical. Regenerate `output/Daily Briefing.html` with `python3 run_briefing.py`; do not hand-edit generated output.

---

## Utils (`src/fdb/utils.py`)

```python
normalize_name(name: str) -> str
    # strips ASCII punctuation, lowercases, collapses whitespace
    # NOTE: Unicode accents (ñ, é, etc.) are preserved — do NOT test for stripped accents

compact(v, ndigits=4) -> float
    # NaN-safe float rounding

get_metric(row: dict, *keys, default=0.0) -> float
    # returns first non-None value from list of dict keys

cache_is_fresh(path: str, max_age_days=1.0) -> bool
    # checks file mtime
```

---

## Test Suite (`test/`)

**Run:** `python3 -m pytest test/ -q` — 80 tests, all offline (no ESPN credentials)

### conftest.py — what it stubs
- `fdb.settings` replaced with a `types.ModuleType` stub containing all 32 settings attributes
- `requests_cache`, `espn_api`, `espn_api.baseball`, `pybaseball`, `dotenv` all stubbed
- `sys.path` includes `src/` and `tools/`
- **Critical:** `sys.modules["fdb"]` is NOT overridden — only `fdb.settings` is stubbed

### Adding new settings variables
When you add a new variable to `settings.py`, you **must** also add it to `test/conftest.py` in the `_settings` stub block, otherwise all tests will fail with `ImportError: cannot import name '...' from 'fdb.settings'`.

---

## Run Pipeline (`src/fdb/run.py`)

```python
main()
  1. _auto_rebuild_cache("build_reference_cache", REFERENCE_DB_PATH,    "build", max_age_hours=168)
  2. _auto_rebuild_cache("build_projection_cache", PROJECTION_DB_PATH,  "build", max_age_hours=168)
  3. _auto_rebuild_cache("build_statcast_cache",   STATCAST_DB_PATH,    "build", max_age_hours=24)
  4. _purge_espn_fantasy_cache()   # clears espn_cache.sqlite if >23h old
  5. connect() → league
  6. build_payload(league) → data
  7. render_html(data) → html string
  8. write HTML to SCRIPT_DIR/fantasy_briefing.html
  9. open in browser (macOS: subprocess open)
```

**One-click launcher:** `Run.command` in repo root — activates `.venv`, checks `.env`, runs `python -m fdb`.

---

## Simulate (`src/fdb/simulate.py`)

`run_season_simulation(league) -> dict` — Monte Carlo over remaining schedule.

**Key bug fixed:** Ties give `wins += 0.5` only — `losses` is **not** incremented on a tie (ESPN convention). Test `test_simulate.py::test_tie_gives_half_win_no_loss` is the regression guard.

Returns:
```python
{
  "sim_standings":      list[dict],  # team, wins, losses, playoff_pct, etc.
  "player_impact":      list[dict],
  "rp_analysis":        dict,
  "schedule_strength":  list[dict],
  "current_week":       int,
  "total_weeks":        int,
  "weeks_remaining":    int,
  "playoff_spots":      int,
  "n_sims":             int,
}
```

---

## Known Patterns & Conventions

1. **`_player_row(player, team_ctx)`** — the canonical dict shape for roster display. Every section in html.py that renders a player reads from this dict. Keys include: `name`, `pos`, `slot`, `is_pitcher`, `mlbam_id`, `headshot`, `headshot2`, `initials`, `status`, `base_score`, `fit_score`, `proj_pts`, `weekly_pts`, `statcast`, `projection`, `reference`, plus signal flags.

2. **Signal flags on player rows:** `"BUY_LOW"`, `"SELL_HIGH"`, `"BREAKOUT_CANDIDATE"`, `"REGRESSION_RISK"` — used in velocity alerts and pickup reasons.

3. **xERA gap direction:** positive gap (xERA > ERA) = regression risk / SELL. Negative gap (xERA < ERA) = buy low / improvement candidate.

4. **`_pane_inner(html_str)`** — local helper defined in `render_html` that strips the outer `<div ...>...</div>` wrapper from a tab-pane string, used when embedding analytics/seasonpace into the Tools composite tab.

5. **CSS color variables always used** — never hardcode hex colors in html.py f-strings. Use `var(--accent)`, `var(--red)`, etc.

6. **f-string backslash restriction (pre-Python 3.12)** — dict key lookups inside f-strings (`f"{d['key']}"`) cause SyntaxError. Always extract to a local variable first.

7. **`esc(v)`** — always wrap user-facing strings in `esc()` before embedding in HTML (defined in model.py, imported by html.py).

8. **Briefing UI validation** — after editing `src/fdb/html.py`, `res/briefing.css`, or `res/briefing.js`, run `python3 -m py_compile src/fdb/html.py`, `node --check res/briefing.js`, and `python3 run_briefing.py`. The generated preview target is `output/Daily Briefing.html`.

9. **Inline style discipline** — prefer existing utility classes and state components for repeated layout, muted text, table-empty states, and loading/error UI. Leave one-off dynamic colors, calculated widths, and canvas/chart dimensions inline when moving them would increase risk.

---

## Dependency Notes

- `espn-api` — `espn_api.baseball.League` is the main object; `league.teams` is a list of `Team` objects each with `.roster` (list of `Player`)
- `pybaseball` — optional; `PYBASEBALL_AVAILABLE` flag in settings gates usage; falls back to FanGraphs CSV download
- `requests-cache` — SQLite cache for all ESPN API calls; configured in settings.py at import time
- `statsapi` (MLB Stats API) — no pip install needed; uses raw `urllib.request` GET calls via `_mlb_get()`

---

## GitHub / CI

- Repo target: public GitHub (not yet pushed as of last session)
- CI: `.github/workflows/ci.yml` — matrix Python 3.10 / 3.11 / 3.12, runs `pytest test/` with coverage
- Community files: README, CHANGELOG, CONTRIBUTING, CODE_OF_CONDUCT, issue templates, PR template all in place

---

## Changelog (recent sessions)

| Date | Change |
|---|---|
| 2026-05 | Staged briefing redesign completed: semantic shell, accessibility pass, token cleanup, nav/card/typography polish, emoji reduction, loading/empty/error state components, and focused inline style reduction |
| 2026-05 | Tab nav restructured: 10 tabs → 4 (Today, My Team, Tools, ⋯ More) |
| 2026-05 | Weekly Pitcher Streaming Plan feature added (model.py + html.py) |
| 2026-05 | Full code review: 8 bugs fixed, ~900 lines dead code removed, utils.py created |
| 2026-05 | Open-source repo template: tests, CI, community files, Run.command |

---

*Last updated: 2026-05-04*
