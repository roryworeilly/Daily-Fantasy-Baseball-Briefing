"""
Unit tests for src/fdb/utils.py

These tests cover every public function and exercise boundary conditions
relevant to the bugs fixed during the 2026-04-29 code review.
"""
import math
import os
import tempfile
import time

from fdb.utils import normalize_name, compact, get_metric, cache_is_fresh


# ══════════════════════════════════════════════════════════════════════════════
# normalize_name
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalizeName:
    def test_basic_lowercase(self):
        assert normalize_name("Mike Trout") == "mike trout"

    def test_strips_punctuation(self):
        assert normalize_name("Shohei Ohtani") == "shohei ohtani"
        assert normalize_name("Ronald Acuña Jr.") == "ronald acuña jr"

    def test_collapses_extra_whitespace(self):
        assert normalize_name("  Freddie   Freeman  ") == "freddie freeman"

    def test_empty_string(self):
        assert normalize_name("") == ""

    def test_none_returns_empty(self):
        assert normalize_name(None) == ""

    def test_numeric_input(self):
        # Non-string input should be stringified
        result = normalize_name(42)
        assert isinstance(result, str)

    def test_already_normalised(self):
        assert normalize_name("mike trout") == "mike trout"

    def test_all_punctuation(self):
        assert normalize_name("!!!") == ""


# ══════════════════════════════════════════════════════════════════════════════
# compact
# ══════════════════════════════════════════════════════════════════════════════

class TestCompact:
    def test_rounds_to_four_digits_by_default(self):
        assert compact(3.14159265) == 3.1416

    def test_custom_ndigits(self):
        assert compact(3.14159265, 2) == 3.14

    def test_zero(self):
        assert compact(0) == 0.0

    def test_none_returns_zero(self):
        assert compact(None) == 0.0

    def test_empty_string_returns_zero(self):
        assert compact("") == 0.0

    def test_nan_returns_zero(self):
        assert compact(math.nan) == 0.0

    def test_numeric_string(self):
        assert compact("3.5") == 3.5

    def test_negative_value(self):
        assert compact(-1.2345) == -1.2345

    def test_nondescript_string_returns_zero(self):
        assert compact("abc") == 0.0

    def test_integer_input(self):
        assert compact(5) == 5.0


# ══════════════════════════════════════════════════════════════════════════════
# get_metric
# ══════════════════════════════════════════════════════════════════════════════

class TestGetMetric:
    def test_returns_first_key_found(self):
        row = {"ERA": 3.50, "xERA": 3.20}
        assert get_metric(row, "ERA", "xERA") == 3.50

    def test_falls_back_to_second_key(self):
        row = {"xERA": 3.20}
        assert get_metric(row, "ERA", "xERA") == 3.20

    def test_returns_default_when_no_key_found(self):
        row = {"AVG": 0.280}
        assert get_metric(row, "ERA", "xERA") == 0.0

    def test_custom_default(self):
        assert get_metric({}, "K", default=99.0) == 99.0

    def test_skips_none_values(self):
        row = {"ERA": None, "xERA": 3.20}
        assert get_metric(row, "ERA", "xERA") == 3.20

    def test_skips_empty_string_values(self):
        row = {"ERA": "", "xERA": 3.20}
        assert get_metric(row, "ERA", "xERA") == 3.20

    def test_numeric_string_value(self):
        row = {"ERA": "3.50"}
        assert get_metric(row, "ERA") == 3.50

    def test_zero_is_a_valid_value(self):
        # ERA of 0.00 is technically valid and should be returned, not skipped
        row = {"SV": 0}
        assert get_metric(row, "SV") == 0.0

    def test_empty_row(self):
        assert get_metric({}, "HR") == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# cache_is_fresh
# ══════════════════════════════════════════════════════════════════════════════

class TestCacheIsFresh:
    def test_nonexistent_file_is_not_fresh(self):
        assert cache_is_fresh("/tmp/does_not_exist_fdb_test.json") is False

    def test_brand_new_file_is_fresh(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            path = f.name
        try:
            assert cache_is_fresh(path, max_age_days=1.0) is True
        finally:
            os.unlink(path)

    def test_stale_file_is_not_fresh(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            path = f.name
        try:
            # Back-date the mtime by 2 days
            stale_mtime = time.time() - (2 * 86_400)
            os.utime(path, (stale_mtime, stale_mtime))
            assert cache_is_fresh(path, max_age_days=1.0) is False
        finally:
            os.unlink(path)

    def test_file_within_custom_age_is_fresh(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            path = f.name
        try:
            # Back-date by 3 days; a 7-day TTL should still consider it fresh
            mtime = time.time() - (3 * 86_400)
            os.utime(path, (mtime, mtime))
            assert cache_is_fresh(path, max_age_days=7.0) is True
        finally:
            os.unlink(path)
