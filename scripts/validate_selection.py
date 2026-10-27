"""Real-data validation for the selection logic.

Runs select_january_forecasts on the committed Elexon snapshot and prints:
  - Missing half-hours per delivery day across January
  - Min / max horizon_hours of selected forecasts
  - 6-row sample for 2026-01-15

Run from the repo root:
    python scripts/validate_selection.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "backend"))

import pandas as pd
from app.selection import load_forecasts, select_january_forecasts

forecasts = load_forecasts()
sel = select_january_forecasts(forecasts, cutoff_hour=9)

assert len(sel) == 1488, f"Expected 1488, got {len(sel)}"

# ── Missing half-hours per day ────────────────────────────────────────────────
sel["delivery_date"] = sel["startTime"].dt.date
missing_per_day = (
    sel.groupby("delivery_date")["missing_forecast"].sum().rename("missing_hh")
)

print("\n=== Missing half-hours per delivery day (cutoff 09:00) ===")
print(missing_per_day.to_string())
total_missing = int(missing_per_day.sum())
print(f"\nTotal missing across January : {total_missing} / 1488")
print(f"Total present               : {1488 - total_missing} / 1488")

# ── Horizon stats ─────────────────────────────────────────────────────────────
present = sel[~sel["missing_forecast"]]
print("\n=== Forecast horizon (startTime - publishTime) for selected rows ===")
print(f"  Count   : {len(present):,}")
print(f"  Min     : {present['horizon_hours'].min():.2f} h")
print(f"  p25     : {present['horizon_hours'].quantile(0.25):.2f} h")
print(f"  Median  : {present['horizon_hours'].median():.2f} h")
print(f"  p75     : {present['horizon_hours'].quantile(0.75):.2f} h")
print(f"  Max     : {present['horizon_hours'].max():.2f} h")

# ── 6-row sample for 2026-01-15 ───────────────────────────────────────────────
jan15 = sel[sel["delivery_date"] == pd.Timestamp("2026-01-15").date()].head(6)
print("\n=== Sample: first 6 slots for 2026-01-15 ===")
print(jan15[["startTime", "forecast_mw", "publishTime", "horizon_hours",
             "missing_forecast"]].to_string(index=False))
