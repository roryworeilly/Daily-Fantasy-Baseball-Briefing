# Contributing to Fantasy Baseball Daily Briefing

Thank you for your interest in contributing! This document covers everything you need to get started.

---

## Table of Contents

1. [Setting Up the Development Environment](#1-setting-up-the-development-environment)
2. [Project Structure](#2-project-structure)
3. [Coding Standards](#3-coding-standards)
4. [Running the Test Suite](#4-running-the-test-suite)
5. [Reporting Bugs](#5-reporting-bugs)
6. [Submitting a Pull Request](#6-submitting-a-pull-request)
7. [Scoring Rules and League Config](#7-scoring-rules-and-league-config)

---

## 1. Setting Up the Development Environment

```bash
# Clone and enter the repo
git clone https://github.com/your-username/FB.git
cd FB

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install runtime + dev dependencies
pip install -r dep/requirements.txt -r dep/requirements-dev.txt

# Set up credentials (needed for integration / manual testing only)
cp .env.example .env
# Fill in LEAGUE_ID, MY_TEAM_NAME, ESPN_SWID, ESPN_S2 in .env
```

> **Note:** ESPN credentials are only required to run the full pipeline (`python run_briefing.py`). The unit test suite in `test/` runs entirely without them.

---

## 2. Project Structure

```
src/fdb/          Core application package (model, html, simulate, settings, utils)
tools/            Standalone cache-building scripts (run independently)
test/             Pytest unit tests
res/              Static CSS/JS assets embedded in the HTML report
.build/           Developer utilities (asset extraction, package generation)
dep/              Dependency manifests (requirements.txt, requirements-dev.txt)
config/           macOS automation scripts and LaunchAgent plist
doc/              Extended design documentation and roadmaps
samples/          Example generated output
output/           Live generated briefings (gitignored)
```

---

## 3. Coding Standards

- **Style:** [PEP 8](https://peps.python.org/pep-0008/). Run `flake8 src/ tools/ test/` to lint before committing.
- **Type hints:** Encouraged on all new public functions — `def foo(name: str) -> float:`.
- **Docstrings:** One-line summary for simple functions; full Google-style docstring for anything with non-obvious parameters or side effects.
- **No secrets in code:** All credentials must come from the `.env` file. Never hard-code `LEAGUE_ID`, `SWID`, or `ESPN_S2`.
- **Shared helpers:** If you find yourself copying a utility function from one tool to another, add it to `src/fdb/utils.py` instead.
- **Cache paths:** All cache file paths must be derived from `SCRIPT_DIR` (defined in `src/fdb/settings.py`), not hard-coded absolute paths.

---

## 4. Running the Test Suite

```bash
# Run all unit tests
pytest test/ -v

# Run with coverage report
pytest test/ --cov=src/fdb --cov-report=term-missing

# Run a single test file
pytest test/test_utils.py -v
```

All tests must pass before a PR will be merged. If you are adding a new feature, please include at least one test covering the happy path and one covering an edge case.

---

## 5. Reporting Bugs

Please use the [Bug Report issue template](../../issues/new?template=bug_report.md). Include:

- A clear description of the unexpected behaviour
- Steps to reproduce (Python version, OS, which script you ran)
- The full error traceback from the console
- Your `espn-api` version (`pip show espn-api`)

> Do **not** include your `.env` contents or ESPN cookie values in a bug report.

---

## 6. Submitting a Pull Request

1. **Fork** the repository and create a feature branch from `main`:
   ```bash
   git checkout -b feat/my-improvement
   ```

2. **Make your changes.** Keep commits focused — one logical change per commit.

3. **Add or update tests** in `test/` covering your change.

4. **Ensure all tests pass:**
   ```bash
   pytest test/ -v
   ```

5. **Update `CHANGELOG.md`** — add a line under `## [Unreleased]` describing your change.

6. **Open the PR** against `main`. Fill in the pull request template completely.

A maintainer will review your PR typically within a few days. Please be patient and responsive to feedback.

---

## 7. Scoring Rules and League Config

Fantasy scoring weights are defined in `src/fdb/settings.py` as two dictionaries:

- `BATTING_SCORING` — maps stat keys (e.g. `"HR"`, `"RBI"`, `"SB"`) to point values
- `PITCHING_SCORING` — maps stat keys (e.g. `"W"`, `"SO"`, `"ERA"`) to point values

Roster slot configuration is in `SLOTS_PER_TEAM`. If your league uses non-standard scoring, edit these dictionaries and all model calculations will update automatically — no changes needed elsewhere.
