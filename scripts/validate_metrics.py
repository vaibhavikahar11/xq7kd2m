"""
validate_metrics.py — Smoke-test metrics.py on the real January 2026 snapshot.

Prints:
  1. Overall decision-time metrics
  2. Metrics per horizon bucket (n, MAE, RMSE, bias)
  3. Five worst delivery days by MAE

Run from the repo root:
  $env:PYTHONUTF8=1
  Set-Location backend
  .venv/Scripts/python ../scripts/validate_metrics.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow imports from backend/app/
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from datetime import date

import pandas as pd

from app.metrics import (
    decision_time_accuracy,
    decision_time_by_date,
    horizon_accuracy,
    MetricSet,
)
from app.selection import load_actuals, load_forecasts, select_january_forecasts

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

print("Loading data...")
forecast_df = load_forecasts()
actuals_df = load_actuals()
selection_df = select_january_forecasts(forecast_df, cutoff_hour=9)

JAN_START = date(2026, 1, 1)
JAN_END = date(2026, 1, 31)

# ---------------------------------------------------------------------------
# 1. Overall decision-time metrics
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("OVERALL DECISION-TIME METRICS (cutoff 09:00)")
print("=" * 60)

overall: MetricSet = decision_time_accuracy(selection_df, actuals_df, JAN_START, JAN_END)

print(f"  n_matched   : {overall.n_matched:,}")
print(f"  n_excluded  : {overall.n_excluded:,}")
print(f"  MAE         : {overall.mae:,.1f} MW")
print(f"  RMSE        : {overall.rmse:,.1f} MW")
print(f"  Bias        : {overall.bias:+,.1f} MW")
print(f"  MAE %       : {overall.mae_pct:.2f}%")
print(f"  |e| P50     : {overall.abs_p50:,.1f} MW")
print(f"  |e| P90     : {overall.abs_p90:,.1f} MW")
print(f"  |e| P95     : {overall.abs_p95:,.1f} MW")
print(f"  signed P5   : {overall.signed_p5:+,.1f} MW")
print(f"  signed P50  : {overall.signed_p50:+,.1f} MW")
print(f"  signed P95  : {overall.signed_p95:+,.1f} MW")

# ---------------------------------------------------------------------------
# 2. Horizon-bucket metrics
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("METRICS BY HORIZON BUCKET (all forecast rows)")
print("=" * 60)

buckets = horizon_accuracy(forecast_df, actuals_df, JAN_START, JAN_END)

header = f"{'Bucket':<10} {'n':>6}  {'MAE':>8}  {'RMSE':>8}  {'Bias':>8}"
print(header)
print("-" * len(header))
for label, ms in buckets.items():
    if ms.n_matched == 0:
        print(f"{label:<10} {'0':>6}  {'—':>8}  {'—':>8}  {'—':>8}")
    else:
        print(
            f"{label:<10} {ms.n_matched:>6,}  "
            f"{ms.mae:>8,.1f}  {ms.rmse:>8,.1f}  {ms.bias:>+8,.1f}"
        )

# ---------------------------------------------------------------------------
# 3. Five worst delivery days by MAE
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("5 WORST DELIVERY DAYS BY MAE")
print("=" * 60)

by_date = decision_time_by_date(selection_df, actuals_df, JAN_START, JAN_END)

worst = sorted(by_date.items(), key=lambda kv: kv[1].mae if not pd.isna(kv[1].mae) else -1, reverse=True)[:5]

print(f"{'Date':<14} {'n':>4}  {'MAE':>8}  {'RMSE':>8}  {'Bias':>8}")
print("-" * 50)
for d, ms in worst:
    print(
        f"{str(d):<14} {ms.n_matched:>4}  "
        f"{ms.mae:>8,.1f}  {ms.rmse:>8,.1f}  {ms.bias:>+8,.1f}"
    )

print("\nDone.")
