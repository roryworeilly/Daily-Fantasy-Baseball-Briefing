# Fantasy Baseball Daily Briefing (FDB)

> Wake up to a personalised ESPN fantasy baseball briefing — advanced Statcast metrics, projection blending, roster optimisation, and matchup analysis, all in one auto-generated HTML report.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

## Features

- **Daily HTML Briefing** — A single self-contained HTML report delivered each morning covering your entire league situation.
- **Lineup Lab** — Start/sit recommendations driven by projected points, matchup splits, and park factors.
- **Waiver Wire Analysis** — Ranked free-agent targets with replacement-level context and league-wide availability.
- **Statcast Signals** — Exit velocity, barrel%, sprint speed, xwOBA, and xERA breakout/regression flags keyed to MLBAM IDs.
- **Projection Blending** — Steamer and ZiPS consensus projections merged with in-season performance for stable forward estimates.
- **Season Simulation** — Monte-Carlo standings projections showing your realistic range of final-week outcomes.
- **Trade Target Identification** — Players whose Statcast profile outpaces their ESPN roster status, surfaced as buy-low candidates.
- **Two-Start Pitcher Tracking** — Automatic detection of pitchers with two starts in the upcoming week, flagged with matchup quality.
- **Custom Scoring Support** — Full configurable roto/points scoring (batting and pitching) defined in `src/fdb/settings.py`.
- **Smart Cache Management** — JSON caches for Statcast, projections, and player reference data with configurable TTLs and auto-rebuild.

---

## Requirements

- **Python 3.10+**
- An **ESPN Fantasy Baseball** league (public or private)
- [espn-api](https://github.com/cwendt94/espn-api) — ESPN fantasy API client
- [pybaseball](https://github.com/jldbc/pybaseball) *(optional)* — enables extended FanGraphs and Baseball Reference stats
- [requests-cache](https://requests-cache.readthedocs.io/) *(optional)* — SQLite-backed HTTP cache reducing ESPN API calls

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-username/FB.git
cd FB

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r dep/requirements.txt

# 4. Configure credentials
cp .env.example .env
# Open .env and fill in your ESPN credentials (see Configuration below)

# 5. Run the briefing
python run_briefing.py
```

The generated HTML report opens automatically (or is written to the `output/` directory).

---

## Configuration

Copy `.env.example` to `.env` and populate the following variables:

| Variable | Required | Description |
|---|---|---|
| `LEAGUE_ID` | Yes | Your ESPN fantasy league ID (visible in the league URL) |
| `YEAR` | Yes | The current season year (e.g. `2026`) |
| `MY_TEAM_NAME` | Yes | The exact name of your team in ESPN — used to personalise the report |
| `N_TEAMS` | Yes | Total number of teams in your league |
| `ESPN_SWID` | Private leagues | The `SWID` cookie from `fantasy.espn.com` |
| `ESPN_S2` | Private leagues | The `espn_s2` cookie from `fantasy.espn.com` |

**Finding your ESPN cookies:**

1. Log in to ESPN Fantasy in your browser.
2. Open DevTools → **Application** → **Cookies** → `fantasy.espn.com`.
3. Copy the values for `SWID` and `ESPN_S2` into your `.env` file.

> **Security note:** `.env` is listed in `.gitignore` and should never be committed.

---

## Project Structure

```
FB/
├── run_briefing.py          # Entry point — run this to generate the briefing
├── .env.example             # Template for ESPN credentials
├── .env                     # Your credentials (gitignored)
│
├── src/
│   └── fdb/                 # Core application package
│       ├── __init__.py
│       ├── run.py           # Pipeline orchestration
│       ├── model.py         # Scoring model, cache loading, market context
│       ├── html.py          # HTML report renderer
│       ├── settings.py      # Scoring rules, slots, thresholds, DB paths
│       ├── simulate.py      # Monte-Carlo season simulation
│       ├── assets.py        # Static asset embedding
│       └── utils.py         # Shared utility functions
│
├── tools/                   # Standalone cache-building scripts
│   ├── build_statcast_cache.py      # Fetches Statcast data via pybaseball
│   ├── build_projection_cache.py    # Blends Steamer + ZiPS projections
│   └── build_reference_cache.py     # Builds MLBAM player reference index
│
├── res/                     # Static web assets bundled into the HTML report
│   ├── briefing.css
│   └── briefing.js
│
├── scripts/                 # Developer and maintenance utilities
│   ├── extract_ui_assets.py
│   └── generate_fdb_package.py
│
├── output/                  # Generated HTML briefings (gitignored)
│
├── dep/                     # Dependency manifests
│   ├── requirements.txt
│   └── requirements-dev.txt
│
├── config/                  # Optional per-machine configuration overrides
│
├── samples/                 # Example output files for documentation/testing
│
├── .build/                  # Build artefacts (gitignored)
│
├── doc/                     # Extended documentation
│
└── .github/
    ├── workflows/
    │   └── ci.yml           # GitHub Actions CI
    └── ISSUE_TEMPLATE/
        ├── bug_report.md
        └── feature_request.md
```

---

## Cache Files

FDB maintains several JSON caches in the project root to avoid re-fetching slow external APIs on every run. They are automatically rebuilt when stale (default TTL: 7 days).

| File | Contents | Rebuilt by |
|---|---|---|
| `statcast_cache.json` | Per-player Statcast metrics (xwOBA, xERA, barrel%, exit velocity, sprint speed, breakout/regression signal) | `tools/build_statcast_cache.py` |
| `projection_cache.json` | Steamer + ZiPS consensus projections keyed by normalised player name | `tools/build_projection_cache.py` |
| `player_reference_cache.json` | MLBAM ID ↔ player name cross-reference | `tools/build_reference_cache.py` |
| `current_season_cache.json` | In-season cumulative stats | Auto-rebuilt by `run.py` |
| `espn_cache.sqlite` | Short-lived SQLite cache for ESPN API HTTP responses (10-minute TTL) | `requests-cache` |

To force a full cache rebuild:

```bash
python tools/build_statcast_cache.py --force
python tools/build_projection_cache.py --force
python tools/build_reference_cache.py --force
```

---

## Development

### Install dev dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r dep/requirements.txt -r dep/requirements-dev.txt
```

### Run the test suite

```bash
pytest test/ -v
```

### Run with coverage

```bash
pytest test/ --cov=src/fdb --cov-report=term-missing
```

### Rebuild all caches manually

```bash
python tools/build_reference_cache.py
python tools/build_statcast_cache.py
python tools/build_projection_cache.py
```

### Scoring rules

Batting and pitching scoring weights live in `src/fdb/settings.py` as `BATTING_SCORING` and `PITCHING_SCORING` dictionaries. Roster slot counts are in `SLOTS_PER_TEAM`. Edit these to match your league's settings.

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

For bug reports and feature requests, use the [GitHub Issues](../../issues) templates.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
