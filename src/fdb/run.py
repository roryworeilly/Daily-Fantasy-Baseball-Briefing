"""
Entry: run briefing using split fdb/ package.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
import pickle
import sqlite3
import subprocess
import traceback

from fdb.html import render_html
from fdb.model import (
    build_market_context,
    build_payload,
    build_score_scaling,
    connect,
    load_reference_db,
    load_statcast_db,
    load_projection_db,
    load_current_season_db,
)
from fdb.settings import SCRIPT_DIR

# ── Cache TTLs (days) — must match the tool scripts ──────────────────────────
_STATCAST_CACHE   = os.path.join(SCRIPT_DIR, "statcast_cache.json")
_PROJECTION_CACHE = os.path.join(SCRIPT_DIR, "projection_cache.json")
_REFERENCE_CACHE  = os.path.join(SCRIPT_DIR, "player_reference_cache.json")
_CACHE_TTL_DAYS   = 7


def _cache_age_days(path: str) -> float:
    """Return the age of a cache file in days, or infinity if it doesn't exist."""
    if not os.path.exists(path):
        return float("inf")
    return (time.time() - os.path.getmtime(path)) / 86400


def _auto_rebuild_cache(
    tool_module_name: str,
    cache_path: str,
    rebuild_fn_name: str,
    max_age_hours: float = _CACHE_TTL_DAYS * 24,
    force: bool = False,
) -> None:
    """
    Generic cache rebuilder.  Loads *tool_module_name* from the tools/ directory
    and calls ``mod.<rebuild_fn_name>(force=force)``.  If *rebuild_fn_name* is
    the empty string the module's ``main()`` is called instead (legacy pattern).
    """
    max_age_days = max_age_hours / 24
    label = tool_module_name.replace("build_", "").replace("_cache", "").replace("_", " ").title()
    age = _cache_age_days(cache_path)
    if not force and age < max_age_days:
        print(f"  {label} cache: fresh ({age:.1f}d old) — skipping rebuild")
        return
    print(f"  {label} cache: {'missing' if age == float('inf') else f'{age:.1f}d old'} — rebuilding…")
    try:
        _tools = os.path.join(SCRIPT_DIR, "tools")
        if _tools not in sys.path:
            sys.path.insert(0, _tools)
        spec = importlib.util.spec_from_file_location(
            tool_module_name,
            os.path.join(_tools, f"{tool_module_name}.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if rebuild_fn_name:
            getattr(mod, rebuild_fn_name)(force=force)
        else:
            # Legacy modules that expose a top-level main() with no arguments
            sys.argv = [sys.argv[0]]
            mod.main()
    except Exception as exc:
        print(f"  {label} cache rebuild failed (non-fatal): {exc}")


def _purge_espn_fantasy_cache() -> None:
    """
    Delete all cached ESPN Fantasy API responses so roster changes, waiver
    claims, trades, and standings are always fetched live on every run.

    MLB stats entries (statsapi.mlb.com) are left intact — they change only
    once a day and are safe to serve from cache.

    Strategy: open the SQLite cache directly, unpickle each row just enough to
    read the URL, and DELETE any row whose URL contains 'fantasy.espn.com'.
    This is faster and more targeted than requests_cache.clear() which would
    wipe the MLB stats cache too.
    """
    cache_path = os.path.join(SCRIPT_DIR, "espn_cache.sqlite")
    if not os.path.exists(cache_path):
        return

    try:
        conn = sqlite3.connect(cache_path)
        rows = conn.execute("SELECT key, value FROM responses").fetchall()

        stale_keys = []
        for key, raw in rows:
            if raw is None:
                continue
            try:
                data = pickle.loads(raw)
                url = data.get("url", "")
            except Exception:
                url = ""
            if "fantasy.espn.com" in url:
                stale_keys.append((key,))

        if stale_keys:
            conn.executemany("DELETE FROM responses WHERE key = ?", stale_keys)
            conn.commit()
            print(f"  Cache: purged {len(stale_keys)} stale ESPN Fantasy entries "
                  f"— rosters and standings will be fetched live.")
        else:
            print("  Cache: no stale ESPN Fantasy entries found.")

        conn.close()
    except Exception as exc:
        # Non-fatal — a stale cache is better than crashing the whole run
        print(f"  Cache purge warning (non-fatal): {exc}")


def main() -> None:
    try:
        print("Purging stale ESPN Fantasy cache entries...")
        _purge_espn_fantasy_cache()

        # ── Auto-rebuild any stale or missing caches ──────────────────────────
        # Each check compares the cache file's mtime against its TTL.
        # A fresh cache is loaded instantly; a stale one is rebuilt in-process.
        # No manual tool runs ever needed.
        print("Checking Statcast cache (Phase 2 — auto-rebuild if > 7 days)...")
        _auto_rebuild_cache("build_statcast_cache", _STATCAST_CACHE, "", force=False)

        print("Checking projection cache (Phase 3 — auto-rebuild if > 7 days)...")
        _auto_rebuild_cache("build_projection_cache", _PROJECTION_CACHE, "build_projection_cache", force=False)

        print("Loading reference database...")
        load_reference_db()

        print("Loading Statcast cache (Phase 2 advanced metrics)...")
        load_statcast_db()

        print("Loading projection cache (Phase 3 — Steamer/ZiPS)...")
        load_projection_db()

        print("Loading live 2026 in-season stats (auto-refresh if > 12 hours)...")
        load_current_season_db()

        print("Connecting to ESPN...")
        league = connect()

        print("Building market context (replacement levels)...")
        build_market_context(league)

        print("Calibrating score scaling...")
        build_score_scaling(league)

        print("Assembling briefing data...")
        data = build_payload(league)

        html_out = render_html(data)
        out_dir = os.path.join(SCRIPT_DIR, "output")
        os.makedirs(out_dir, exist_ok=True)
        html_path = os.path.join(out_dir, "Daily Briefing.html")

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_out)

        print("Opening briefing...")
        subprocess.Popen(["open", html_path])

    except Exception as exc:
        print(f"\nError: {exc}")
        traceback.print_exc()
        print(
            "\nIf credentials expired, grab fresh SWID and ESPN_S2 from "
            "Edge DevTools -> Application -> Cookies."
        )


if __name__ == "__main__":
    main()
