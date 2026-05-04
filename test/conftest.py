"""
pytest configuration — mocks ESPN/pybaseball dependencies so all tests run
without credentials or network access.
"""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ── Ensure src/ and tools/ are importable ─────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tools"))

# ── Stub heavy third-party libs BEFORE any fdb.* import ───────────────────────

# requests_cache — installed as side-effect in settings.py
if "requests_cache" not in sys.modules:
    _rc = types.ModuleType("requests_cache")
    _rc.install_cache = MagicMock()
    sys.modules["requests_cache"] = _rc

# espn_api
for _mod in ("espn_api", "espn_api.baseball", "espn_api.baseball.player"):
    if _mod not in sys.modules:
        _m = types.ModuleType(_mod)
        sys.modules[_mod] = _m
sys.modules["espn_api.baseball.player"].Player = MagicMock

# pybaseball (optional in production, absent in CI)
for _mod in ("pybaseball",):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)
_pybaseball = sys.modules["pybaseball"]
_pybaseball.statcast_batter_expected_stats = MagicMock()
_pybaseball.statcast_batter_exitvelo_barrels = MagicMock()
_pybaseball.statcast_sprint_speed = MagicMock()
_pybaseball.statcast_pitcher_expected_stats = MagicMock()
_pybaseball.statcast_pitcher_exitvelo_barrels = MagicMock()

# dotenv — settings.py may try to import it
if "dotenv" not in sys.modules:
    _de = types.ModuleType("dotenv")
    _de.load_dotenv = MagicMock()
    sys.modules["dotenv"] = _de

# ── Pre-populate fdb.settings with safe stubs ─────────────────────────────────
# This must happen before any `from fdb.settings import ...` executes.

_BATTING_SCORING = {
    "R": 1, "HR": 4, "TB": 1, "RBI": 1, "BB": 1, "SB": 2,
    "K": -1, "GWRBI": 2, "GSHR": 3,
}
_PITCHING_SCORING = {
    "IP": 3, "H": -1, "ER": -2, "HR": -3, "BB": -1, "K": 1,
    "QS": 2, "W": 2, "L": -2, "SV": 6, "BS": -3, "HD": 5,
    "SVHD": 2, "CG": 5, "SO": 1,
}

_settings = types.ModuleType("fdb.settings")
_settings.MY_TEAM_NAME              = "Test Team"
_settings.N_TEAMS                   = 10
_settings.BATTING_SCORING           = _BATTING_SCORING
_settings.PITCHING_SCORING          = _PITCHING_SCORING
_settings.SLOTS_PER_TEAM            = {
    "C":1,"1B":1,"2B":1,"3B":1,"SS":1,"OF":3,"UTIL":1,
    "SP":2,"RP":2,"P":3,"BE":5,"IL":2,
}
_settings.SCRIPT_DIR                = str(REPO_ROOT)
_settings.LEAGUE_ID                 = 0
_settings.YEAR                      = 2026
_settings.SWID                      = ""
_settings.ESPN_S2                   = ""
_settings.REPLACEMENT_BUFFER        = 1.0
_settings.STASH_SCORE_THRESHOLD     = 5.0
_settings.SEASON_INTEL_FA_THRESHOLD = 10.0
_settings.SEASON_TREND_MIN_GAMES    = 10
_settings.SEASON_TREND_LOOKBACK     = 14
_settings.MARKET                    = {}
_settings.WEEKLY_STARTS             = {}
_settings.SCALING                   = {}
_settings.REFERENCE_DB_PATH        = ""
_settings.REFERENCE_DB             = {}
_settings.PROJECTION_DB_PATH       = ""
_settings.PROJECTION_DB            = {}
_settings.STATCAST_DB_PATH         = ""
_settings.STATCAST_DB              = {}
_settings.WEEKLY_IP_LIMIT          = 50
_settings.PYBASEBALL_AVAILABLE     = False
_settings.League                   = MagicMock()
_settings.batting_stats            = MagicMock(return_value=None)
_settings.pitching_stats           = MagicMock(return_value=None)
_settings.batting_stats_bref       = MagicMock(return_value=None)
_settings.pitching_stats_bref      = MagicMock(return_value=None)
_settings.bwar_bat                 = MagicMock(return_value=None)
_settings.bwar_pitch               = MagicMock(return_value=None)

sys.modules["fdb.settings"] = _settings
