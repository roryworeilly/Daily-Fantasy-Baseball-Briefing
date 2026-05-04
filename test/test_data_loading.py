"""
Regression tests for cache loading and Statcast name extraction.
"""
import json
import os
from types import SimpleNamespace

import fdb.model as model
from build_statcast_cache import _player_name


class TestStatcastPlayerName:
    def test_reads_player_name_last_first(self):
        row = {"player_name": "Judge, Aaron"}
        assert _player_name(row) == "Aaron Judge"

    def test_reads_display_name_variants(self):
        row = {"name_display_first_last": "Shohei Ohtani"}
        assert _player_name(row) == "Shohei Ohtani"

    def test_reads_split_first_last_columns(self):
        row = {"first_name": "Mookie", "last_name": "Betts"}
        assert _player_name(row) == "Mookie Betts"


class TestStatcastCacheLoad:
    def test_load_statcast_db_builds_name_index(self, monkeypatch, tmp_path):
        cache_path = tmp_path / "statcast_cache.json"
        cache_path.write_text(json.dumps({
            "season": 2025,
            "built_at": "2026-05-04T00:00:00Z",
            "batters": {
                "592450": {"name": "Mookie Betts", "xwOBA": 0.4},
            },
            "pitchers": {
                "605135": {"name": "Gerrit Cole", "xERA": 3.1},
            },
        }))

        monkeypatch.setattr(model, "STATCAST_DB_PATH", str(cache_path))
        monkeypatch.setattr(model, "STATCAST_DB", {
            "season": None,
            "built_at": None,
            "batters": {},
            "pitchers": {},
            "loaded": False,
        })
        monkeypatch.setattr(model, "_SC_NAME_TO_MLBAM", {})

        model.load_statcast_db()

        player = SimpleNamespace(name="Mookie Betts")
        assert model.get_statcast_name_index_size() == 2
        assert model.get_mlbam_id(player) == "592450"


class TestCurrentSeasonStaleFallback:
    def test_load_current_season_db_uses_stale_cache_when_refresh_fails(self, monkeypatch, tmp_path):
        cache_path = tmp_path / "current_season_cache.json"
        cache_payload = {
            "season": model.YEAR,
            "built_at": "2026-05-02T00:00:00Z",
            "sources": {"hitters": "MLB Stats API", "pitchers": "MLB Stats API"},
            "hitters": {"aaron judge": {"HR": 10}},
            "pitchers": {"tarik skubal": {"SO": 50}},
        }
        cache_path.write_text(json.dumps(cache_payload))

        stale_time = 1_700_000_000
        os.utime(cache_path, (stale_time, stale_time))

        monkeypatch.setattr(model, "_CURRENT_SEASON_DB_PATH", str(cache_path))
        monkeypatch.setattr(model, "_CURRENT_SEASON_DB", {
            "season": None,
            "built_at": None,
            "hitters": {},
            "pitchers": {},
            "loaded": False,
        })
        monkeypatch.setattr(model, "PYBASEBALL_AVAILABLE", False)

        import requests

        def _boom(*args, **kwargs):
            raise requests.ConnectionError("offline for test")

        monkeypatch.setattr(requests, "get", _boom)

        model.load_current_season_db()

        assert model._CURRENT_SEASON_DB["loaded"] is True
        assert model._CURRENT_SEASON_DB["hitters"]["aaron judge"]["HR"] == 10
        assert model._CURRENT_SEASON_DB["pitchers"]["tarik skubal"]["SO"] == 50
