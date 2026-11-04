"""
data_cache.py — Module-level in-memory cache for Gridbricks API data.

Loads the compressed CSV snapshots from backend/data/ once at process startup.
Warm requests hit only in-memory DataFrames, so latency is negligible.

Path resolution is delegated to selection.load_forecasts / load_actuals, which
resolve relative to config.py (__file__), not the working directory.  This
means the same code works in local dev, Docker, and Vercel serverless.

Usage
-----
    from app.data_cache import startup, get_forecasts, get_actuals, get_selection
    # Call startup() once from the FastAPI lifespan handler (main.py).
    # Then call get_*() freely from any request handler.
"""

from __future__ import annotations

import pandas as pd

from app.config import settings
from app.selection import load_actuals, load_forecasts, select_january_forecasts

# Per-cutoff-hour selection cache: the UI exposes a what-if selector, so
# multiple cutoff values may be requested during a session.
_selection_cache: dict[int, pd.DataFrame] = {}


def get_forecasts() -> pd.DataFrame:
    """Return the raw WINDFOR forecast DataFrame (module-level cached)."""
    return load_forecasts()


def get_actuals() -> pd.DataFrame:
    """Return the FUELHH wind actuals DataFrame (module-level cached)."""
    return load_actuals()


def get_selection(cutoff_hour: int) -> pd.DataFrame:
    """
    Return the 1,488-row January 2026 selection DataFrame for *cutoff_hour*.

    Results are cached in a dict keyed by cutoff_hour so repeated requests
    with the same cutoff (default 9) return immediately without recomputing.
    """
    if cutoff_hour not in _selection_cache:
        _selection_cache[cutoff_hour] = select_january_forecasts(
            load_forecasts(), cutoff_hour=cutoff_hour
        )
    return _selection_cache[cutoff_hour]


def startup() -> None:
    """
    Pre-load all data into memory and warm the default cutoff cache.

    Called once from the FastAPI lifespan context so the first real request
    does not pay the CSV decompression cost.  On Vercel this runs during the
    cold start; subsequent invocations (warm) skip this entirely.
    """
    load_forecasts()
    load_actuals()
    get_selection(settings.DECISION_CUTOFF_HOUR)  # pre-warm the default cutoff
