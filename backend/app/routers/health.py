"""Health-check router.

Exposes GET /api/health so orchestration tools, the Vercel warm-up probe,
and the frontend placeholder page can verify that the API is reachable and
show the active configuration to operators.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(tags=["meta"])


class ConfigSnapshot(BaseModel):
    """Subset of Settings exposed through the health endpoint."""

    decision_cutoff_hour: int
    timezone: str
    start_date: str
    end_date: str


class HealthResponse(BaseModel):
    """Standard health-check response envelope."""

    status: str
    version: str
    config: ConfigSnapshot


@router.get("/health", response_model=HealthResponse, summary="API health and config")
def get_health() -> HealthResponse:
    """Return service liveness status and the active runtime configuration.

    This endpoint is intentionally unauthenticated and read-only.  It is
    used by Docker health-checks, Vercel probes, and the UI splash page.
    """
    return HealthResponse(
        status="ok",
        version="0.1.0",
        config=ConfigSnapshot(
            decision_cutoff_hour=settings.DECISION_CUTOFF_HOUR,
            timezone=settings.TIMEZONE,
            start_date=str(settings.START_DATE),
            end_date=str(settings.END_DATE),
        ),
    )
