"""
routers/accuracy.py — GET /api/accuracy/*

Four sub-endpoints:
  /api/accuracy/summary    — overall MetricSet + suggested reserve buffer
  /api/accuracy/by-hour    — grouped by hour-of-day (Europe/London)
  /api/accuracy/by-date    — grouped by delivery date
  /api/accuracy/by-horizon — grouped by horizon bucket (all publishTimes)

All decision-time endpoints accept an optional cutoff_hour parameter so the
UI's what-if selector propagates through to accuracy numbers.

NaN-to-None conversion:
  MetricSet stores NaN (not None) when a bucket is empty.  We convert to
  JSON null via _ms_to_response() before sending to the client.

suggested_buffer_mw:
  Defined as max(0, signed_p95).  signed_p95 is the 95th percentile of signed
  errors (forecast - actual).  Positive error = over-forecast = buyer is short
  (expected more wind than materialised).  This reserve covers 95 % of
  over-forecast shortfall events.

surplus_risk_mw:
  Defined as max(0, -signed_p5).  -signed_p5 is the 95th percentile of the
  under-forecast magnitude (actual exceeded forecast).  The buyer had more
  wind than expected and may need to spill or sell the surplus.
"""

from __future__ import annotations

import math
from datetime import date as _date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.data_cache import get_actuals, get_forecasts, get_selection
from app.metrics import (
    MetricSet,
    decision_time_accuracy,
    decision_time_by_date,
    decision_time_by_hour,
    horizon_accuracy,
)

router = APIRouter(prefix="/accuracy", tags=["accuracy"])


# ---------------------------------------------------------------------------
# Shared response model
# ---------------------------------------------------------------------------


class MetricSetResponse(BaseModel):
    """JSON-serialisable version of MetricSet (NaN replaced by null)."""

    n_matched: int
    n_excluded: int
    mae: float | None
    rmse: float | None
    bias: float | None
    mae_pct: float | None
    abs_p50: float | None
    abs_p90: float | None
    abs_p95: float | None
    signed_p5: float | None
    signed_p50: float | None
    signed_p95: float | None


def _ms_to_response(ms: MetricSet) -> MetricSetResponse:
    """Convert a MetricSet (may contain NaN) to a JSON-safe response model."""

    def n(v: float) -> float | None:
        return None if math.isnan(v) else float(v)

    return MetricSetResponse(
        n_matched=ms.n_matched,
        n_excluded=ms.n_excluded,
        mae=n(ms.mae),
        rmse=n(ms.rmse),
        bias=n(ms.bias),
        mae_pct=n(ms.mae_pct),
        abs_p50=n(ms.abs_p50),
        abs_p90=n(ms.abs_p90),
        abs_p95=n(ms.abs_p95),
        signed_p5=n(ms.signed_p5),
        signed_p50=n(ms.signed_p50),
        signed_p95=n(ms.signed_p95),
    )


# ---------------------------------------------------------------------------
# Shared validation helpers
# ---------------------------------------------------------------------------


def _parse_date(date_str: str, field: str = "date") -> _date:
    """Parse a YYYY-MM-DD string and validate it is within the allowed range."""
    try:
        d = _date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format for '{field}': '{date_str}'. Expected YYYY-MM-DD.",
        )
    if d < settings.START_DATE or d > settings.END_DATE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{field}' {date_str} is outside the allowed range "
                f"{settings.START_DATE} to {settings.END_DATE}."
            ),
        )
    return d


def _validate_range(start_str: str, end_str: str) -> tuple[_date, _date]:
    """Parse and validate start/end dates; enforce start <= end."""
    start = _parse_date(start_str, "start")
    end = _parse_date(end_str, "end")
    if start > end:
        raise HTTPException(
            status_code=400,
            detail=f"'start' ({start_str}) must be on or before 'end' ({end_str}).",
        )
    return start, end


def _validate_cutoff(cutoff_hour: int) -> None:
    if not (0 <= cutoff_hour <= 23):
        raise HTTPException(
            status_code=400,
            detail=f"cutoff_hour must be an integer 0-23, got {cutoff_hour}.",
        )


# ---------------------------------------------------------------------------
# /accuracy/summary
# ---------------------------------------------------------------------------


class AccuracySummaryResponse(BaseModel):
    """Overall decision-time accuracy for a date range."""

    start: str
    end: str
    cutoff_hour: int
    metrics: MetricSetResponse
    suggested_buffer_mw: float | None
    suggested_buffer_explanation: str
    surplus_risk_mw: float | None
    surplus_risk_explanation: str


@router.get(
    "/summary",
    response_model=AccuracySummaryResponse,
    summary="Overall decision-time accuracy",
)
def get_accuracy_summary(
    start: str = Query(..., description="Start delivery date YYYY-MM-DD"),
    end: str = Query(..., description="End delivery date YYYY-MM-DD"),
    cutoff_hour: int = Query(
        default=settings.DECISION_CUTOFF_HOUR,
        description="Decision cutoff hour 0-23 (Europe/London)",
    ),
) -> AccuracySummaryResponse:
    """
    Overall accuracy of the D-1 decision-time forecast over a date range.

    ``suggested_buffer_mw`` is the 95th percentile of over-forecast error
    (= ``signed_p95``).  Over-forecast means forecast > actual, so the buyer
    bought less conventional power than needed and is short.  Holding this
    reserve covers 95 % of historical shortfall events.

    ``surplus_risk_mw`` is the 95th percentile of under-forecast magnitude
    (= ``-signed_p5``).  Under-forecast means actual > forecast, so the buyer
    has more wind than planned and may need to spill or sell.
    """
    _validate_cutoff(cutoff_hour)
    start_date, end_date = _validate_range(start, end)

    ms = decision_time_accuracy(get_selection(cutoff_hour), get_actuals(), start_date, end_date)
    ms_resp = _ms_to_response(ms)

    # ── Suggested reserve buffer (over-forecast / shortfall tail) ──────────
    if ms_resp.signed_p95 is not None:
        buffer = max(0.0, ms_resp.signed_p95)
        buffer_explanation = (
            f"In {start} to {end}, 95% of over-forecast shortfalls were smaller than "
            f"{buffer:,.0f} MW; holding this reserve covers those events."
        )
    else:
        buffer = None
        buffer_explanation = "Insufficient matched data to compute a buffer recommendation."

    # ── Surplus risk (under-forecast / excess-wind tail) ───────────────────
    if ms_resp.signed_p5 is not None:
        surplus = max(0.0, -ms_resp.signed_p5)
        surplus_explanation = (
            f"In {start} to {end}, 95% of cases where wind exceeded the forecast "
            f"had a surplus smaller than {surplus:,.0f} MW."
        )
    else:
        surplus = None
        surplus_explanation = "Insufficient matched data to compute surplus risk."

    return AccuracySummaryResponse(
        start=start,
        end=end,
        cutoff_hour=cutoff_hour,
        metrics=ms_resp,
        suggested_buffer_mw=buffer,
        suggested_buffer_explanation=buffer_explanation,
        surplus_risk_mw=surplus,
        surplus_risk_explanation=surplus_explanation,
    )


# ---------------------------------------------------------------------------
# /accuracy/by-hour
# ---------------------------------------------------------------------------


class HourEntry(BaseModel):
    """Metrics for one hour of day (Europe/London, 0-23)."""

    hour: int
    metrics: MetricSetResponse


class AccuracyByHourResponse(BaseModel):
    start: str
    end: str
    cutoff_hour: int
    by_hour: list[HourEntry]


@router.get(
    "/by-hour",
    response_model=AccuracyByHourResponse,
    summary="Decision-time accuracy by hour of day",
)
def get_accuracy_by_hour(
    start: str = Query(...),
    end: str = Query(...),
    cutoff_hour: int = Query(default=settings.DECISION_CUTOFF_HOUR),
) -> AccuracyByHourResponse:
    """
    Accuracy grouped by hour of day in Europe/London time (0-23).

    All 24 hours are always present; hours with no matched data have
    ``n_matched=0`` and null metric fields.
    """
    _validate_cutoff(cutoff_hour)
    start_date, end_date = _validate_range(start, end)

    by_hour = decision_time_by_hour(
        get_selection(cutoff_hour), get_actuals(), start_date, end_date
    )
    return AccuracyByHourResponse(
        start=start,
        end=end,
        cutoff_hour=cutoff_hour,
        by_hour=[
            HourEntry(hour=h, metrics=_ms_to_response(ms))
            for h, ms in sorted(by_hour.items())
        ],
    )


# ---------------------------------------------------------------------------
# /accuracy/by-date
# ---------------------------------------------------------------------------


class DateEntry(BaseModel):
    """Metrics for one delivery date."""

    date: str  # YYYY-MM-DD
    metrics: MetricSetResponse


class AccuracyByDateResponse(BaseModel):
    start: str
    end: str
    cutoff_hour: int
    by_date: list[DateEntry]


@router.get(
    "/by-date",
    response_model=AccuracyByDateResponse,
    summary="Decision-time accuracy by delivery date",
)
def get_accuracy_by_date(
    start: str = Query(...),
    end: str = Query(...),
    cutoff_hour: int = Query(default=settings.DECISION_CUTOFF_HOUR),
) -> AccuracyByDateResponse:
    """Accuracy grouped by delivery date, sorted chronologically."""
    _validate_cutoff(cutoff_hour)
    start_date, end_date = _validate_range(start, end)

    by_date = decision_time_by_date(
        get_selection(cutoff_hour), get_actuals(), start_date, end_date
    )
    return AccuracyByDateResponse(
        start=start,
        end=end,
        cutoff_hour=cutoff_hour,
        by_date=[
            DateEntry(date=str(d), metrics=_ms_to_response(ms))
            for d, ms in sorted(by_date.items())
        ],
    )


# ---------------------------------------------------------------------------
# /accuracy/by-horizon
# ---------------------------------------------------------------------------


class HorizonEntry(BaseModel):
    """Metrics for one forecast-horizon bucket."""

    bucket: str  # "0-6h", "6-12h", "12-24h", "24-36h", "36-48h", "48h+"
    metrics: MetricSetResponse


class AccuracyByHorizonResponse(BaseModel):
    start: str
    end: str
    by_horizon: list[HorizonEntry]


@router.get(
    "/by-horizon",
    response_model=AccuracyByHorizonResponse,
    summary="Accuracy by forecast-horizon bucket (all publishTimes)",
)
def get_accuracy_by_horizon(
    start: str = Query(...),
    end: str = Query(...),
) -> AccuracyByHorizonResponse:
    """
    Accuracy grouped by horizon bucket using ALL WINDFOR forecast rows.

    Buckets (left-inclusive, right-exclusive):
      0-6h | 6-12h | 12-24h | 24-36h | 36-48h | 48h+

    No ``cutoff_hour`` parameter — every publishTime is used.
    Rows with horizon < 0 (re-published past periods) are excluded.
    All six bucket labels are always present; empty ones have ``n_matched=0``
    and null metric fields.
    """
    start_date, end_date = _validate_range(start, end)

    by_horizon = horizon_accuracy(get_forecasts(), get_actuals(), start_date, end_date)
    return AccuracyByHorizonResponse(
        start=start,
        end=end,
        by_horizon=[
            HorizonEntry(bucket=bucket, metrics=_ms_to_response(ms))
            for bucket, ms in by_horizon.items()
        ],
    )
