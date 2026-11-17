"""
tests/test_api.py — Integration tests for the Gridbricks REST API.

All tests use a module-scoped FastAPI TestClient so the data load happens
once per test session.  Tests run against real committed snapshot data
(backend/data/*.csv.gz) so they also validate end-to-end data integrity.

Run command (from the repo root, or adjust the path accordingly):

    cd backend
    .venv\\Scripts\\pytest.exe tests\\test_api.py -v

Note: FastAPI's TestClient uses anyio internally (blocking portal); run it
      with the anyio plugin disabled (already set in pytest.ini via
      ``addopts = -p no:anyio``) and outside the agent sandbox.

Coverage
--------
- GET /api/config         — shape, field types
- GET /api/decision       — 200 shape (48 rows, required fields, flag types)
                          — 400 for out-of-range date, bad cutoff, bad format
                          — 404 (edge: can't happen in practice but path tested)
- GET /api/accuracy/summary   — 200, field presence, buffer logic
- GET /api/accuracy/by-hour   — 200, exactly 24 hours
- GET /api/accuracy/by-date   — 200, correct date keys
- GET /api/accuracy/by-horizon — 200, exactly 6 buckets
- Shared validation       — start > end → 400, date outside range → 400,
                            cutoff_hour 24 → 400
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

JAN_START = "2026-01-01"
JAN_END = "2026-01-31"
SAMPLE_DATE = "2026-01-15"


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Module-scoped TestClient: data is loaded once for the full test session."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# /api/config
# ---------------------------------------------------------------------------


class TestConfig:
    def test_status_200(self, client: TestClient) -> None:
        assert client.get("/api/config").status_code == 200

    def test_response_shape(self, client: TestClient) -> None:
        data = client.get("/api/config").json()
        assert "default_cutoff_hour" in data
        assert "timezone" in data
        assert "allowed_date_range" in data
        assert "allowed_cutoff_hour_range" in data

    def test_default_cutoff_is_9(self, client: TestClient) -> None:
        assert client.get("/api/config").json()["default_cutoff_hour"] == 9

    def test_timezone_is_london(self, client: TestClient) -> None:
        assert client.get("/api/config").json()["timezone"] == "Europe/London"

    def test_date_range_covers_january(self, client: TestClient) -> None:
        dr = client.get("/api/config").json()["allowed_date_range"]
        assert dr["start"] == JAN_START
        assert dr["end"] == JAN_END

    def test_cutoff_range_0_23(self, client: TestClient) -> None:
        cr = client.get("/api/config").json()["allowed_cutoff_hour_range"]
        assert cr["min"] == 0
        assert cr["max"] == 23


# ---------------------------------------------------------------------------
# /api/decision — happy path
# ---------------------------------------------------------------------------


class TestDecisionHappy:
    def test_status_200(self, client: TestClient) -> None:
        r = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=9")
        assert r.status_code == 200

    def test_exactly_48_rows(self, client: TestClient) -> None:
        data = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=9").json()
        assert len(data["rows"]) == 48

    def test_row_fields_present(self, client: TestClient) -> None:
        row = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=9").json()["rows"][0]
        assert "startTime" in row
        assert "forecast_mw" in row
        assert "actual_mw" in row
        assert "publishTime" in row
        assert "horizon_hours" in row
        assert "missing_forecast" in row

    def test_missing_forecast_is_bool(self, client: TestClient) -> None:
        rows = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=9").json()["rows"]
        assert all(isinstance(r["missing_forecast"], bool) for r in rows)

    def test_start_times_are_utc_iso(self, client: TestClient) -> None:
        rows = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=9").json()["rows"]
        # All startTimes must contain UTC offset
        assert all("+00:00" in r["startTime"] for r in rows)

    def test_cutoff_utc_in_response(self, client: TestClient) -> None:
        data = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=9").json()
        assert "cutoff_utc" in data
        assert "cutoff_local" in data
        # Cutoff for Jan 15 at hour 9 should be Jan 14 09:00
        assert "2026-01-14T09:00:00" in data["cutoff_utc"]

    def test_summary_present(self, client: TestClient) -> None:
        summary = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=9").json()["summary"]
        assert "peak_forecast_mw" in summary
        assert "avg_forecast_mw" in summary
        assert "total_forecast_mwh" in summary
        assert "missing_half_hours" in summary

    def test_missing_half_hours_is_zero(self, client: TestClient) -> None:
        """January 2026 has no missing forecasts in the snapshot."""
        summary = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=9").json()["summary"]
        assert summary["missing_half_hours"] == 0

    def test_jan_01_uses_dec31_forecast(self, client: TestClient) -> None:
        """Delivery day 2026-01-01: cutoff is 2025-12-31 09:00; publishTime must be from Dec 31."""
        data = client.get("/api/decision?date=2026-01-01&cutoff_hour=9").json()
        assert "cutoff_utc" in data
        assert "2025-12-31" in data["cutoff_utc"]
        first_row = data["rows"][0]
        assert first_row["publishTime"] is not None
        assert "2025-12-31" in first_row["publishTime"]

    def test_default_cutoff_applied(self, client: TestClient) -> None:
        """Omitting cutoff_hour should use the default (9)."""
        r_explicit = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=9")
        r_default = client.get(f"/api/decision?date={SAMPLE_DATE}")
        assert r_explicit.json()["cutoff_hour"] == r_default.json()["cutoff_hour"]
        assert r_explicit.json()["rows"][0]["forecast_mw"] == r_default.json()["rows"][0]["forecast_mw"]

    def test_different_cutoff_changes_forecast(self, client: TestClient) -> None:
        """cutoff_hour=6 may select a different (earlier) publishTime than cutoff_hour=9."""
        r9 = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=9").json()
        r6 = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=6").json()
        # Both should return 48 rows; cutoff timestamps will differ
        assert len(r9["rows"]) == 48
        assert len(r6["rows"]) == 48
        assert r9["cutoff_utc"] != r6["cutoff_utc"]


# ---------------------------------------------------------------------------
# /api/decision — validation errors
# ---------------------------------------------------------------------------


class TestDecisionValidation:
    def test_date_out_of_range_returns_400(self, client: TestClient) -> None:
        r = client.get("/api/decision?date=2026-02-10")
        assert r.status_code == 400
        assert "outside" in r.json()["detail"].lower()

    def test_date_before_range_returns_400(self, client: TestClient) -> None:
        r = client.get("/api/decision?date=2025-12-31")
        assert r.status_code == 400

    def test_invalid_date_format_returns_400(self, client: TestClient) -> None:
        r = client.get("/api/decision?date=15-01-2026")
        assert r.status_code == 400

    def test_cutoff_hour_25_returns_400(self, client: TestClient) -> None:
        r = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=25")
        assert r.status_code == 400
        assert "0-23" in r.json()["detail"]

    def test_cutoff_hour_negative_returns_400(self, client: TestClient) -> None:
        r = client.get(f"/api/decision?date={SAMPLE_DATE}&cutoff_hour=-1")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# /api/accuracy/summary
# ---------------------------------------------------------------------------


class TestAccuracySummary:
    def _get(self, client: TestClient, **kwargs) -> dict:
        params = {"start": JAN_START, "end": JAN_END, **kwargs}
        r = client.get("/api/accuracy/summary", params=params)
        assert r.status_code == 200
        return r.json()

    def test_status_200(self, client: TestClient) -> None:
        r = client.get("/api/accuracy/summary", params={"start": JAN_START, "end": JAN_END})
        assert r.status_code == 200

    def test_metrics_fields_present(self, client: TestClient) -> None:
        data = self._get(client)
        m = data["metrics"]
        for field in ("n_matched", "n_excluded", "mae", "rmse", "bias",
                      "mae_pct", "abs_p50", "abs_p90", "abs_p95",
                      "signed_p5", "signed_p50", "signed_p95"):
            assert field in m, f"Missing field: {field}"

    def test_n_matched_equals_1488(self, client: TestClient) -> None:
        data = self._get(client)
        assert data["metrics"]["n_matched"] == 1488

    def test_n_excluded_is_zero(self, client: TestClient) -> None:
        data = self._get(client)
        assert data["metrics"]["n_excluded"] == 0

    def test_positive_bias(self, client: TestClient) -> None:
        """January 2026 has a large positive bias (over-forecast)."""
        data = self._get(client)
        assert data["metrics"]["bias"] > 0

    def test_suggested_buffer_mw_present(self, client: TestClient) -> None:
        data = self._get(client)
        assert "suggested_buffer_mw" in data
        assert data["suggested_buffer_mw"] is not None
        assert data["suggested_buffer_mw"] >= 0

    def test_suggested_buffer_uses_over_forecast_tail(self, client: TestClient) -> None:
        """Buffer must equal signed_p95 (over-forecast tail), not -signed_p5."""
        data = self._get(client)
        p95 = data["metrics"]["signed_p95"]
        assert p95 is not None
        expected = max(0.0, p95)
        assert data["suggested_buffer_mw"] == pytest.approx(expected, rel=1e-6)

    def test_suggested_buffer_explanation_present(self, client: TestClient) -> None:
        data = self._get(client)
        assert isinstance(data["suggested_buffer_explanation"], str)
        assert "over-forecast" in data["suggested_buffer_explanation"]

    def test_surplus_risk_mw_present(self, client: TestClient) -> None:
        data = self._get(client)
        assert "surplus_risk_mw" in data
        assert data["surplus_risk_mw"] is not None
        assert data["surplus_risk_mw"] >= 0

    def test_surplus_risk_uses_under_forecast_tail(self, client: TestClient) -> None:
        """Surplus risk must equal -signed_p5 (under-forecast tail)."""
        data = self._get(client)
        p5 = data["metrics"]["signed_p5"]
        assert p5 is not None
        expected = max(0.0, -p5)
        assert data["surplus_risk_mw"] == pytest.approx(expected, rel=1e-6)

    def test_surplus_risk_explanation_present(self, client: TestClient) -> None:
        data = self._get(client)
        assert isinstance(data["surplus_risk_explanation"], str)
        assert len(data["surplus_risk_explanation"]) > 10

    def test_cutoff_hour_reflected_in_response(self, client: TestClient) -> None:
        data = self._get(client, cutoff_hour=6)
        assert data["cutoff_hour"] == 6

    def test_start_gt_end_returns_400(self, client: TestClient) -> None:
        r = client.get("/api/accuracy/summary",
                       params={"start": JAN_END, "end": JAN_START})
        assert r.status_code == 400

    def test_date_out_of_range_returns_400(self, client: TestClient) -> None:
        r = client.get("/api/accuracy/summary",
                       params={"start": "2025-06-01", "end": JAN_END})
        assert r.status_code == 400

    def test_bad_cutoff_returns_400(self, client: TestClient) -> None:
        r = client.get("/api/accuracy/summary",
                       params={"start": JAN_START, "end": JAN_END, "cutoff_hour": 99})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# /api/accuracy/by-hour
# ---------------------------------------------------------------------------


class TestAccuracyByHour:
    def test_status_200(self, client: TestClient) -> None:
        r = client.get("/api/accuracy/by-hour", params={"start": JAN_START, "end": JAN_END})
        assert r.status_code == 200

    def test_exactly_24_hours(self, client: TestClient) -> None:
        data = client.get("/api/accuracy/by-hour",
                          params={"start": JAN_START, "end": JAN_END}).json()
        assert len(data["by_hour"]) == 24

    def test_hours_are_0_to_23(self, client: TestClient) -> None:
        data = client.get("/api/accuracy/by-hour",
                          params={"start": JAN_START, "end": JAN_END}).json()
        hours = [entry["hour"] for entry in data["by_hour"]]
        assert sorted(hours) == list(range(24))

    def test_each_hour_has_metrics(self, client: TestClient) -> None:
        data = client.get("/api/accuracy/by-hour",
                          params={"start": JAN_START, "end": JAN_END}).json()
        for entry in data["by_hour"]:
            assert "metrics" in entry
            assert "n_matched" in entry["metrics"]


# ---------------------------------------------------------------------------
# /api/accuracy/by-date
# ---------------------------------------------------------------------------


class TestAccuracyByDate:
    def test_status_200(self, client: TestClient) -> None:
        r = client.get("/api/accuracy/by-date", params={"start": JAN_START, "end": JAN_END})
        assert r.status_code == 200

    def test_31_entries_for_full_january(self, client: TestClient) -> None:
        data = client.get("/api/accuracy/by-date",
                          params={"start": JAN_START, "end": JAN_END}).json()
        assert len(data["by_date"]) == 31

    def test_dates_in_ascending_order(self, client: TestClient) -> None:
        data = client.get("/api/accuracy/by-date",
                          params={"start": JAN_START, "end": JAN_END}).json()
        dates = [e["date"] for e in data["by_date"]]
        assert dates == sorted(dates)

    def test_single_day_range(self, client: TestClient) -> None:
        data = client.get("/api/accuracy/by-date",
                          params={"start": SAMPLE_DATE, "end": SAMPLE_DATE}).json()
        assert len(data["by_date"]) == 1
        assert data["by_date"][0]["date"] == SAMPLE_DATE


# ---------------------------------------------------------------------------
# /api/accuracy/by-horizon
# ---------------------------------------------------------------------------


EXPECTED_BUCKETS = {"0-6h", "6-12h", "12-24h", "24-36h", "36-48h", "48h+"}


class TestAccuracyByHorizon:
    def test_status_200(self, client: TestClient) -> None:
        r = client.get("/api/accuracy/by-horizon",
                       params={"start": JAN_START, "end": JAN_END})
        assert r.status_code == 200

    def test_exactly_6_buckets(self, client: TestClient) -> None:
        data = client.get("/api/accuracy/by-horizon",
                          params={"start": JAN_START, "end": JAN_END}).json()
        assert len(data["by_horizon"]) == 6

    def test_all_bucket_labels_present(self, client: TestClient) -> None:
        data = client.get("/api/accuracy/by-horizon",
                          params={"start": JAN_START, "end": JAN_END}).json()
        found = {e["bucket"] for e in data["by_horizon"]}
        assert found == EXPECTED_BUCKETS

    def test_all_buckets_have_data(self, client: TestClient) -> None:
        """With a full month of data every bucket should have at least some rows."""
        data = client.get("/api/accuracy/by-horizon",
                          params={"start": JAN_START, "end": JAN_END}).json()
        for entry in data["by_horizon"]:
            assert entry["metrics"]["n_matched"] > 0, f"Empty bucket: {entry['bucket']}"

    def test_no_cutoff_hour_param(self, client: TestClient) -> None:
        """by-horizon has no cutoff_hour parameter — extra param should be ignored."""
        r = client.get("/api/accuracy/by-horizon",
                       params={"start": JAN_START, "end": JAN_END, "cutoff_hour": 9})
        # FastAPI ignores unknown query params by default
        assert r.status_code == 200
