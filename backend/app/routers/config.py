"""
routers/config.py — GET /api/config

Returns the active API configuration so the frontend can build its UI
(default cutoff, allowed date range, allowed cutoff range) without
hard-coding values that may change.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(tags=["config"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DateRange(BaseModel):
    """Inclusive allowed delivery date range."""

    start: str  # YYYY-MM-DD
    end: str


class CutoffHourRange(BaseModel):
    """Inclusive allowed cutoff_hour values (Europe/London)."""

    min: int
    max: int


class ConfigResponse(BaseModel):
    """Active API configuration snapshot."""

    default_cutoff_hour: int
    timezone: str
    allowed_date_range: DateRange
    allowed_cutoff_hour_range: CutoffHourRange


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="API configuration",
)
def get_config() -> ConfigResponse:
    """
    Return the active runtime configuration.

    The frontend uses this to initialise the date picker, the cutoff-hour
    selector default, and validation bounds — so there is a single source of
    truth in ``config.py`` rather than duplicated constants in the UI.
    """
    return ConfigResponse(
        default_cutoff_hour=settings.DECISION_CUTOFF_HOUR,
        timezone=settings.TIMEZONE,
        allowed_date_range=DateRange(
            start=str(settings.START_DATE),
            end=str(settings.END_DATE),
        ),
        allowed_cutoff_hour_range=CutoffHourRange(min=0, max=23),
    )
