# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Additional Statcast metrics (whiff rate, chase rate, spin rate trends)
- Multi-league support
- Web dashboard mode (serve the briefing over localhost)
- Customisable report sections via config flags

---

## [1.0.0] - 2026-04-29

### Added
- **Daily HTML Briefing** — fully self-contained single-file HTML report generated each morning covering matchup scoring, roster status, and league context
- **Lineup Lab** — start/sit recommendations combining weekly projected points, matchup splits, park factors, and positional scarcity multipliers
- **Waiver Wire Analysis** — ranked free-agent targets with replacement-level context, injury status, and recent trend arrows
- **Statcast Signal Engine** — per-player breakout/regression flags derived from exit velocity, barrel%, xwOBA, xERA, sprint speed, and whiff rate via pybaseball
- **Projection Blending** — Steamer + ZiPS consensus projections merged with in-season rolling stats using a week-weighted blend that shifts toward actuals as the season progresses
- **Season Simulation** — Monte-Carlo standings simulation (configurable iterations) producing playoff probability distributions and realistic final-week outcome ranges
- **Trade Target Identification** — surfaces buy-low and sell-high candidates whose Statcast profile diverges meaningfully from their current ESPN roster cost
- **Two-Start Pitcher Tracker** — automatic detection of SP with two starts in the upcoming scoring week, annotated with matchup quality scores
- **Win Probability Engine** — per-matchup win probability using weekly projected points vs. live running scores
- **Custom Scoring** — fully configurable roto/points weights for batting (`BATTING_SCORING`) and pitching (`PITCHING_SCORING`) in `src/fdb/settings.py`
- **Smart Cache System** — JSON caches for Statcast, projections, and player reference data with configurable TTLs, auto-rebuild on staleness, and `--force` flag override
- **`src/fdb/utils.py`** — shared `normalize_name`, `compact`, `get_metric`, `cache_is_fresh` helpers extracted from duplicated tool code
- **`dep/requirements.txt`** and **`dep/requirements-dev.txt`** — explicit dependency manifests
- **GitHub Actions CI** — unit test workflow running on every push and pull request
- Full open-source project structure: `src/`, `test/`, `doc/`, `res/`, `tools/`, `.build/`, `dep/`, `config/`, `samples/`

### Fixed
- Tie handling in `simulate.py` — ESPN awards 0.5 wins and **0 losses** per tie (was incorrectly 0.5 losses, inflating playoff probabilities)
- `_velocity_alert()` pitcher branch checked for `"BREAKOUT_CANDIDATE"` signal which pitchers never emit; corrected to `"BUY_LOW"` / `"SELL_HIGH"`
- xERA gap buy/sell direction was inverted — positive `xERA_gap` (xERA > ERA) now correctly triggers a regression/sell flag
- `get_scarcity_multiplier()` in `build_lineup_lab()` received a player name string instead of an ESPN player object, causing scarcity to always silently return 1.0
- Duplicate `fetch_todays_mlb_schedule()` API call in `build_payload()` removed
- `win_probability()` now uses weekly projected points (`best_lineup_pts(weekly=True)`) rather than season totals
- `calc_fdb_pit()` holds fallback was `stats.get("HLD", stats.get("BS", 0))` — blown saves were being credited as holds; fixed to `stats.get("HLD", 0)`
- `YEAR` hardcoded to `2026` in `build_reference_cache.py`; now reads from `$YEAR` environment variable with current year as default
- `json.load(open(...))` file handle in `build_projection_cache.py` now uses a `with` context manager

### Removed
- Dead two-start season tracker subsystem (`update_season_twostart_tracker`, `get_season_twostart_weeks`, `get_season_total_starts`, `_load_season_tsc`, `_save_season_tsc`, and associated module globals)
- Dead `_reconcile_roster()` and `_sync_my_team_roster()` functions
- Unused `import io` in `model.py`; unused `import io / math / re / hashlib / subprocess` leaking from `settings.py` via `import *`
- Dead `_fetch_fg_projection_csv` backward-compat alias in `build_projection_cache.py`
- Dead `sim_js` variable computed and discarded in `_how_it_works_tab()` (~258 lines)
- Dead inner functions `_sos_row()` and `_standing_row()` (the latter containing a latent `NameError`) superseded by corrected `_v2` versions
- `legacy/fdbRV_separated.py` — referenced a non-existent `fdbRV.py` and would always crash on import

---

[Unreleased]: https://github.com/your-username/FB/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/your-username/FB/releases/tag/v1.0.0
