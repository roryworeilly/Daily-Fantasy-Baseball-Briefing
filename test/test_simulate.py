"""
Unit tests for src/fdb/simulate.py

Focuses on the core simulation logic, particularly the tie-handling bug
that was fixed: ESPN awards 0.5 wins + 0 losses per tie (not 0.5 losses).
"""
import random
import pytest

# Import the pure helper functions directly — they don't touch ESPN.
# The fdb.settings and fdb.model stubs are set up in conftest.py.
from fdb.simulate import (
    _draw_weekly_score,
    _simulate_once,
    _rank_teams,
)


# ══════════════════════════════════════════════════════════════════════════════
# _draw_weekly_score
# ══════════════════════════════════════════════════════════════════════════════

class TestDrawWeeklyScore:
    def test_positive_mu_returns_positive_score(self):
        rng = random.Random(42)
        for _ in range(50):
            score = _draw_weekly_score(100.0, rng)
            assert score >= 0.0

    def test_zero_mu_returns_zero(self):
        rng = random.Random(0)
        assert _draw_weekly_score(0.0, rng) == 0.0

    def test_negative_mu_returns_zero(self):
        rng = random.Random(0)
        assert _draw_weekly_score(-50.0, rng) == 0.0

    def test_score_is_float(self):
        rng = random.Random(1)
        score = _draw_weekly_score(80.0, rng)
        assert isinstance(score, float)

    def test_scores_vary(self):
        """Verify the normal distribution produces different values."""
        rng = random.Random(99)
        scores = {_draw_weekly_score(100.0, rng) for _ in range(20)}
        assert len(scores) > 1


# ══════════════════════════════════════════════════════════════════════════════
# _simulate_once — tie handling (regression test for the ESPN rule fix)
# ══════════════════════════════════════════════════════════════════════════════

class TestSimulateOnceTieHandling:
    """
    ESPN awards 0.5 wins + 0 losses per tie.
    A tie must NOT add 0.5 to the losses column.
    """

    def _make_profiles(self, mu_a, mu_b):
        return {
            "Team A": {"mu": mu_a, "wins": 0, "losses": 0, "pts": 0.0},
            "Team B": {"mu": mu_b, "wins": 0, "losses": 0, "pts": 0.0},
        }

    def test_winner_gets_one_win_no_loss(self):
        # Team A is much stronger — should win reliably
        profiles = self._make_profiles(200.0, 10.0)
        schedule = {1: [("Team A", "Team B")]}
        rng = random.Random(0)
        result = _simulate_once(profiles, schedule, current_week=1, rng=rng)
        total_wins = result["Team A"]["wins"] + result["Team B"]["wins"]
        total_losses = result["Team A"]["losses"] + result["Team B"]["losses"]
        assert total_wins == 1.0
        assert total_losses == 1.0  # one win + one loss for a decisive result

    def test_tie_gives_half_win_and_zero_losses(self):
        """
        Force a tie by using a deterministic RNG that produces identical scores.
        We patch _draw_weekly_score to return a constant.
        """
        import fdb.simulate as sim_mod
        original = sim_mod._draw_weekly_score

        sim_mod._draw_weekly_score = lambda mu, rng: 100.0  # always tie

        profiles = self._make_profiles(100.0, 100.0)
        schedule = {1: [("Team A", "Team B")]}
        rng = random.Random(0)
        result = _simulate_once(profiles, schedule, current_week=1, rng=rng)

        sim_mod._draw_weekly_score = original  # restore

        assert result["Team A"]["wins"] == 0.5, "Tie should give 0.5 wins"
        assert result["Team B"]["wins"] == 0.5, "Tie should give 0.5 wins"
        assert result["Team A"]["losses"] == 0.0, "Tie must NOT add losses"
        assert result["Team B"]["losses"] == 0.0, "Tie must NOT add losses"

    def test_total_wins_equals_games_played(self):
        """Sum of all wins across teams must equal number of games played."""
        profiles = self._make_profiles(100.0, 80.0)
        schedule = {1: [("Team A", "Team B")], 2: [("Team A", "Team B")]}
        rng = random.Random(7)
        result = _simulate_once(profiles, schedule, current_week=1, rng=rng)
        total_wins = result["Team A"]["wins"] + result["Team B"]["wins"]
        assert total_wins == pytest.approx(2.0)

    def test_past_week_is_skipped(self):
        """Weeks before current_week should not be simulated."""
        profiles = self._make_profiles(100.0, 100.0)
        schedule = {1: [("Team A", "Team B")]}  # week 1 is in the past
        rng = random.Random(0)
        result = _simulate_once(profiles, schedule, current_week=2, rng=rng)
        assert result["Team A"]["wins"] == 0.0
        assert result["Team B"]["wins"] == 0.0
        assert result["Team A"]["losses"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# _rank_teams
# ══════════════════════════════════════════════════════════════════════════════

class TestRankTeams:
    def test_higher_wins_ranks_first(self):
        results = {
            "Alpha": {"wins": 10, "pts": 500.0},
            "Beta": {"wins": 5, "pts": 600.0},
        }
        ranks = _rank_teams(results)
        assert ranks["Alpha"] == 1
        assert ranks["Beta"] == 2

    def test_pts_breaks_wins_tie(self):
        results = {
            "Alpha": {"wins": 8, "pts": 400.0},
            "Beta": {"wins": 8, "pts": 500.0},
        }
        ranks = _rank_teams(results)
        assert ranks["Beta"] == 1
        assert ranks["Alpha"] == 2

    def test_all_teams_get_a_rank(self):
        results = {f"Team{i}": {"wins": i, "pts": float(i * 10)} for i in range(10)}
        ranks = _rank_teams(results)
        assert set(ranks.values()) == set(range(1, 11))

    def test_single_team(self):
        results = {"Solo": {"wins": 5, "pts": 300.0}}
        ranks = _rank_teams(results)
        assert ranks["Solo"] == 1
