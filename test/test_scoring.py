"""
Unit tests for the FDB fantasy-point scoring formulas.

Covers calc_fdb_bat / calc_fdb_pit from tools/model_comparison.py,
including a regression test for the holds/blown-saves fallback bug that
was fixed: stats.get("HLD", stats.get("BS", 0)) incorrectly credited
blown saves as holds.
"""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
model_comparison = importlib.import_module("model_comparison")
calc_fdb_bat = model_comparison.calc_fdb_bat
calc_fdb_pit = model_comparison.calc_fdb_pit


# ══════════════════════════════════════════════════════════════════════════════
# calc_fdb_bat  —  R + HR + TB + RBI + BB + SB - K
# ══════════════════════════════════════════════════════════════════════════════

class TestCalcFdbBat:
    def test_zero_stats_give_zero(self):
        assert calc_fdb_bat({}) == pytest.approx(0.0)

    def test_single_home_run(self):
        # HR=1 contributes: 4 TB (1B+1B+1B+HR) counted via h+d+t*2+hr*3
        # H=1, HR=1 → tb = 1 + 0 + 0 + 3 = 4; score = 0+1+4+0+0+0-0 = 5
        stats = {"H": 1, "HR": 1}
        score = calc_fdb_bat(stats)
        assert score == pytest.approx(5.0)

    def test_strikeouts_penalise(self):
        stats = {"SO": 5}
        assert calc_fdb_bat(stats) == pytest.approx(-5.0)

    def test_k_alias_works(self):
        """SO and K keys should both be recognised for strikeouts."""
        assert calc_fdb_bat({"SO": 3}) == calc_fdb_bat({"K": 3})

    def test_stolen_bases(self):
        stats = {"SB": 3, "R": 3, "RBI": 3, "BB": 1}
        # R=3, SB=3, RBI=3, BB=1, TB=0, K=0 → 3+3+3+1 = 10
        assert calc_fdb_bat(stats) == pytest.approx(10.0)

    def test_known_season_line(self):
        """
        Shohei Ohtani 2023 approximation.
        H=151, 2B=26, 3B=8, HR=44, R=102, RBI=95, BB=91, SB=20, K=143
        TB = 151 + 26 + 8*2 + 44*3 = 151+26+16+132 = 325
        score = 102 + 44 + 325 + 95 + 91 + 20 - 143 = 534
        """
        stats = {
            "H": 151, "2B": 26, "3B": 8, "HR": 44,
            "R": 102, "RBI": 95, "BB": 91, "SB": 20, "SO": 143,
        }
        assert calc_fdb_bat(stats) == pytest.approx(534.0)

    def test_none_values_treated_as_zero(self):
        stats = {"HR": None, "R": 5}
        assert calc_fdb_bat(stats) == pytest.approx(5.0)


# ══════════════════════════════════════════════════════════════════════════════
# calc_fdb_pit  —  IP*3 + K - H - ER*2 - HR - BB + W*2 - L*2 + SV*6 + HD*5 + QS*2
# ══════════════════════════════════════════════════════════════════════════════

class TestCalcFdbPit:
    def test_zero_stats_give_zero(self):
        assert calc_fdb_pit({}) == pytest.approx(0.0)

    def test_innings_pitched(self):
        stats = {"IP": 6.0}
        assert calc_fdb_pit(stats) == pytest.approx(18.0)

    def test_win_adds_points(self):
        stats = {"W": 1}
        assert calc_fdb_pit(stats) == pytest.approx(2.0)

    def test_loss_subtracts_points(self):
        stats = {"L": 1}
        assert calc_fdb_pit(stats) == pytest.approx(-2.0)

    def test_save_value(self):
        stats = {"SV": 1}
        assert calc_fdb_pit(stats) == pytest.approx(6.0)

    def test_hold_value(self):
        stats = {"HLD": 1}
        assert calc_fdb_pit(stats) == pytest.approx(5.0)

    def test_quality_start_value(self):
        stats = {"QS": 1}
        assert calc_fdb_pit(stats) == pytest.approx(2.0)

    # ── Regression test: holds/blown-saves bug (fixed 2026-04-29) ─────────────
    def test_holds_fallback_does_not_use_blown_saves(self):
        """
        BUG: stats.get("HLD", stats.get("BS", 0)) used blown saves as a
        fallback for holds.  A pitcher with 5 BS and 0 HLD was credited 5 holds.
        FIX: stats.get("HLD", 0) — BS should never count as holds.
        """
        stats_bs_only = {"IP": 10.0, "BS": 5}  # 5 blown saves, 0 holds
        stats_hld = {"IP": 10.0, "HLD": 5}  # 5 holds, 0 blown saves

        score_bs = calc_fdb_pit(stats_bs_only)
        score_hld = calc_fdb_pit(stats_hld)

        # Blown saves should NOT be scored as holds
        assert score_bs != score_hld, (
            "Blown saves must not be credited as holds"
        )
        # Specifically: BS brings no hold points (only the IP contributes)
        assert score_bs == pytest.approx(30.0), (
            "10 IP × 3 = 30; BS alone should not add hold points"
        )
        # HLD=5 adds 5×5=25 hold points on top of 30 IP points
        assert score_hld == pytest.approx(55.0)

    def test_so_and_k_aliases_equivalent(self):
        """SO and K keys should both be recognised for strikeouts."""
        assert calc_fdb_pit({"SO": 10}) == calc_fdb_pit({"K": 10})

    def test_era_does_not_directly_appear(self):
        """ERA is a ratio stat — calc_fdb_pit uses counting stats only."""
        stats_with_era = {"IP": 9.0, "ERA": 1.50}
        stats_without_era = {"IP": 9.0}
        # ERA should have no effect on the raw points formula
        assert calc_fdb_pit(stats_with_era) == calc_fdb_pit(stats_without_era)

    def test_known_ace_line(self):
        """
        Gerrit Cole 2023 approximation.
        IP=209, H=145, ER=52, HR=18, BB=43, K=222, W=15, L=4, QS=22
        score = 209*3 + 222 - 145 - 52*2 - 18 - 43 + 15*2 - 4*2 + 22*2
              = 627 + 222 - 145 - 104 - 18 - 43 + 30 - 8 + 44 = 605
        """
        stats = {
            "IP": 209, "H": 145, "ER": 52, "HR": 18, "BB": 43,
            "SO": 222, "W": 15, "L": 4, "QS": 22,
        }
        assert calc_fdb_pit(stats) == pytest.approx(605.0)
