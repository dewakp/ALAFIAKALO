"""Unit tests for firebase_sync helper functions.

These are pure-Python, no DB, no Firebase — fast and deterministic.
"""

import datetime
import pytest

from app.services.firebase_sync import (
    _float,
    _int,
    _parse_time_str,
    _parse_session_dt,
    _parse_hhmm_to_minutes,
    _to_celsius,
    _parse_ref_range,
)


# ── _float ────────────────────────────────────────────────────────────────────

def test_float_returns_first_match():
    assert _float({"a": 3.5, "b": 1.0}, "a", "b") == 3.5


def test_float_falls_back_to_second_key():
    assert _float({"b": 2.0}, "a", "b") == 2.0


def test_float_returns_none_when_no_key():
    assert _float({"x": 1}, "a", "b") is None


def test_float_coerces_string():
    assert _float({"v": "42.0"}, "v") == 42.0


def test_float_ignores_non_numeric_string():
    assert _float({"v": "N/A"}, "v") is None


# ── _int ─────────────────────────────────────────────────────────────────────

def test_int_truncates_float():
    assert _int({"v": 3.9}, "v") == 3


def test_int_returns_none_for_missing():
    assert _int({}, "v") is None


# ── _parse_time_str ──────────────────────────────────────────────────────────

def test_parse_time_hhmm():
    t = _parse_time_str("13:30")
    assert t == datetime.time(13, 30, 0)


def test_parse_time_hhmmss():
    t = _parse_time_str("08:05:45")
    assert t == datetime.time(8, 5, 45)


def test_parse_time_midnight():
    assert _parse_time_str("00:00") == datetime.time(0, 0, 0)


def test_parse_time_none():
    assert _parse_time_str(None) is None


def test_parse_time_empty_string():
    assert _parse_time_str("") is None


def test_parse_time_invalid():
    assert _parse_time_str("not-a-time") is None


# ── _parse_session_dt ────────────────────────────────────────────────────────

def test_parse_session_dt_basic():
    dt = _parse_session_dt("2026-04-28", "14:30")
    assert dt is not None
    assert dt.date() == datetime.date(2026, 4, 28)
    assert dt.hour == 14
    assert dt.minute == 30
    assert dt.tzinfo is not None  # must be timezone-aware


def test_parse_session_dt_no_time_defaults_midnight():
    dt = _parse_session_dt("2026-04-28", None)
    assert dt is not None
    assert dt.hour == 0 and dt.minute == 0


def test_parse_session_dt_none_date():
    assert _parse_session_dt(None, "10:00") is None


def test_parse_session_dt_invalid_date():
    assert _parse_session_dt("not-a-date", "10:00") is None


# ── _parse_hhmm_to_minutes ───────────────────────────────────────────────────

def test_hhmm_to_minutes_basic():
    assert _parse_hhmm_to_minutes("4:14") == 254  # 4*60 + 14


def test_hhmm_to_minutes_zero():
    assert _parse_hhmm_to_minutes("0:00") == 0


def test_hhmm_to_minutes_whole_hours():
    assert _parse_hhmm_to_minutes("3:00") == 180


def test_hhmm_to_minutes_decimal_hours():
    # 1.5 hours = 90 minutes
    assert _parse_hhmm_to_minutes("1.5") == 90


def test_hhmm_to_minutes_none():
    assert _parse_hhmm_to_minutes(None) is None


def test_hhmm_to_minutes_invalid():
    assert _parse_hhmm_to_minutes("bad") is None


# ── _to_celsius ──────────────────────────────────────────────────────────────

def test_to_celsius_already_celsius():
    assert _to_celsius(37.0, "Celsius") == 37.0


def test_to_celsius_from_fahrenheit():
    result = _to_celsius(98.6, "Fahrenheit")
    assert result is not None
    assert abs(result - 37.0) < 0.01


def test_to_celsius_from_fahrenheit_case_insensitive():
    result = _to_celsius(212.0, "fahrenheit")
    assert result is not None
    assert abs(result - 100.0) < 0.01


def test_to_celsius_none_value():
    assert _to_celsius(None, "Celsius") is None


def test_to_celsius_none_unit_passthrough():
    assert _to_celsius(36.5, None) == 36.5


# ── _parse_ref_range ─────────────────────────────────────────────────────────

def test_parse_ref_range_basic():
    low, high = _parse_ref_range("3.4 - 4.8")
    assert low == 3.4
    assert high == 4.8


def test_parse_ref_range_integer_values():
    low, high = _parse_ref_range("0 - 100")
    assert low == 0.0 and high == 100.0


def test_parse_ref_range_empty():
    low, high = _parse_ref_range("")
    assert low is None and high is None


def test_parse_ref_range_none():
    low, high = _parse_ref_range(None)
    assert low is None and high is None


def test_parse_ref_range_non_numeric():
    low, high = _parse_ref_range("Negative")
    assert low is None and high is None


def test_parse_ref_range_en_dash():
    # Firebase sometimes uses en-dash (–) instead of hyphen
    low, high = _parse_ref_range("1.00\u20132.50")
    assert low == 1.0 and high == 2.5
