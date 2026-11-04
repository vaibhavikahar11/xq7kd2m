"""
metrics.py — Forecast accuracy metrics for Gridbricks wind forecast app.

Pairing rule (mirrors selection.py):
  WINDFOR is hourly; actuals (FUELHH) are half-hourly.
  Each hourly forecast covers BOTH the :00 and :30 half-hours whose hour matches.
  This means every paired row contributes two (forecast, actual) pairs to the metrics.

Error convention:
  error = forecast_mw - actual_mw
  Positive error → over-forecast (predicted more wind than occurred).

Exclusion policy:
  Any slot where forecast_mw is None/NaN OR actual_mw is None/NaN is excluded.
  n_excluded = total slots in the date range − n_matched.

Horizon buckets (left-inclusive, right-exclusive):
  "0-6h"   : [0, 6)
  "6-12h"  : [6, 12)
  "12-24h" : [12, 24)   ← exactly 12.0 h lands here
  "24-36h" : [24, 36)
  "36-48h" : [36, 48)
  "48h+"   : [48, ∞)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timezone
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

HORIZON_BUCKETS: list[tuple[str, float, float]] = [
    ("0-6h", 0.0, 6.0),
    ("6-12h", 6.0, 12.0),
    ("12-24h", 12.0, 24.0),
    ("24-36h", 24.0, 36.0),
    ("36-48h", 36.0, 48.0),
    ("48h+", 48.0, float("inf")),
]

BUCKET_LABELS = [b[0] for b in HORIZON_BUCKETS]


@dataclass(frozen=True)
class MetricSet:
    """
    Immutable container for a set of forecast accuracy metrics.

    Attributes
    ----------
    n_matched   : Number of (forecast, actual) pairs used in computation.
    n_excluded  : Number of slots excluded due to missing forecast or actual.
    mae         : Mean Absolute Error (MW).
    rmse        : Root Mean Square Error (MW).
    bias        : Mean signed error — forecast minus actual (MW).
    mae_pct     : MAE as a percentage of the mean actual (NaN if mean_actual == 0).
    abs_p50     : 50th percentile of absolute errors (MW).
    abs_p90     : 90th percentile of absolute errors (MW).
    abs_p95     : 95th percentile of absolute errors (MW).
    signed_p5   : 5th percentile of signed errors (MW).
    signed_p50  : 50th percentile of signed errors (MW).
    signed_p95  : 95th percentile of signed errors (MW).
    """

    n_matched: int
    n_excluded: int
    mae: float
    rmse: float
    bias: float
    mae_pct: float
    abs_p50: float
    abs_p90: float
    abs_p95: float
    signed_p5: float
    signed_p50: float
    signed_p95: float


def _empty_metric_set(n_excluded: int = 0) -> MetricSet:
    """Return a MetricSet with zero matches and NaN metrics."""
    nan = float("nan")
    return MetricSet(
        n_matched=0,
        n_excluded=n_excluded,
        mae=nan,
        rmse=nan,
        bias=nan,
        mae_pct=nan,
        abs_p50=nan,
        abs_p90=nan,
        abs_p95=nan,
        signed_p5=nan,
        signed_p50=nan,
        signed_p95=nan,
    )


def _compute_metrics(errors: np.ndarray, actuals: np.ndarray, n_excluded: int) -> MetricSet:
    """
    Compute a MetricSet from arrays of signed errors and actual values.

    Parameters
    ----------
    errors      : 1-D array of (forecast - actual) values (no NaNs).
    actuals     : 1-D array of actual generation values (no NaNs), same length.
    n_excluded  : Pre-computed exclusion count to embed in the result.
    """
    n = len(errors)
    if n == 0:
        return _empty_metric_set(n_excluded)

    abs_err = np.abs(errors)
    mae = float(np.mean(abs_err))
    rmse = float(np.sqrt(np.mean(errors**2)))
    bias = float(np.mean(errors))
    mean_actual = float(np.mean(actuals))
    mae_pct = (mae / mean_actual * 100.0) if mean_actual != 0.0 else float("nan")

    abs_p50 = float(np.percentile(abs_err, 50))
    abs_p90 = float(np.percentile(abs_err, 90))
    abs_p95 = float(np.percentile(abs_err, 95))
    signed_p5 = float(np.percentile(errors, 5))
    signed_p50 = float(np.percentile(errors, 50))
    signed_p95 = float(np.percentile(errors, 95))

    return MetricSet(
        n_matched=n,
        n_excluded=n_excluded,
        mae=mae,
        rmse=rmse,
        bias=bias,
        mae_pct=mae_pct,
        abs_p50=abs_p50,
        abs_p90=abs_p90,
        abs_p95=abs_p95,
        signed_p5=signed_p5,
        signed_p50=signed_p50,
        signed_p95=signed_p95,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _date_bounds(start_date: date, end_date: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    Return UTC-aware Timestamps for [midnight start_date, midnight after end_date].
    """
    t_start = pd.Timestamp(start_date, tz="UTC")
    t_end = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1)
    return t_start, t_end


def _filter_by_date(df: pd.DataFrame, col: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Filter *df* so that *col* falls in [start_date, end_date] (inclusive, UTC days)."""
    t_start, t_end = _date_bounds(start_date, end_date)
    ts = df[col]
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    mask = (ts >= t_start) & (ts < t_end)
    return df[mask].copy()


def _join_selection_actuals(
    selection_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> tuple[pd.DataFrame, int]:
    """
    Inner-join selection_df with actuals_df on startTime within [start_date, end_date].

    Returns (joined_df, n_excluded).
    n_excluded accounts for missing_forecast rows and unmatched startTimes.
    """
    sel = _filter_by_date(selection_df, "startTime", start_date, end_date).copy()
    act = _filter_by_date(actuals_df, "startTime", start_date, end_date).copy()

    # Normalise timezone representation for join key
    sel["startTime"] = pd.to_datetime(sel["startTime"], utc=True)
    act["startTime"] = pd.to_datetime(act["startTime"], utc=True)

    n_total = len(sel)

    # Drop rows where forecast is missing before joining
    sel_valid = sel[sel["missing_forecast"] == False].copy()  # noqa: E712

    joined = sel_valid.merge(
        act[["startTime", "generation_mw"]].rename(columns={"generation_mw": "actual_mw"}),
        on="startTime",
        how="inner",
    )

    # Drop any remaining rows with NaN in either column
    joined = joined.dropna(subset=["forecast_mw", "actual_mw"])

    n_excluded = n_total - len(joined)
    return joined, n_excluded


# ---------------------------------------------------------------------------
# Public API — Decision-time accuracy
# ---------------------------------------------------------------------------

def decision_time_accuracy(
    selection_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> MetricSet:
    """
    Overall decision-time accuracy for the given delivery date range.

    Parameters
    ----------
    selection_df : DataFrame produced by selection.select_january_forecasts()
                   (columns: startTime, forecast_mw, publishTime,
                    horizon_hours, missing_forecast).
    actuals_df   : DataFrame with columns startTime, generation_mw.
    start_date   : First delivery date (inclusive).
    end_date     : Last delivery date (inclusive).

    Returns
    -------
    MetricSet with all accuracy metrics.
    """
    joined, n_excluded = _join_selection_actuals(selection_df, actuals_df, start_date, end_date)
    errors = (joined["forecast_mw"] - joined["actual_mw"]).to_numpy(dtype=float)
    actuals = joined["actual_mw"].to_numpy(dtype=float)
    return _compute_metrics(errors, actuals, n_excluded)


def decision_time_by_hour(
    selection_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> dict[int, MetricSet]:
    """
    Decision-time accuracy grouped by hour-of-day in UK local time (Europe/London).

    Returns a dict keyed by integer hour (0–23).
    Hours with no matched data return an empty MetricSet.
    """
    joined, _ = _join_selection_actuals(selection_df, actuals_df, start_date, end_date)

    result: dict[int, MetricSet] = {}
    if joined.empty:
        return {h: _empty_metric_set() for h in range(24)}

    joined["hour_local"] = (
        joined["startTime"].dt.tz_convert("Europe/London").dt.hour
    )

    for hour in range(24):
        subset = joined[joined["hour_local"] == hour]
        if subset.empty:
            result[hour] = _empty_metric_set()
        else:
            errors = (subset["forecast_mw"] - subset["actual_mw"]).to_numpy(dtype=float)
            actuals = subset["actual_mw"].to_numpy(dtype=float)
            result[hour] = _compute_metrics(errors, actuals, n_excluded=0)

    return result


def decision_time_by_date(
    selection_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> dict[date, MetricSet]:
    """
    Decision-time accuracy grouped by delivery date (UTC calendar day).

    Returns a dict keyed by ``datetime.date``.
    """
    joined, _ = _join_selection_actuals(selection_df, actuals_df, start_date, end_date)

    result: dict[date, MetricSet] = {}
    if joined.empty:
        return {}

    joined["delivery_date"] = joined["startTime"].dt.date

    for d, group in joined.groupby("delivery_date"):
        errors = (group["forecast_mw"] - group["actual_mw"]).to_numpy(dtype=float)
        actuals = group["actual_mw"].to_numpy(dtype=float)
        result[d] = _compute_metrics(errors, actuals, n_excluded=0)

    return result


# ---------------------------------------------------------------------------
# Public API — Horizon accuracy
# ---------------------------------------------------------------------------

def _assign_bucket(horizon_h: float) -> Optional[str]:
    """Return the bucket label for a given horizon in hours, or None if horizon < 0."""
    if horizon_h < 0:
        return None
    for label, lo, hi in HORIZON_BUCKETS:
        if lo <= horizon_h < hi:
            return label
    return "48h+"  # catch-all (should be handled above, but be safe)


def horizon_accuracy(
    forecast_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> dict[str, MetricSet]:
    """
    Accuracy grouped by forecast horizon bucket, using ALL forecast rows.

    Each WINDFOR row is expanded to BOTH the :00 and :30 half-hourly actuals whose
    hour matches (consistent with the selection.py pairing rule).
    Rows with horizon < 0 are excluded (published after their delivery period).

    Bucket boundaries are left-inclusive, right-exclusive:
      "0-6h": [0,6), "6-12h": [6,12), "12-24h": [12,24),
      "24-36h": [24,36), "36-48h": [36,48), "48h+": [48,∞)
    Exactly 12.0 h lands in "12-24h".

    Parameters
    ----------
    forecast_df : Raw forecasts DataFrame (columns: startTime, publishTime, generation_mw).
    actuals_df  : DataFrame with columns startTime, generation_mw.
    start_date  : First delivery date (inclusive) — filters forecast startTime.
    end_date    : Last delivery date (inclusive).

    Returns
    -------
    dict[str, MetricSet] with all 6 bucket labels always present.
    """
    fc = _filter_by_date(forecast_df, "startTime", start_date, end_date).copy()
    act = _filter_by_date(actuals_df, "startTime", start_date, end_date).copy()

    fc["startTime"] = pd.to_datetime(fc["startTime"], utc=True)
    fc["publishTime"] = pd.to_datetime(fc["publishTime"], utc=True)
    act["startTime"] = pd.to_datetime(act["startTime"], utc=True)

    # Compute horizon in hours
    fc["horizon_h"] = (fc["startTime"] - fc["publishTime"]).dt.total_seconds() / 3600.0

    # Exclude negative horizons
    fc = fc[fc["horizon_h"] >= 0].copy()

    # Expand each hourly forecast to :00 and :30 half-hourly keys.
    # The :00 key is the forecast's startTime; :30 key is startTime + 30 min.
    # The :30 row's actual delivery is 30 min further into the future, so its
    # true horizon is 0.5 h larger than the :00 row's horizon.
    rows_00 = fc.copy()
    rows_30 = fc.copy()
    rows_30["startTime"] = rows_30["startTime"] + pd.Timedelta(minutes=30)
    rows_30["horizon_h"] = rows_30["horizon_h"] + 0.5

    expanded = pd.concat([rows_00, rows_30], ignore_index=True)

    # Join with actuals
    joined = expanded.merge(
        act[["startTime", "generation_mw"]].rename(columns={"generation_mw": "actual_mw"}),
        on="startTime",
        how="inner",
    ).dropna(subset=["generation_mw", "actual_mw"])

    joined["error"] = joined["generation_mw"] - joined["actual_mw"]

    # Assign buckets
    joined["bucket"] = joined["horizon_h"].apply(_assign_bucket)
    joined = joined.dropna(subset=["bucket"])

    result: dict[str, MetricSet] = {}
    for label, _, _ in HORIZON_BUCKETS:
        subset = joined[joined["bucket"] == label]
        if subset.empty:
            result[label] = _empty_metric_set()
        else:
            errors = subset["error"].to_numpy(dtype=float)
            actuals = subset["actual_mw"].to_numpy(dtype=float)
            result[label] = _compute_metrics(errors, actuals, n_excluded=0)

    return result
