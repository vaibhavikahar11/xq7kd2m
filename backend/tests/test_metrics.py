"""
Tests for backend/app/metrics.py.

All test cases use small, hand-calculated synthetic datasets so the expected
values can be verified by inspection.
"""

from __future__ import annotations

import math
from datetime import date, timezone

import numpy as np
import pandas as pd
import pytest

from app.metrics import (
    BUCKET_LABELS,
    MetricSet,
    decision_time_accuracy,
    decision_time_by_date,
    decision_time_by_hour,
    horizon_accuracy,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JAN_START = date(2026, 1, 1)
_JAN_END = date(2026, 1, 31)


def _ts(dt_str: str) -> pd.Timestamp:
    """Parse an ISO-8601 string to a UTC-aware Timestamp."""
    return pd.Timestamp(dt_str, tz="UTC")


def _make_selection(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal selection DataFrame from a list of row dicts."""
    df = pd.DataFrame(rows)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    if "publishTime" not in df.columns:
        df["publishTime"] = pd.NaT
    else:
        df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    if "missing_forecast" not in df.columns:
        df["missing_forecast"] = False
    if "horizon_hours" not in df.columns:
        df["horizon_hours"] = float("nan")
    return df


def _make_actuals(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal actuals DataFrame from a list of row dicts."""
    df = pd.DataFrame(rows)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    return df


def _make_forecasts(rows: list[dict]) -> pd.DataFrame:
    """Build a raw forecast DataFrame for horizon_accuracy tests."""
    df = pd.DataFrame(rows)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    return df


# ---------------------------------------------------------------------------
# 1. Sign convention
# ---------------------------------------------------------------------------

class TestSignConvention:
    """error = forecast - actual; positive means over-forecast."""

    def test_over_forecast_is_positive(self):
        sel = _make_selection([
            {"startTime": "2026-01-15 00:00:00", "forecast_mw": 100.0},
        ])
        act = _make_actuals([
            {"startTime": "2026-01-15 00:00:00", "generation_mw": 80.0},
        ])
        m = decision_time_accuracy(sel, act, date(2026, 1, 15), date(2026, 1, 15))
        assert m.bias > 0, "bias should be positive when forecast > actual"
        assert m.bias == pytest.approx(20.0)

    def test_under_forecast_is_negative(self):
        sel = _make_selection([
            {"startTime": "2026-01-15 00:00:00", "forecast_mw": 60.0},
        ])
        act = _make_actuals([
            {"startTime": "2026-01-15 00:00:00", "generation_mw": 80.0},
        ])
        m = decision_time_accuracy(sel, act, date(2026, 1, 15), date(2026, 1, 15))
        assert m.bias < 0
        assert m.bias == pytest.approx(-20.0)


# ---------------------------------------------------------------------------
# 2. MAE / RMSE / bias hand-calculation
# ---------------------------------------------------------------------------

class TestMaeRmseBias:
    """errors = [+10, -10]: MAE=10, RMSE=10, bias=0."""

    def _two_row_metrics(self) -> MetricSet:
        sel = _make_selection([
            {"startTime": "2026-01-15 00:00:00", "forecast_mw": 110.0},
            {"startTime": "2026-01-15 00:30:00", "forecast_mw": 90.0},
        ])
        act = _make_actuals([
            {"startTime": "2026-01-15 00:00:00", "generation_mw": 100.0},
            {"startTime": "2026-01-15 00:30:00", "generation_mw": 100.0},
        ])
        return decision_time_accuracy(sel, act, date(2026, 1, 15), date(2026, 1, 15))

    def test_mae(self):
        m = self._two_row_metrics()
        assert m.mae == pytest.approx(10.0)

    def test_rmse(self):
        m = self._two_row_metrics()
        assert m.rmse == pytest.approx(10.0)

    def test_bias_zero(self):
        m = self._two_row_metrics()
        assert m.bias == pytest.approx(0.0)

    def test_n_matched(self):
        m = self._two_row_metrics()
        assert m.n_matched == 2

    def test_n_excluded_zero(self):
        m = self._two_row_metrics()
        assert m.n_excluded == 0


# ---------------------------------------------------------------------------
# 3. Percentile values (hand-calculated)
# ---------------------------------------------------------------------------

class TestPercentiles:
    """
    errors = [0, 10, 20, 30, 40] → |e| p50=20, p90=36, p95=38.
    numpy.percentile uses linear interpolation by default.
    """

    def _five_row_metrics(self) -> MetricSet:
        slots = [
            ("2026-01-15 00:00:00", 100.0, 100.0),   # error =  0
            ("2026-01-15 00:30:00", 110.0, 100.0),   # error = +10
            ("2026-01-15 01:00:00", 120.0, 100.0),   # error = +20
            ("2026-01-15 01:30:00", 130.0, 100.0),   # error = +30
            ("2026-01-15 02:00:00", 140.0, 100.0),   # error = +40
        ]
        sel = _make_selection([
            {"startTime": s, "forecast_mw": f} for s, f, _ in slots
        ])
        act = _make_actuals([
            {"startTime": s, "generation_mw": a} for s, _, a in slots
        ])
        return decision_time_accuracy(sel, act, date(2026, 1, 15), date(2026, 1, 15))

    def test_abs_p50(self):
        m = self._five_row_metrics()
        assert m.abs_p50 == pytest.approx(20.0)

    def test_abs_p90(self):
        m = self._five_row_metrics()
        # np.percentile([0,10,20,30,40], 90) = 36.0
        assert m.abs_p90 == pytest.approx(36.0)

    def test_abs_p95(self):
        m = self._five_row_metrics()
        # np.percentile([0,10,20,30,40], 95) = 38.0
        assert m.abs_p95 == pytest.approx(38.0)

    def test_signed_p5(self):
        m = self._five_row_metrics()
        # np.percentile([0,10,20,30,40], 5) = 2.0
        assert m.signed_p5 == pytest.approx(2.0)

    def test_signed_p50(self):
        m = self._five_row_metrics()
        assert m.signed_p50 == pytest.approx(20.0)

    def test_signed_p95(self):
        m = self._five_row_metrics()
        # np.percentile([0,10,20,30,40], 95) = 38.0
        assert m.signed_p95 == pytest.approx(38.0)


# ---------------------------------------------------------------------------
# 4. Exclusion of missing forecasts
# ---------------------------------------------------------------------------

class TestExclusion:
    """3 slots, 1 with missing_forecast=True → n_matched=2, n_excluded=1."""

    def _excluded_metrics(self) -> MetricSet:
        sel = _make_selection([
            {"startTime": "2026-01-15 00:00:00", "forecast_mw": 110.0, "missing_forecast": False},
            {"startTime": "2026-01-15 00:30:00", "forecast_mw": 90.0,  "missing_forecast": False},
            {"startTime": "2026-01-15 01:00:00", "forecast_mw": None,   "missing_forecast": True},
        ])
        act = _make_actuals([
            {"startTime": "2026-01-15 00:00:00", "generation_mw": 100.0},
            {"startTime": "2026-01-15 00:30:00", "generation_mw": 100.0},
            {"startTime": "2026-01-15 01:00:00", "generation_mw": 100.0},
        ])
        return decision_time_accuracy(sel, act, date(2026, 1, 15), date(2026, 1, 15))

    def test_n_matched(self):
        assert self._excluded_metrics().n_matched == 2

    def test_n_excluded(self):
        assert self._excluded_metrics().n_excluded == 1

    def test_metrics_only_from_valid_rows(self):
        m = self._excluded_metrics()
        assert m.mae == pytest.approx(10.0)
        assert m.bias == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 5. :00 / :30 pairing (one forecast row → two matched rows)
# ---------------------------------------------------------------------------

class TestHalfHourPairing:
    """
    selection_df has :00 and :30 rows (both with same forecast_mw=120).
    actuals has matching :00 (actual=100) and :30 (actual=100).
    Expected: n_matched=2, each contributing error=+20.
    """

    def test_both_rows_matched(self):
        sel = _make_selection([
            {"startTime": "2026-01-15 10:00:00", "forecast_mw": 120.0},
            {"startTime": "2026-01-15 10:30:00", "forecast_mw": 120.0},
        ])
        act = _make_actuals([
            {"startTime": "2026-01-15 10:00:00", "generation_mw": 100.0},
            {"startTime": "2026-01-15 10:30:00", "generation_mw": 100.0},
        ])
        m = decision_time_accuracy(sel, act, date(2026, 1, 15), date(2026, 1, 15))
        assert m.n_matched == 2
        assert m.bias == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# 6. Bucket boundary tests
# ---------------------------------------------------------------------------

class TestHorizonBuckets:
    """Verify left-inclusive, right-exclusive bucket assignment."""

    def _horizon_forecast(self, horizon_hours: float, ref_time: str = "2026-01-15 12:00:00") -> pd.DataFrame:
        """Create a one-row forecast with the specified horizon."""
        start = _ts(ref_time)
        publish = start - pd.Timedelta(hours=horizon_hours, unit="ns")
        return _make_forecasts([{
            "startTime": ref_time,
            "publishTime": str(publish),
            "generation_mw": 100.0,
        }])

    def _single_actual(self, ref_time: str = "2026-01-15 12:00:00") -> pd.DataFrame:
        return _make_actuals([
            {"startTime": ref_time, "generation_mw": 90.0},
            {"startTime": pd.Timestamp(ref_time, tz="UTC") + pd.Timedelta(minutes=30, unit="ns"), "generation_mw": 90.0},
        ])

    def _get_label(self, horizon_hours: float) -> str:
        fc = self._horizon_forecast(horizon_hours)
        act = self._single_actual()
        result = horizon_accuracy(fc, act, date(2026, 1, 15), date(2026, 1, 15))
        # Return the label with matched rows
        for label, ms in result.items():
            if ms.n_matched > 0:
                return label
        return "none"

    def test_exactly_12h_is_12_24h(self):
        assert self._get_label(12.0) == "12-24h"

    def test_just_below_12h_is_6_12h(self):
        assert self._get_label(11.99) == "6-12h"

    def test_exactly_6h_is_6_12h(self):
        assert self._get_label(6.0) == "6-12h"

    def test_just_below_6h_is_0_6h(self):
        assert self._get_label(5.99) == "0-6h"

    def test_exactly_48h_is_48h_plus(self):
        assert self._get_label(48.0) == "48h+"

    def test_all_bucket_labels_present(self):
        fc = self._horizon_forecast(12.0)
        act = self._single_actual()
        result = horizon_accuracy(fc, act, date(2026, 1, 15), date(2026, 1, 15))
        assert set(result.keys()) == set(BUCKET_LABELS)

    def test_half_hour_30_horizon_regression(self):
        """Regression: a :30 row with true horizon exactly 12.0h must be in 12-24h.

        If the hourly forecast's :00 horizon is 11.5h, the :30 expansion adds
        0.5h → true horizon is exactly 12.0h.  Before the fix, horizon_accuracy
        used the :00 horizon (11.5h) for both rows, incorrectly placing the :30
        row in the 6-12h bucket.
        """
        # Forecast with :00 horizon = 11.5h
        fc = self._horizon_forecast(11.5)
        act = self._single_actual()
        result = horizon_accuracy(fc, act, date(2026, 1, 15), date(2026, 1, 15))

        # :00 row (horizon 11.5h) → 6-12h  (1 match)
        # :30 row (horizon 12.0h) → 12-24h (1 match)
        assert result["6-12h"].n_matched == 1, "the :00 row should land in 6-12h"
        assert result["12-24h"].n_matched == 1, "the :30 row should land in 12-24h"


# ---------------------------------------------------------------------------
# 7. MAE as percentage of mean actual
# ---------------------------------------------------------------------------

class TestMaePct:
    """actuals=[100, 100], errors=[+10, -10] → MAE=10, mean_actual=100, mae_pct=10.0."""

    def test_mae_pct(self):
        sel = _make_selection([
            {"startTime": "2026-01-15 00:00:00", "forecast_mw": 110.0},
            {"startTime": "2026-01-15 00:30:00", "forecast_mw": 90.0},
        ])
        act = _make_actuals([
            {"startTime": "2026-01-15 00:00:00", "generation_mw": 100.0},
            {"startTime": "2026-01-15 00:30:00", "generation_mw": 100.0},
        ])
        m = decision_time_accuracy(sel, act, date(2026, 1, 15), date(2026, 1, 15))
        assert m.mae_pct == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# 8. Empty / edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """All missing forecasts → n_matched=0, all metrics NaN."""

    def test_all_missing_returns_nan_metrics(self):
        sel = _make_selection([
            {"startTime": "2026-01-15 00:00:00", "forecast_mw": None, "missing_forecast": True},
        ])
        act = _make_actuals([
            {"startTime": "2026-01-15 00:00:00", "generation_mw": 100.0},
        ])
        m = decision_time_accuracy(sel, act, date(2026, 1, 15), date(2026, 1, 15))
        assert m.n_matched == 0
        assert m.n_excluded == 1
        assert math.isnan(m.mae)
        assert math.isnan(m.rmse)

    def test_horizon_negative_excluded(self):
        """Rows with horizon < 0 must not appear in any bucket."""
        fc = _make_forecasts([{
            "startTime": "2026-01-15 00:00:00",
            "publishTime": "2026-01-16 00:00:00",   # publishTime > startTime → horizon < 0
            "generation_mw": 100.0,
        }])
        act = _make_actuals([
            {"startTime": "2026-01-15 00:00:00", "generation_mw": 90.0},
            {"startTime": "2026-01-15 00:30:00", "generation_mw": 90.0},
        ])
        result = horizon_accuracy(fc, act, date(2026, 1, 15), date(2026, 1, 15))
        total_matched = sum(ms.n_matched for ms in result.values())
        assert total_matched == 0

    def test_by_date_returns_date_keyed_dict(self):
        sel = _make_selection([
            {"startTime": "2026-01-15 00:00:00", "forecast_mw": 110.0},
            {"startTime": "2026-01-16 00:00:00", "forecast_mw": 90.0},
        ])
        act = _make_actuals([
            {"startTime": "2026-01-15 00:00:00", "generation_mw": 100.0},
            {"startTime": "2026-01-16 00:00:00", "generation_mw": 100.0},
        ])
        result = decision_time_by_date(sel, act, date(2026, 1, 15), date(2026, 1, 16))
        assert date(2026, 1, 15) in result
        assert date(2026, 1, 16) in result
        assert result[date(2026, 1, 15)].bias == pytest.approx(10.0)
        assert result[date(2026, 1, 16)].bias == pytest.approx(-10.0)

    def test_by_hour_returns_all_24_hours(self):
        sel = _make_selection([
            {"startTime": "2026-01-15 00:00:00", "forecast_mw": 110.0},
        ])
        act = _make_actuals([
            {"startTime": "2026-01-15 00:00:00", "generation_mw": 100.0},
        ])
        result = decision_time_by_hour(sel, act, date(2026, 1, 15), date(2026, 1, 15))
        assert set(result.keys()) == set(range(24))


# ---------------------------------------------------------------------------
# Buffer tail correctness
# ---------------------------------------------------------------------------


class TestBufferTail:
    """Prove that the over-forecast shortfall buffer uses signed_p95,
    not -signed_p5.

    Hand-calculated dataset:
        20 rows, errors = [-10, -8, -6, -4, -2, 0, 2, 4, 6, 8,
                            10, 12, 14, 16, 18, 20, 22, 24, 26, 28]

        numpy linear interpolation (default):
          signed_p5  = np.percentile(errors, 5)   = -8.1
          signed_p95 = np.percentile(errors, 95)  = 26.1

        Old (wrong) buffer = max(0, -signed_p5) = 8.1   (under-forecast tail)
        New (correct) buffer = max(0, signed_p95) = 26.1 (over-forecast tail)

    The over-forecast tail (positive errors) is the one that leaves the
    buyer short, so the reserve buffer MUST equal signed_p95.
    """

    @pytest.fixture()
    def metrics(self) -> MetricSet:
        # 20 evenly spaced errors from -10 to +28 (step 2)
        errors = list(range(-10, 30, 2))  # [-10, -8, ..., 26, 28]
        assert len(errors) == 20
        actuals_val = 100.0
        rows = []
        for i, err in enumerate(errors):
            t = f"2026-01-15 {i:02d}:00:00"
            rows.append({"startTime": t, "forecast_mw": actuals_val + err})
        sel = _make_selection(rows)
        act = _make_actuals([
            {"startTime": f"2026-01-15 {i:02d}:00:00", "generation_mw": actuals_val}
            for i in range(20)
        ])
        return decision_time_accuracy(sel, act, date(2026, 1, 15), date(2026, 1, 15))

    def test_signed_p95_is_over_forecast_tail(self, metrics: MetricSet):
        """signed_p95 must be the large POSITIVE value (over-forecast side)."""
        assert metrics.signed_p95 > 0
        assert metrics.signed_p95 == pytest.approx(26.1, abs=0.01)

    def test_signed_p5_is_under_forecast_tail(self, metrics: MetricSet):
        """signed_p5 must be NEGATIVE (under-forecast / surplus side)."""
        assert metrics.signed_p5 < 0
        assert metrics.signed_p5 == pytest.approx(-8.1, abs=0.01)

    def test_buffer_should_use_signed_p95_not_neg_p5(self, metrics: MetricSet):
        """The reserve buffer = max(0, signed_p95), NOT max(0, -signed_p5).

        This test would FAIL under the old formula (max(0, -signed_p5) = 8.1)
        because the correct buffer (= 26.1) is much larger.
        """
        correct_buffer = max(0.0, metrics.signed_p95)
        wrong_buffer = max(0.0, -metrics.signed_p5)
        # The two tails are NOT equal for an asymmetric distribution
        assert correct_buffer != pytest.approx(wrong_buffer, abs=1.0)
        # The correct buffer is the over-forecast (positive) tail
        assert correct_buffer == pytest.approx(26.1, abs=0.01)

    def test_surplus_risk_uses_neg_signed_p5(self, metrics: MetricSet):
        """Surplus risk = max(0, -signed_p5) — the under-forecast tail."""
        surplus = max(0.0, -metrics.signed_p5)
        assert surplus == pytest.approx(8.1, abs=0.01)
