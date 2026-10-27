"""Download and snapshot Elexon BMRS data for January 2026.

This is the ONLY place in the project that calls the Elexon Insights API.
All backend API endpoints serve data from the compressed CSV snapshots written
here; they never call Elexon at request time.

Usage
-----
    python scripts/fetch_data.py            # fetch everything
    python scripts/fetch_data.py --dry-run  # print plan, do not fetch

Outputs (written to backend/data/)
-----------------------------------
    actuals.csv.gz
        FUELHH WIND generation outturn, 30-minute resolution.
        Columns: startTime (UTC ISO-8601), generation_mw (int)

    forecasts.csv.gz
        WINDFOR wind generation forecasts, 1-hour resolution.
        Every distinct publishTime revision is retained (no de-duplication).
        Columns: startTime (UTC ISO-8601), publishTime (UTC ISO-8601),
                 generation_mw (int)

Verified Elexon endpoints used
-------------------------------
    Actuals  : GET /datasets/FUELHH
               Params: settlementDateFrom, settlementDateTo (yyyy-MM-dd),
                       format=json
               Filter: fuelType == "WIND" (applied client-side)

    Forecasts: GET /datasets/WINDFOR
               Params: publishDateTimeFrom, publishDateTimeTo (ISO-8601 UTC),
                       format=json
               Then filter to keep only rows whose startTime ∈ Jan 2026.

No API key required.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

# ── Path bootstrap ───────────────────────────────────────────────────────────
# Allow running from the repo root:  python scripts/fetch_data.py
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.elexon import fetch_fuelhh_wind, fetch_windfor  # noqa: E402

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
DATA_DIR = _REPO_ROOT / "backend" / "data"
ACTUALS_PATH = DATA_DIR / "actuals.csv.gz"
FORECASTS_PATH = DATA_DIR / "forecasts.csv.gz"

# ── Temporal constants ───────────────────────────────────────────────────────
# Delivery window: every half-hour in January 2026 (UK GMT == UTC in January).
JAN_START_DATE = date(2026, 1, 1)
JAN_END_DATE = date(2026, 1, 31)

# UTC datetime bounds for startTime filtering.
JAN_START_UTC = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
JAN_END_UTC = datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc)  # exclusive

# WINDFOR publish window.
# Forecasts published before Jan 1 can have startTimes in Jan 2026 because
# each WINDFOR snapshot covers ~3 days ahead.  We start from Dec 20 (12 days
# before Jan 1) to be certain we capture every revision used for the
# D-1 09:00 cutoff on 2026-01-01.
WINDFOR_PUBLISH_FROM = datetime(2025, 12, 20, 0, 0, tzinfo=timezone.utc)
WINDFOR_PUBLISH_TO = JAN_END_UTC


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def build_actuals() -> pd.DataFrame:
    """Fetch FUELHH WIND rows and normalise to the actuals schema.

    Returns:
        DataFrame with columns [startTime, generation_mw], sorted by
        startTime ascending, all UTC-aware.
    """
    log.info("=== FUELHH WIND actuals – fetching ===")
    rows = fetch_fuelhh_wind(JAN_START_DATE, JAN_END_DATE)

    df = pd.DataFrame(
        {"startTime": r.startTime, "generation_mw": r.generation}
        for r in rows
    )
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df = df.sort_values("startTime").reset_index(drop=True)
    log.info("FUELHH  → %d rows after normalisation", len(df))
    return df


def build_forecasts() -> pd.DataFrame:
    """Fetch WINDFOR rows, keep only startTimes in January 2026.

    Returns:
        DataFrame with columns [startTime, publishTime, generation_mw],
        sorted by (startTime, publishTime) ascending, all UTC-aware.
    """
    log.info("=== WINDFOR forecasts – fetching ===")
    rows = fetch_windfor(WINDFOR_PUBLISH_FROM, WINDFOR_PUBLISH_TO)

    df = pd.DataFrame(
        {
            "publishTime": r.publishTime,
            "startTime": r.startTime,
            "generation_mw": r.generation,
        }
        for r in rows
    )
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)

    # Keep only rows whose startTime falls within January 2026.
    # (Early publish windows return startTimes outside Jan as well.)
    before = len(df)
    mask = (df["startTime"] >= JAN_START_UTC) & (df["startTime"] < JAN_END_UTC)
    df = df[mask].sort_values(["startTime", "publishTime"]).reset_index(drop=True)
    log.info(
        "WINDFOR  → %d rows after startTime filter (dropped %d outside Jan 2026)",
        len(df), before - len(df),
    )
    return df


# ── Save ──────────────────────────────────────────────────────────────────────

def save(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` to a gzip-compressed CSV and log the file size."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, compression="gzip")
    size_kb = path.stat().st_size / 1024
    log.info("Saved  %-30s  %6.1f KB  (%d rows)", path.name, size_kb, len(df))


# ── Quality report ────────────────────────────────────────────────────────────

def quality_report(actuals: pd.DataFrame, forecasts: pd.DataFrame) -> None:
    """Print a plain-text data quality report.

    No data is modified, imputed, or dropped here.  Anomalies are flagged so
    the caller can decide how to handle them.
    """
    sep = "=" * 64

    print(f"\n{sep}")
    print("DATA QUALITY REPORT – January 2026 Elexon snapshot")
    print(sep)

    # ── Actuals ─────────────────────────────────────────────────────────────
    print("\n── FUELHH WIND actuals ─────────────────────────────────────")
    n = len(actuals)
    expected_hh = 31 * 48  # 1,488
    print(f"  Row count            : {n:,}  (expected {expected_hh:,})")
    print(f"  Null startTime       : {actuals['startTime'].isna().sum()}")
    print(f"  Null generation_mw   : {actuals['generation_mw'].isna().sum()}")
    print(f"  Negative generation  : {(actuals['generation_mw'] < 0).sum()}")
    print(f"  startTime range      : {actuals['startTime'].min()}  ->  {actuals['startTime'].max()}")

    dup_act = actuals.duplicated(subset=["startTime"]).sum()
    print(f"  Duplicate startTimes : {dup_act}")

    # Missing half-hours
    expected_idx = pd.date_range(
        "2026-01-01T00:00:00Z", "2026-01-31T23:30:00Z", freq="30min", tz="UTC"
    )
    actual_times = set(actuals["startTime"])
    missing_hh = sorted(t for t in expected_idx if t not in actual_times)
    print(f"  Missing half-hours   : {len(missing_hh)}")
    if missing_hh:
        print("  (first 10 missing)   :", *[str(t) for t in missing_hh[:10]])

    # ── Forecasts ────────────────────────────────────────────────────────────
    print("\n── WINDFOR forecasts ───────────────────────────────────────")
    nf = len(forecasts)
    print(f"  Row count            : {nf:,}")
    print(f"  Null startTime       : {forecasts['startTime'].isna().sum()}")
    print(f"  Null publishTime     : {forecasts['publishTime'].isna().sum()}")
    print(f"  Null generation_mw   : {forecasts['generation_mw'].isna().sum()}")
    print(f"  Negative generation  : {(forecasts['generation_mw'] < 0).sum()}")
    print(f"  publishTime range    : {forecasts['publishTime'].min()}  ->  {forecasts['publishTime'].max()}")
    print(f"  startTime range      : {forecasts['startTime'].min()}  ->  {forecasts['startTime'].max()}")

    dup_for = forecasts.duplicated(subset=["startTime", "publishTime"]).sum()
    print(f"  Duplicate (startTime, publishTime) pairs : {dup_for}")

    # Distinct publishTimes per startTime
    pub_counts = forecasts.groupby("startTime")["publishTime"].nunique()
    print(f"\n  Distinct publishTimes per startTime:")
    print(f"    min    : {pub_counts.min()}")
    print(f"    median : {pub_counts.median():.1f}")
    print(f"    max    : {pub_counts.max()}")
    # Show any startTimes with very few revisions
    sparse = pub_counts[pub_counts == pub_counts.min()]
    if len(sparse) <= 10:
        print(f"    startTimes with fewest revisions:")
        for st, cnt in sparse.items():
            print(f"      {st}  ->  {cnt} publish(es)")

    # Forecast horizon
    horizons_h = (
        (forecasts["startTime"] - forecasts["publishTime"])
        .dt.total_seconds()
        .div(3600)
    )
    print(f"\n  Forecast horizon (startTime − publishTime):")
    print(f"    min    : {horizons_h.min():.1f} h")
    print(f"    p25    : {horizons_h.quantile(0.25):.1f} h")
    print(f"    median : {horizons_h.median():.1f} h")
    print(f"    p75    : {horizons_h.quantile(0.75):.1f} h")
    print(f"    max    : {horizons_h.max():.1f} h")

    # Resolution check – WINDFOR vs FUELHH
    st_sorted = forecasts["startTime"].drop_duplicates().sort_values()
    diffs_min = st_sorted.diff().dropna().dt.total_seconds().div(60)
    vc = diffs_min.value_counts()
    print(f"\n  WINDFOR startTime step sizes (minutes):")
    for step, cnt in vc.head(5).items():
        print(f"    {int(step):3d} min  ×  {cnt:,}")

    print(
        "\n  WARNING - RESOLUTION MISMATCH:"
        "\n    WINDFOR startTime is 1-hour; FUELHH actuals are 30-minute."
        "\n    Each forecast hour aligns to TWO actual half-hours (:00 and :30)."
        "\n    Phase 2 cutoff logic will match on the hour boundary."
        "\n    Accuracy metrics will pair each forecast with both actuals."
        "\n    No imputation is applied; the mismatch is preserved as-is."
    )

    print(f"\n{sep}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main(dry_run: bool = False) -> None:
    """Orchestrate fetch, save, and quality report.

    Args:
        dry_run: If True, print the fetch plan and exit without making API
                 calls or writing files.
    """
    if dry_run:
        print("DRY RUN – no API calls will be made.")
        print(f"  FUELHH   settlementDate  {JAN_START_DATE}  ->  {JAN_END_DATE}")
        print(f"  WINDFOR  publishDateTime {WINDFOR_PUBLISH_FROM.date()}  ->  {WINDFOR_PUBLISH_TO.date()}")
        print(f"  Output   {ACTUALS_PATH}")
        print(f"           {FORECASTS_PATH}")
        return

    actuals = build_actuals()
    forecasts = build_forecasts()

    save(actuals, ACTUALS_PATH)
    save(forecasts, FORECASTS_PATH)

    quality_report(actuals, forecasts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the fetch plan without making API calls.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
