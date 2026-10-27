"""Tests for app.selection – forecast cutoff-selection logic.

All tests use synthetic in-memory DataFrames so they run without any
data files on disk.  The seven cases specified in the project brief are
marked with their number in the test name.

Helper
------
``make_df(rows)`` converts a list of dicts with plain ISO strings into a
properly UTC-aware DataFrame matching the shape expected by select_day_forecast.
An empty list produces an empty DataFrame with the correct dtypes.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from app.selection import (
    HalfHourSlot,
    compute_cutoff_utc,
    select_day_forecast,
    select_january_forecasts,
)

# ── Test helpers ──────────────────────────────────────────────────────────────

UTC = timezone.utc


def utc(iso: str) -> datetime:
    """Parse an ISO-8601 string ending in Z into a UTC-aware datetime."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a forecast DataFrame from plain-dict rows.

    Accepts ``startTime`` and ``publishTime`` as ISO strings or datetimes.
    Returns a DataFrame with UTC-aware timestamp columns – the same shape
    that ``load_forecasts()`` produces.
    """
    if not rows:
        df = pd.DataFrame(
            {"startTime": pd.Series([], dtype="object"),
             "publishTime": pd.Series([], dtype="object"),
             "generation_mw": pd.Series([], dtype="int64")}
        )
    else:
        df = pd.DataFrame(rows)

    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    return df


def slot_for(slots: list[HalfHourSlot], iso: str) -> HalfHourSlot:
    """Return the slot whose startTime matches the given ISO string."""
    target = utc(iso)
    matches = [s for s in slots if s.startTime == target]
    assert matches, f"No slot found for {iso}"
    return matches[0]


# ── compute_cutoff_utc unit tests ─────────────────────────────────────────────


def test_cutoff_january_is_utc():
    """January is GMT, so cutoff_hour=9 → 09:00 UTC on D-1."""
    cutoff = compute_cutoff_utc(date(2026, 1, 15), 9)
    assert cutoff == utc("2026-01-14T09:00:00Z")


def test_cutoff_crosses_year_boundary():
    """Delivery 2026-01-01 → D-1 is 2025-12-31, cutoff 09:00 UTC."""
    cutoff = compute_cutoff_utc(date(2026, 1, 1), 9)
    assert cutoff == utc("2025-12-31T09:00:00Z")


def test_cutoff_respects_cutoff_hour():
    """Different cutoff_hour values map to the correct UTC hour."""
    assert compute_cutoff_utc(date(2026, 1, 15), 6) == utc("2026-01-14T06:00:00Z")
    assert compute_cutoff_utc(date(2026, 1, 15), 12) == utc("2026-01-14T12:00:00Z")


# ── select_day_forecast – the 7 mandated test cases ──────────────────────────


def test_case1_forecast_one_minute_after_cutoff_is_ignored():
    """Case 1: a forecast published 1 minute after the cutoff is excluded."""
    df = make_df([
        {
            "startTime": "2026-01-15T00:00:00Z",
            "publishTime": "2026-01-14T09:01:00Z",   # 1 min AFTER 09:00 cutoff
            "generation_mw": 5000,
        }
    ])
    slots = select_day_forecast(date(2026, 1, 15), df, cutoff_hour=9)

    assert len(slots) == 48
    assert all(s.missing_forecast for s in slots)
    assert all(s.forecast_mw is None for s in slots)


def test_case2_latest_of_several_earlier_forecasts_wins():
    """Case 2: the forecast with the greatest publishTime ≤ cutoff is chosen."""
    df = make_df([
        {"startTime": "2026-01-15T06:00:00Z",
         "publishTime": "2026-01-14T06:00:00Z", "generation_mw": 100},
        {"startTime": "2026-01-15T06:00:00Z",
         "publishTime": "2026-01-14T07:30:00Z", "generation_mw": 250},
        {"startTime": "2026-01-15T06:00:00Z",
         "publishTime": "2026-01-14T08:30:00Z", "generation_mw": 400},   # latest
    ])
    slots = select_day_forecast(date(2026, 1, 15), df, cutoff_hour=9)

    s00 = slot_for(slots, "2026-01-15T06:00:00Z")
    s30 = slot_for(slots, "2026-01-15T06:30:00Z")
    assert s00.forecast_mw == 400
    assert s30.forecast_mw == 400
    assert s00.publishTime == utc("2026-01-14T08:30:00Z")


def test_case3_forecast_exactly_at_cutoff_is_included():
    """Case 3: a forecast published exactly at the cutoff (<=) is included."""
    df = make_df([
        {
            "startTime": "2026-01-15T12:00:00Z",
            "publishTime": "2026-01-14T09:00:00Z",   # EXACTLY at cutoff
            "generation_mw": 7777,
        }
    ])
    slots = select_day_forecast(date(2026, 1, 15), df, cutoff_hour=9)

    s = slot_for(slots, "2026-01-15T12:00:00Z")
    assert not s.missing_forecast
    assert s.forecast_mw == 7777
    assert s.publishTime == utc("2026-01-14T09:00:00Z")


def test_case4_missing_forecast_produces_flagged_null():
    """Case 4: when no eligible forecast exists, missing_forecast=True, forecast_mw=None."""
    df = make_df([])   # empty – no data at all
    slots = select_day_forecast(date(2026, 1, 15), df, cutoff_hour=9)

    assert len(slots) == 48
    for s in slots:
        assert s.missing_forecast is True
        assert s.forecast_mw is None
        assert s.publishTime is None
        assert s.horizon_hours is None


def test_case5_hourly_forecast_maps_to_both_half_hours():
    """Case 5: one WINDFOR hourly row produces both :00 and :30 slots."""
    df = make_df([
        {
            "startTime": "2026-01-15T05:00:00Z",
            "publishTime": "2026-01-14T08:00:00Z",
            "generation_mw": 5000,
        }
    ])
    slots = select_day_forecast(date(2026, 1, 15), df, cutoff_hour=9)

    s00 = slot_for(slots, "2026-01-15T05:00:00Z")
    s30 = slot_for(slots, "2026-01-15T05:30:00Z")

    # Both carry the same generation value (no interpolation).
    assert s00.forecast_mw == 5000
    assert s30.forecast_mw == 5000
    assert not s00.missing_forecast
    assert not s30.missing_forecast

    # Horizon differs by exactly 0.5 h.
    assert s30.horizon_hours == pytest.approx(s00.horizon_hours + 0.5)

    # publishTime is identical for both.
    assert s00.publishTime == s30.publishTime


def test_case6_jan1_uses_dec31_forecast():
    """Case 6: delivery 2026-01-01 uses a forecast published on 2025-12-31."""
    df = make_df([
        # Published before cutoff (2025-12-31 09:00 UTC) → eligible
        {"startTime": "2026-01-01T00:00:00Z",
         "publishTime": "2025-12-31T08:30:00Z", "generation_mw": 9000},
        # Published after cutoff → must be excluded
        {"startTime": "2026-01-01T00:00:00Z",
         "publishTime": "2026-01-01T01:00:00Z", "generation_mw": 9999},
    ])
    slots = select_day_forecast(date(2026, 1, 1), df, cutoff_hour=9)

    s = slot_for(slots, "2026-01-01T00:00:00Z")
    assert s.forecast_mw == 9000
    assert s.publishTime == utc("2025-12-31T08:30:00Z")
    assert not s.missing_forecast


def test_case7_changing_cutoff_hour_changes_selection():
    """Case 7: moving the cutoff hour changes which forecast is selected."""
    df = make_df([
        {"startTime": "2026-01-15T00:00:00Z",
         "publishTime": "2026-01-14T07:00:00Z", "generation_mw": 100},
        {"startTime": "2026-01-15T00:00:00Z",
         "publishTime": "2026-01-14T08:30:00Z", "generation_mw": 200},
    ])

    # cutoff_hour=9: both forecasts eligible, 08:30 (latest) wins → 200 MW
    slots_9 = select_day_forecast(date(2026, 1, 15), df, cutoff_hour=9)
    assert slot_for(slots_9, "2026-01-15T00:00:00Z").forecast_mw == 200

    # cutoff_hour=8: cutoff is 08:00; 08:30 is after cutoff → excluded
    # only 07:00 is eligible → 100 MW
    slots_8 = select_day_forecast(date(2026, 1, 15), df, cutoff_hour=8)
    assert slot_for(slots_8, "2026-01-15T00:00:00Z").forecast_mw == 100

    # cutoff_hour=6: cutoff is 06:00; both forecasts are after → all missing
    slots_6 = select_day_forecast(date(2026, 1, 15), df, cutoff_hour=6)
    assert slot_for(slots_6, "2026-01-15T00:00:00Z").missing_forecast is True


# ── Additional correctness tests ──────────────────────────────────────────────


def test_always_returns_48_slots():
    """select_day_forecast always returns exactly 48 slots regardless of input."""
    for df in [make_df([]), make_df([{
        "startTime": "2026-01-10T12:00:00Z",
        "publishTime": "2026-01-09T08:00:00Z",
        "generation_mw": 1234,
    }])]:
        slots = select_day_forecast(date(2026, 1, 10), df, cutoff_hour=9)
        assert len(slots) == 48


def test_slots_cover_all_half_hours_of_the_day():
    """The 48 slots span exactly 00:00 to 23:30 UTC for a January date."""
    df = make_df([])
    slots = select_day_forecast(date(2026, 1, 20), df, cutoff_hour=9)
    times = [s.startTime for s in slots]

    assert times[0] == utc("2026-01-20T00:00:00Z")
    assert times[-1] == utc("2026-01-20T23:30:00Z")
    # All consecutive pairs are 30 minutes apart.
    for a, b in zip(times, times[1:]):
        assert (b - a).total_seconds() == 1800


def test_horizon_hours_is_positive_for_future_forecasts():
    """A forecast published before delivery must have positive horizon_hours."""
    df = make_df([{
        "startTime": "2026-01-15T10:00:00Z",
        "publishTime": "2026-01-14T09:00:00Z",   # 25 h before :00, 25.5 h before :30
        "generation_mw": 3000,
    }])
    slots = select_day_forecast(date(2026, 1, 15), df, cutoff_hour=9)

    s00 = slot_for(slots, "2026-01-15T10:00:00Z")
    s30 = slot_for(slots, "2026-01-15T10:30:00Z")
    assert s00.horizon_hours == pytest.approx(25.0)
    assert s30.horizon_hours == pytest.approx(25.5)


def test_publishtime_tiebreak_picks_higher_generation():
    """When two rows share the same publishTime, higher generation_mw is chosen."""
    df = make_df([
        {"startTime": "2026-01-15T00:00:00Z",
         "publishTime": "2026-01-14T08:00:00Z", "generation_mw": 100},
        {"startTime": "2026-01-15T00:00:00Z",
         "publishTime": "2026-01-14T08:00:00Z", "generation_mw": 999},  # same pub, higher gen
    ])
    slots = select_day_forecast(date(2026, 1, 15), df, cutoff_hour=9)
    assert slot_for(slots, "2026-01-15T00:00:00Z").forecast_mw == 999


def test_unrelated_forecasts_do_not_contaminate_other_hours():
    """A forecast for 05:00 must not appear in the 06:00 slot."""
    df = make_df([{
        "startTime": "2026-01-15T05:00:00Z",
        "publishTime": "2026-01-14T08:00:00Z",
        "generation_mw": 5000,
    }])
    slots = select_day_forecast(date(2026, 1, 15), df, cutoff_hour=9)

    # 06:00 and 06:30 should be missing
    assert slot_for(slots, "2026-01-15T06:00:00Z").missing_forecast is True
    assert slot_for(slots, "2026-01-15T06:30:00Z").missing_forecast is True


# ── select_january_forecasts integration ─────────────────────────────────────


def test_select_january_returns_1488_rows():
    """select_january_forecasts returns 31 × 48 = 1 488 rows for any input."""
    df = make_df([])
    result = select_january_forecasts(df, cutoff_hour=9)
    assert len(result) == 1488


def test_select_january_column_names():
    """Result DataFrame has the expected columns."""
    df = make_df([])
    result = select_january_forecasts(df, cutoff_hour=9)
    assert set(result.columns) == {
        "startTime", "forecast_mw", "publishTime", "horizon_hours", "missing_forecast"
    }


def test_select_january_starttime_is_utc_aware():
    """startTime column must be UTC-aware (no naive timestamps)."""
    df = make_df([])
    result = select_january_forecasts(df, cutoff_hour=9)
    assert str(result["startTime"].dtype) == "datetime64[ns, UTC]"


def test_select_january_cutoff_hour_propagates():
    """cutoff_hour is forwarded to every daily call."""
    df = make_df([
        # Published 08:30 on D-1 → eligible for cutoff=9, not for cutoff=8
        {"startTime": "2026-01-15T00:00:00Z",
         "publishTime": "2026-01-14T08:30:00Z", "generation_mw": 999},
    ])
    result_9 = select_january_forecasts(df, cutoff_hour=9)
    result_8 = select_january_forecasts(df, cutoff_hour=8)

    jan15_9 = result_9[result_9["startTime"] == utc("2026-01-15T00:00:00Z")]
    jan15_8 = result_8[result_8["startTime"] == utc("2026-01-15T00:00:00Z")]

    assert jan15_9.iloc[0]["forecast_mw"] == 999
    # pandas returns np.bool_, so use == not `is`
    assert jan15_8.iloc[0]["missing_forecast"] == True  # noqa: E712
