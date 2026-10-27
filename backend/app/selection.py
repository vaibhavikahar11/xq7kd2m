"""Forecast cutoff-selection logic for the Wind Forecast Portal.

WINDFOR vs. FUELHH resolution mismatch
---------------------------------------
WINDFOR provides forecasts at **1-hour** intervals
(startTime: 00:00, 01:00, ..., 23:00 UTC).
FUELHH actuals are at **30-minute** intervals
(startTime: 00:00, 00:30, 01:00, ..., 23:30 UTC).

To produce the required 48 half-hourly rows per delivery day, this module
expands each hourly forecast to cover both the :00 and the :30 slot of that
hour with the **same forecast_mw value**.  No interpolation is applied:

    WINDFOR row: startTime = 2026-01-15 05:00 UTC, generation_mw = 5 000
    ↓ expansion
    HalfHourSlot: startTime = 2026-01-15 05:00 UTC, forecast_mw = 5 000
    HalfHourSlot: startTime = 2026-01-15 05:30 UTC, forecast_mw = 5 000

If an hour has no eligible forecast, both its :00 and :30 slots carry
``forecast_mw = None`` and ``missing_forecast = True``.

Decision-cutoff rule
---------------------
For delivery day D (a UK-local calendar date in Europe/London), the cutoff
is computed as:

    cutoff_utc = datetime(D-1, cutoff_hour, 0, 0, tzinfo=LONDON_TZ).astimezone(UTC)

For each hourly startTime H on day D, the selected forecast is the row in
the WINDFOR snapshot whose:

* ``startTime == H``, **and**
* ``publishTime <= cutoff_utc``  (strictly: anything published after the
  cutoff is excluded — no look-ahead bias)
* ``publishTime`` is the **maximum** among all eligible rows (most recent
  revision).

Tiebreak: if two rows share the maximum publishTime (API-level duplicate),
the one with the higher ``generation_mw`` is chosen for determinism.

The ``cutoff_hour`` parameter is exposed on every public function so the
UI's "what-if" cutoff selector can recompute the selection from the raw
snapshot without re-fetching from Elexon.

horizon_hours definition
-------------------------
``horizon_hours = (slot.startTime − publishTime).total_seconds() / 3600``

For the :30 expansion of an hourly slot, horizon_hours is 0.5 h larger
than for the corresponding :00 slot, by definition.  Both are stored.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from app.config import settings

log = logging.getLogger(__name__)

LONDON_TZ: ZoneInfo = ZoneInfo("Europe/London")
JANUARY_2026_DATES: list[date] = [date(2026, 1, d) for d in range(1, 32)]


# ── Result type ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HalfHourSlot:
    """One 30-minute delivery slot with its selected forecast.

    Attributes:
        startTime:        UTC datetime of this half-hour (:00 or :30).
        forecast_mw:      Forecast wind generation in MW.  ``None`` when
                          ``missing_forecast`` is ``True``.
        publishTime:      UTC datetime of the selected WINDFOR revision.
                          ``None`` when ``missing_forecast`` is ``True``.
        horizon_hours:    ``(startTime − publishTime)`` in decimal hours.
                          Positive = forecast was made before delivery.
                          ``None`` when ``missing_forecast`` is ``True``.
        missing_forecast: ``True`` iff no eligible forecast existed for
                          this slot.  Data is never imputed.
    """

    startTime: datetime
    forecast_mw: Optional[int]
    publishTime: Optional[datetime]
    horizon_hours: Optional[float]
    missing_forecast: bool


# ── Internal helpers ──────────────────────────────────────────────────────────


def compute_cutoff_utc(delivery_date: date, cutoff_hour: int) -> datetime:
    """Convert D-1 cutoff_hour in Europe/London to a UTC datetime.

    Args:
        delivery_date: The day power is delivered (day D).
        cutoff_hour:   Hour of the cutoff (0-23) in Europe/London local time.

    Returns:
        UTC-aware :class:`datetime` of the decision cutoff.

    Example:
        >>> compute_cutoff_utc(date(2026, 1, 15), 9)
        datetime(2026, 1, 14, 9, 0, tzinfo=timezone.utc)
        # January is GMT, so London == UTC.
    """
    d_minus_1 = delivery_date - timedelta(days=1)
    cutoff_local = datetime(
        d_minus_1.year,
        d_minus_1.month,
        d_minus_1.day,
        cutoff_hour,
        0,
        0,
        tzinfo=LONDON_TZ,
    )
    return cutoff_local.astimezone(timezone.utc)


def _delivery_hours_utc(delivery_date: date) -> list[datetime]:
    """Return the 24 UTC hourly datetimes that compose delivery day D.

    Computed from Europe/London midnight so any DST transitions (irrelevant
    in January, but correct in the general case) are handled automatically.
    """
    midnight_local = datetime(
        delivery_date.year,
        delivery_date.month,
        delivery_date.day,
        0,
        0,
        0,
        tzinfo=LONDON_TZ,
    )
    return [
        (midnight_local + timedelta(hours=h)).astimezone(timezone.utc)
        for h in range(24)
    ]


# ── Public selection functions ────────────────────────────────────────────────


def select_day_forecast(
    delivery_date: date,
    forecast_df: pd.DataFrame,
    *,
    cutoff_hour: int = settings.DECISION_CUTOFF_HOUR,
) -> list[HalfHourSlot]:
    """Select the cutoff forecast for every half-hour on *delivery_date*.

    See the module docstring for the full selection rule.

    Args:
        delivery_date: UK local date of power delivery (day D).
        forecast_df:   DataFrame with columns ``[startTime, publishTime,
                       generation_mw]``.  ``startTime`` and ``publishTime``
                       must be UTC-aware (``datetime64[ns, UTC]``).
        cutoff_hour:   Decision cutoff hour in Europe/London (0-23).
                       Defaults to ``settings.DECISION_CUTOFF_HOUR`` (9).
                       Pass a different value for what-if analysis.

    Returns:
        List of exactly 48 :class:`HalfHourSlot` objects sorted by
        ``startTime`` ascending.

    Raises:
        AssertionError: If the returned list does not contain exactly 48 rows
                        (indicates a bug in the expansion logic).
    """
    cutoff = compute_cutoff_utc(delivery_date, cutoff_hour)
    hours_utc = _delivery_hours_utc(delivery_date)

    # Pre-filter once: rows published at or before the cutoff.
    eligible = forecast_df.loc[forecast_df["publishTime"] <= cutoff]

    slots: list[HalfHourSlot] = []

    for hour_utc in hours_utc:
        # Rows whose startTime matches this delivery hour exactly.
        candidates = eligible.loc[eligible["startTime"] == hour_utc]

        if candidates.empty:
            # No eligible forecast for this hour — flag both half-hours.
            for minute in (0, 30):
                slots.append(
                    HalfHourSlot(
                        startTime=hour_utc + timedelta(minutes=minute),
                        forecast_mw=None,
                        publishTime=None,
                        horizon_hours=None,
                        missing_forecast=True,
                    )
                )
        else:
            # Select the most recent eligible revision.
            # Secondary sort on generation_mw breaks publishTime ties
            # deterministically (higher generation wins).
            best = candidates.sort_values(
                ["publishTime", "generation_mw"], ascending=True
            ).iloc[-1]

            pub_time: datetime = best["publishTime"].to_pydatetime()
            gen_mw: int = int(best["generation_mw"])

            # Expand to :00 and :30 half-hours.
            for minute in (0, 30):
                half_hour = hour_utc + timedelta(minutes=minute)
                horizon_h = round(
                    (half_hour - pub_time).total_seconds() / 3600.0, 4
                )
                slots.append(
                    HalfHourSlot(
                        startTime=half_hour,
                        forecast_mw=gen_mw,
                        publishTime=pub_time,
                        horizon_hours=horizon_h,
                        missing_forecast=False,
                    )
                )

    assert len(slots) == 48, f"Expected 48 slots for {delivery_date}, got {len(slots)}"
    return slots


def select_january_forecasts(
    forecast_df: pd.DataFrame,
    *,
    cutoff_hour: int = settings.DECISION_CUTOFF_HOUR,
) -> pd.DataFrame:
    """Build the complete forecast selection for all 31 days of January 2026.

    Calls :func:`select_day_forecast` for each date in
    :data:`JANUARY_2026_DATES` and concatenates the results.

    Args:
        forecast_df:  DataFrame with columns ``[startTime, publishTime,
                      generation_mw]``, UTC-aware.
        cutoff_hour:  Decision cutoff hour in Europe/London.  Pass a value
                      other than the default to power the UI what-if selector.

    Returns:
        DataFrame with **1 488 rows** (31 × 48) and columns:
        ``[startTime, forecast_mw, publishTime, horizon_hours,
        missing_forecast]``.  ``startTime`` is UTC-aware.
    """
    records: list[dict] = []
    for d in JANUARY_2026_DATES:
        for slot in select_day_forecast(d, forecast_df, cutoff_hour=cutoff_hour):
            records.append(
                {
                    "startTime": slot.startTime,
                    "forecast_mw": slot.forecast_mw,
                    "publishTime": slot.publishTime,
                    "horizon_hours": slot.horizon_hours,
                    "missing_forecast": slot.missing_forecast,
                }
            )

    df = pd.DataFrame(records)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    # publishTime has NaT for missing slots; coerce to UTC-aware.
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    return df


# ── Module-level data loaders (warm-request cache) ────────────────────────────

_forecast_cache: Optional[pd.DataFrame] = None
_actuals_cache: Optional[pd.DataFrame] = None


def load_forecasts(path: Optional[object] = None) -> pd.DataFrame:
    """Load ``forecasts.csv.gz`` with a module-level in-memory cache.

    On the first call the file is read from disk and the result is cached.
    Subsequent calls (warm requests) return the cached DataFrame instantly.
    On Vercel, the cache is populated during the first request after a
    cold-start and reused for the lifetime of the function instance.

    Args:
        path: Optional path override (useful in tests).

    Returns:
        DataFrame with ``[startTime, publishTime, generation_mw]``,
        UTC-aware timestamps.
    """
    global _forecast_cache
    if _forecast_cache is None:
        file = path or (settings.DATA_DIR / "forecasts.csv.gz")
        log.info("Loading forecasts from %s", file)
        df = pd.read_csv(file, compression="gzip")
        df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
        df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
        _forecast_cache = df
    return _forecast_cache


def load_actuals(path: Optional[object] = None) -> pd.DataFrame:
    """Load ``actuals.csv.gz`` with a module-level in-memory cache.

    Args:
        path: Optional path override (useful in tests).

    Returns:
        DataFrame with ``[startTime, generation_mw]``, UTC-aware timestamps.
    """
    global _actuals_cache
    if _actuals_cache is None:
        file = path or (settings.DATA_DIR / "actuals.csv.gz")
        log.info("Loading actuals from %s", file)
        df = pd.read_csv(file, compression="gzip")
        df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
        _actuals_cache = df
    return _actuals_cache
