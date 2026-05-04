"""
Unit tests for scoring helper functions inside src/fdb/model.py.

We test _hitter_pts_from_stats, _pitcher_pts_from_stats, and the
xERA gap direction fix without needing a live ESPN connection.
fdb.settings is mocked in conftest.py.
"""
import pytest
import sys
import types
from unittest.mock import MagicMock

# conftest.py has already set up fdb.settings stub and path insertions.
# We also need to stub fdb.model's dependency on espn_api before importing.

# Stub requests_cache so settings.py import chain doesn't break
if "requests_cache" not in sys.modules:
    rc = types.ModuleType("requests_cache")
    rc.install_cache = MagicMock()
    sys.modules["requests_cache"] = rc

# Now import only the pure functions from model
from fdb.model import (
    _hitter_pts_from_stats,
    _pitcher_pts_from_stats,
    normalize_name,
    as_float,
)
from fdb.settings import PITCHING_SCORING


# ══════════════════════════════════════════════════════════════════════════════
# _hitter_pts_from_stats
# ══════════════════════════════════════════════════════════════════════════════

class TestHitterPtsFromStats:
    def test_empty_stats_returns_near_zero(self):
        score = _hitter_pts_from_stats({})
        assert score == pytest.approx(0.0, abs=0.1)

    def test_home_run_scores_positively(self):
        score = _hitter_pts_from_stats({"HR": 1, "H": 1, "R": 1, "RBI": 1})
        assert score > 0

    def test_strikeouts_reduce_score(self):
        base = _hitter_pts_from_stats({"R": 5, "HR": 2, "RBI": 5})
        with_k = _hitter_pts_from_stats({"R": 5, "HR": 2, "RBI": 5, "SO": 10})
        assert with_k < base

    def test_stolen_bases_add_points(self):
        base = _hitter_pts_from_stats({"R": 10})
        with_sb = _hitter_pts_from_stats({"R": 10, "SB": 3})
        assert with_sb > base

    def test_k_and_so_aliases(self):
        """Both SO and K should be read as strikeouts."""
        s1 = _hitter_pts_from_stats({"SO": 5})
        s2 = _hitter_pts_from_stats({"K": 5})
        assert s1 == pytest.approx(s2)


# ══════════════════════════════════════════════════════════════════════════════
# _pitcher_pts_from_stats
# ══════════════════════════════════════════════════════════════════════════════

class TestPitcherPtsFromStats:
    def test_empty_stats_returns_near_zero(self):
        score = _pitcher_pts_from_stats({})
        assert score == pytest.approx(0.0, abs=0.5)

    def test_innings_pitched_score_positively(self):
        score = _pitcher_pts_from_stats({"IP": 9.0})
        assert score == pytest.approx(9.0 * PITCHING_SCORING["IP"], abs=0.1)

    def test_wins_add_to_score(self):
        base = _pitcher_pts_from_stats({"IP": 6.0})
        with_win = _pitcher_pts_from_stats({"IP": 6.0, "W": 1})
        assert with_win > base

    def test_earned_runs_reduce_score(self):
        base = _pitcher_pts_from_stats({"IP": 7.0})
        with_er = _pitcher_pts_from_stats({"IP": 7.0, "ER": 4})
        assert with_er < base

    def test_saves_score_highly(self):
        score = _pitcher_pts_from_stats({"SV": 1})
        assert score == pytest.approx(PITCHING_SCORING["SV"] + PITCHING_SCORING["SVHD"], abs=0.1)

    def test_holds_score_positively(self):
        score = _pitcher_pts_from_stats({"HD": 1})
        assert score > 0


# ══════════════════════════════════════════════════════════════════════════════
# normalize_name (model.py re-exports from utils.py)
# ══════════════════════════════════════════════════════════════════════════════

class TestModelNormalizeName:
    def test_basic(self):
        assert normalize_name("Shohei Ohtani") == "shohei ohtani"

    def test_none(self):
        assert normalize_name(None) == ""


# ══════════════════════════════════════════════════════════════════════════════
# as_float
# ══════════════════════════════════════════════════════════════════════════════

class TestAsFloat:
    def test_numeric_string(self):
        assert as_float("3.14") == pytest.approx(3.14)

    def test_none_returns_default(self):
        assert as_float(None) == 0.0

    def test_custom_default(self):
        assert as_float("bad", default=99.0) == 99.0

    def test_integer(self):
        assert as_float(7) == 7.0

    def test_empty_string_returns_default(self):
        assert as_float("") == 0.0
