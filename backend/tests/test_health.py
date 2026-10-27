"""Tests for GET /api/health.

Uses FastAPI's synchronous TestClient (backed by httpx) so no async runner
is required.  These tests run in CI and locally with:

    cd backend && pytest tests/test_health.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Happy-path                                                                   #
# --------------------------------------------------------------------------- #


def test_health_status_200() -> None:
    """Endpoint must respond with HTTP 200."""
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_status_is_ok() -> None:
    """'status' field must be the string 'ok'."""
    data = client.get("/api/health").json()
    assert data["status"] == "ok"


def test_health_version_present() -> None:
    """'version' field must be a non-empty string."""
    data = client.get("/api/health").json()
    assert isinstance(data["version"], str)
    assert data["version"]


def test_health_config_cutoff_hour() -> None:
    """Default decision cutoff must be 09:00 (project brief §5)."""
    config = client.get("/api/health").json()["config"]
    assert config["decision_cutoff_hour"] == 9


def test_health_config_timezone() -> None:
    """Timezone must be 'Europe/London' (project brief §5)."""
    config = client.get("/api/health").json()["config"]
    assert config["timezone"] == "Europe/London"


def test_health_config_date_range() -> None:
    """Date range must cover January 2026 (project brief §3)."""
    config = client.get("/api/health").json()["config"]
    assert config["start_date"] == "2026-01-01"
    assert config["end_date"] == "2026-01-31"


# --------------------------------------------------------------------------- #
# Response schema                                                               #
# --------------------------------------------------------------------------- #


def test_health_response_keys() -> None:
    """Top-level response must contain exactly status, version, config."""
    data = client.get("/api/health").json()
    assert set(data.keys()) == {"status", "version", "config"}


def test_health_config_keys() -> None:
    """Config object must expose the four expected keys."""
    config = client.get("/api/health").json()["config"]
    expected = {"decision_cutoff_hour", "timezone", "start_date", "end_date"}
    assert expected.issubset(config.keys())


# --------------------------------------------------------------------------- #
# Content-type                                                                  #
# --------------------------------------------------------------------------- #


def test_health_content_type_json() -> None:
    """Response Content-Type must be application/json."""
    response = client.get("/api/health")
    assert "application/json" in response.headers["content-type"]
