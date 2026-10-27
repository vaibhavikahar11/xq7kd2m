"""Elexon Insights API client.

Verified endpoints (confirmed by live test calls on 2026-10-27, no guessing):

FUELHH (half-hourly generation outturn by fuel type)
  URL    : GET https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH
  Params : settlementDateFrom  str  "yyyy-MM-dd"
           settlementDateTo    str  "yyyy-MM-dd"
           format              str  "json"
  Fields : publishTime (ISO-8601 UTC), startTime (ISO-8601 UTC),
           settlementDate, settlementPeriod, fuelType, generation (int MW)
  Note   : Returns ALL fuel types; filter to fuelType=="WIND" client-side.
  Res.   : 30-minute half-hours.

WINDFOR (wind generation forecast)
  URL    : GET https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR
  Params : publishDateTimeFrom  str  ISO-8601 UTC
           publishDateTimeTo    str  ISO-8601 UTC
           format               str  "json"
  Fields : publishTime (ISO-8601 UTC), startTime (ISO-8601 UTC),
           generation (int MW)
  Note   : Returns every publishTime revision in the window; no de-dup.
           startTime in the response may extend beyond the publish window.
  Res.   : 1-hour (NOT 30-minute – see quality report for implications).

No API key required for either endpoint.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"

# ── Chunking ────────────────────────────────────────────────────────────────
# Keep individual response bodies small and avoid any implicit server limits.
FUELHH_CHUNK_DAYS: int = 7   # 7 settlement-days per FUELHH request
WINDFOR_CHUNK_DAYS: int = 3  # 3 publish-days per WINDFOR request

# ── HTTP settings ────────────────────────────────────────────────────────────
_TIMEOUT_S: float = 30.0
_MAX_RETRIES: int = 4
_BACKOFF_BASE_S: float = 2.0          # doubles on each retry
_RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


# ── Pydantic response models ─────────────────────────────────────────────────

class FuelHHRow(BaseModel):
    """One FUELHH record, pre-filtered to fuelType == 'WIND'."""

    publishTime: datetime   # UTC; approx startTime + 30 min
    startTime: datetime     # UTC; start of the 30-minute half-hour
    fuelType: str           # always "WIND" when returned by this client
    generation: int         # MW; positive = generation, negative unusual for WIND


class WindForRow(BaseModel):
    """One WINDFOR record (a single forecast point at hourly resolution)."""

    publishTime: datetime   # UTC; when this forecast snapshot was issued
    startTime: datetime     # UTC; the hour being forecast (1-hour resolution)
    generation: int         # MW; forecast wind generation


# ── Low-level HTTP ───────────────────────────────────────────────────────────

def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET ``url`` with ``params``, returning parsed JSON.

    Retries up to ``_MAX_RETRIES`` times with exponential back-off on
    transient errors (network timeouts and retryable HTTP status codes).
    Raises on permanent client errors (4xx other than 429).

    Args:
        url: Full URL to request.
        params: Query parameters (values are URL-encoded automatically).

    Returns:
        Parsed JSON response as a dict.

    Raises:
        httpx.HTTPStatusError: On non-retryable HTTP errors.
        httpx.TimeoutException: If all retries time out.
    """
    delay = _BACKOFF_BASE_S
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=_TIMEOUT_S) as client:
                resp = client.get(url, params=params)

            if resp.status_code in _RETRYABLE_STATUSES:
                logger.warning(
                    "HTTP %s on attempt %d/%d; retrying in %.1f s",
                    resp.status_code, attempt, _MAX_RETRIES, delay,
                )
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
            else:
                resp.raise_for_status()
                return resp.json()

        except httpx.TimeoutException as exc:
            logger.warning(
                "Timeout on attempt %d/%d; retrying in %.1f s",
                attempt, _MAX_RETRIES, delay,
            )
            last_exc = exc

        if attempt < _MAX_RETRIES:
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"All {_MAX_RETRIES} retries exhausted") from last_exc


# ── Public fetchers ──────────────────────────────────────────────────────────

def fetch_fuelhh_wind(
    date_from: date,
    date_to: date,
    *,
    chunk_days: int = FUELHH_CHUNK_DAYS,
) -> list[FuelHHRow]:
    """Fetch FUELHH WIND actuals for settlement dates in [date_from, date_to].

    Chunked into ``chunk_days``-day windows.  Only rows with
    ``fuelType == "WIND"`` are returned; all other fuel types are dropped
    client-side (the API does not support server-side fuel-type filtering).

    Args:
        date_from: First settlement date (inclusive).
        date_to: Last settlement date (inclusive).
        chunk_days: Number of settlement days per API request.

    Returns:
        Flat list of :class:`FuelHHRow` objects, one per 30-minute half-hour,
        all timestamps in UTC.
    """
    rows: list[FuelHHRow] = []
    cursor = date_from

    while cursor <= date_to:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), date_to)
        logger.info("FUELHH  %s → %s", cursor.isoformat(), chunk_end.isoformat())

        payload = _get_json(
            f"{BASE_URL}/datasets/FUELHH",
            {
                "settlementDateFrom": cursor.isoformat(),
                "settlementDateTo": chunk_end.isoformat(),
                "format": "json",
            },
        )

        for rec in payload.get("data", []):
            if rec.get("fuelType") == "WIND":
                rows.append(
                    FuelHHRow(
                        publishTime=rec["publishTime"],
                        startTime=rec["startTime"],
                        fuelType=rec["fuelType"],
                        generation=rec["generation"],
                    )
                )

        cursor = chunk_end + timedelta(days=1)

    logger.info("FUELHH  fetched %d WIND rows total", len(rows))
    return rows


def fetch_windfor(
    publish_from: datetime,
    publish_to: datetime,
    *,
    chunk_days: int = WINDFOR_CHUNK_DAYS,
) -> list[WindForRow]:
    """Fetch all WINDFOR forecast rows published in [publish_from, publish_to).

    Every distinct ``publishTime`` revision is retained (no de-duplication)
    so that the cutoff-selection logic can pick the correct snapshot for any
    given decision time.

    The caller is responsible for filtering the returned rows to the
    ``startTime`` range of interest (January 2026), because a single
    publishTime window can contain startTimes that span several days ahead.

    Args:
        publish_from: Start of publish-time window (inclusive), UTC.
        publish_to: End of publish-time window (exclusive), UTC.
        chunk_days: Width of each publish-time chunk in days.

    Returns:
        Flat list of :class:`WindForRow` objects, all timestamps in UTC.
        startTime resolution is 1-hour (NOT 30-minute).
    """
    rows: list[WindForRow] = []
    cursor = publish_from

    while cursor < publish_to:
        chunk_end = min(cursor + timedelta(days=chunk_days), publish_to)
        logger.info(
            "WINDFOR  publish %s → %s",
            cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
            chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        payload = _get_json(
            f"{BASE_URL}/datasets/WINDFOR",
            {
                "publishDateTimeFrom": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "publishDateTimeTo": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "format": "json",
            },
        )

        for rec in payload.get("data", []):
            rows.append(
                WindForRow(
                    publishTime=rec["publishTime"],
                    startTime=rec["startTime"],
                    generation=rec["generation"],
                )
            )

        cursor = chunk_end

    logger.info("WINDFOR  fetched %d rows total (before startTime filter)", len(rows))
    return rows
