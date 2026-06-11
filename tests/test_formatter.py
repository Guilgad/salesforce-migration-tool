"""בדיקות formatter — parse_date, normalize_text."""
from modules import formatter


# ===== parse_date =====

def test_parse_iso():
    assert formatter.parse_date("2026-06-04") == "2026-06-04"

def test_parse_dotted_israeli():
    assert formatter.parse_date("04.06.2026") == "2026-06-04"

def test_parse_dotted_single_digit():
    assert formatter.parse_date("4.6.2026") == "2026-06-04"

def test_parse_slash():
    assert formatter.parse_date("04/06/2026") == "2026-06-04"

def test_parse_dash_dmy():
    assert formatter.parse_date("04-06-2026") == "2026-06-04"

def test_parse_slash_ymd():
    assert formatter.parse_date("2026/06/04") == "2026-06-04"

def test_parse_strips_whitespace():
    assert formatter.parse_date("  04.06.2026  ") == "2026-06-04"

def test_junk_returns_none():
    assert formatter.parse_date("לא תאריך") is None

def test_impossible_date_returns_none():
    assert formatter.parse_date("32.13.2026") is None

def test_empty_returns_none():
    assert formatter.parse_date("") is None

def test_none_returns_none():
    assert formatter.parse_date(None) is None


# ===== normalize_text =====

def test_normalize_trims():
    assert formatter.normalize_text("  שלום  ") == "שלום"

def test_normalize_none():
    assert formatter.normalize_text(None) == ""

def test_normalize_number():
    assert formatter.normalize_text(42) == "42"


import pytest
from modules.formatter import parse_bool


@pytest.mark.parametrize("val", ["TRUE", "true", "yes", "1", "כן", "אמת", "V", "✓"])
def test_parse_bool_true(val):
    assert parse_bool(val) == "TRUE"


@pytest.mark.parametrize("val", ["FALSE", "false", "no", "0", "לא"])
def test_parse_bool_false(val):
    assert parse_bool(val) == "FALSE"


def test_parse_bool_empty_is_none():
    assert parse_bool("") is None
    assert parse_bool(None) is None
    assert parse_bool("   ") is None


def test_parse_bool_unknown_is_none():
    assert parse_bool("אולי") is None
