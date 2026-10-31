"""
routers/decision.py — GET /api/decision

Returns the 48 half-hourly decision-time wind forecasts for one delivery day,
together with actual generation values and a day summary.

Selection rule (mirroring selection.py):
  For each hourly startTime on delivery day D, pick the WINDFOR row with the
  latest publishTime that is <= the D-1 cutoff_hour cutoff in Europe/London.
  The hourly forecast is then replicated to BOTH the :00 and :30 half-hours.

Missing-data policy:
  If no eligible forecast exists, forecast_mw and publishTime are null and
  missing_forecast=True.  actual_mw is null if the actuals snapshot has no
  matching row (not expected in January 2026, but surfaced explicitly).
"""

from __future__ import annotations

import math
from datetime import date as _date
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.data_cache import get_actuals, get_selection
from app.selection import compute_cutoff_utc

router = APIRouter(tags=["decision"])

_LONDON = ZoneInfo("Europe/London")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class HalfHourRow(BaseModel):
    """One half-hourly slot in the decision-time forecast."""

    startTime: str            # ISO-8601 UTC
    forecast_mw: float | None
    actual_mw: float | None   # null if actuals snapshot has no matching row
    publishTime: str | None   # ISO-8601 UTC; null when missing_forecast=True
    horizon_hours: float | None
    missing_forecast: bool


class DaySummary(BaseModel):
    """Day-level aggregate statistics."""

    peak_forecast_mw: float | None
    avg_forecast_mw: float | None
    total_forecast_mwh: float | None   # sum(forecast_mw) / 2  (30-min → MWh)
    peak_actual_mw: float | None
    avg_actual_mw: float | None
    total_actual_mwh: float | None
    missing_half_hours: int            # count of missing_forecast=True


class DecisionResponse(BaseModel):
    """Full decision-time forecast response for one delivery day."""

    date: str             # YYYY-MM-DD
    cutoff_hour: int
    cutoff_utc: str       # ISO-8601 UTC
    cutoff_local: str     # ISO-8601 Europe/London
    rows: list[HalfHourRow]
    summary: DaySummary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _nan_to_none(v: object) -> float | None:
    """Convert NaN / None to None; otherwise return float."""
    if v is None:
        return None
    try:
        f = float(v)  # type: ignore[arg-type]
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _ts_to_iso(ts: object) -> str | None:
    """Convert a pandas Timestamp (or NaT / None) to an ISO-8601 UTC string."""
    if ts is None:
        return None
    try:
        if pd.isna(ts):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    pt = pd.Timestamp(ts)  # type: ignore[arg-type]
    if pd.isna(pt):
        return None
    return pt.tz_convert("UTC").isoformat()


def _validate_date(date_str: str) -> _date:
    """Parse and range-check a YYYY-MM-DD string; raise 400 on failure."""
    try:
        d = _date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format '{date_str}'. Expected YYYY-MM-DD.",
        )
    if d < settings.START_DATE or d > settings.END_DATE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Date {date_str} is outside the allowed range "
                f"{settings.START_DATE} to {settings.END_DATE}."
            ),
        )
    return d


def _validate_cutoff(cutoff_hour: int) -> None:
    if not (0 <= cutoff_hour <= 23):
        raise HTTPException(
            status_code=400,
            detail=f"cutoff_hour must be an integer 0-23, got {cutoff_hour}.",
        )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/decision",
    response_model=DecisionResponse,
    summary="Day-ahead forecast for one delivery day",
)
def get_decision(
    date: str = Query(
        ...,
        description="Delivery date YYYY-MM-DD, within 2026-01-01 to 2026-01-31",
    ),
    cutoff_hour: int = Query(
        default=settings.DECISION_CUTOFF_HOUR,
        description="Decision cutoff hour 0-23 (Europe/London); default 9",
    ),
) -> DecisionResponse:
    """
    Return the 48 half-hourly decision-time wind forecasts for a delivery day.

    For each hourly delivery period the latest WINDFOR forecast published at or
    before ``cutoff_hour`` on D-1 is selected.  The value is replicated to
    both the :00 and :30 half-hours (no interpolation).

    ``actual_mw`` is joined from the committed FUELHH actuals snapshot.
    Both ``forecast_mw`` and ``actual_mw`` are null (with ``missing_forecast``
    or ``actual_mw=null``) when the respective data is absent — never imputed.
    """
    _validate_cutoff(cutoff_hour)
    delivery_date = _validate_date(date)

    # --- Retrieve cached data -----------------------------------------------
    selection_df = get_selection(cutoff_hour)
    actuals_df = get_actuals()

    sel = selection_df.copy()
    sel["startTime"] = pd.to_datetime(sel["startTime"], utc=True)

    # Filter to delivery day (UTC date == UK date throughout January 2026)
    day_sel = sel[sel["startTime"].dt.date == delivery_date].copy()
    if day_sel.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No selection data found for {date}.",
        )

    # Join actuals
    act = actuals_df.copy()
    act["startTime"] = pd.to_datetime(act["startTime"], utc=True)
    merged = day_sel.merge(
        act[["startTime", "generation_mw"]].rename(columns={"generation_mw": "actual_mw"}),
        on="startTime",
        how="left",
    ).sort_values("startTime")

    # --- Build rows ---------------------------------------------------------
    rows: list[HalfHourRow] = []
    for _, r in merged.iterrows():
        rows.append(
            HalfHourRow(
                startTime=r["startTime"].tz_convert("UTC").isoformat(),
                forecast_mw=_nan_to_none(r.get("forecast_mw")),
                actual_mw=_nan_to_none(r.get("actual_mw")),
                publishTime=_ts_to_iso(r.get("publishTime")),
                horizon_hours=_nan_to_none(r.get("horizon_hours")),
                missing_forecast=bool(r.get("missing_forecast", False)),
            )
        )

    # --- Day summary --------------------------------------------------------
    fc_vals = [r.forecast_mw for r in rows if r.forecast_mw is not None]
    ac_vals = [r.actual_mw for r in rows if r.actual_mw is not None]

    def _mean(vals: list[float]) -> float | None:
        return sum(vals) / len(vals) if vals else None

    summary = DaySummary(
        peak_forecast_mw=max(fc_vals) if fc_vals else None,
        avg_forecast_mw=_mean(fc_vals),
        total_forecast_mwh=(sum(fc_vals) / 2.0) if fc_vals else None,
        peak_actual_mw=max(ac_vals) if ac_vals else None,
        avg_actual_mw=_mean(ac_vals),
        total_actual_mwh=(sum(ac_vals) / 2.0) if ac_vals else None,
        missing_half_hours=sum(1 for r in rows if r.missing_forecast),
    )

    # --- Cutoff timestamps --------------------------------------------------
    cutoff_utc = compute_cutoff_utc(delivery_date, cutoff_hour)
    cutoff_local = cutoff_utc.astimezone(_LONDON)

    return DecisionResponse(
        date=str(delivery_date),
        cutoff_hour=cutoff_hour,
        cutoff_utc=cutoff_utc.isoformat(),
        cutoff_local=cutoff_local.isoformat(),
        rows=rows,
        summary=summary,
    )
