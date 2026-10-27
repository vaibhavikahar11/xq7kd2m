"""Central configuration for the Wind Forecast Portal backend.

Values are read from environment variables first; the defaults here match
the project brief exactly.  Override them in a local .env file or via
docker-compose environment entries – never hard-code secrets.
"""

from datetime import date
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with sensible production defaults."""

    # ------------------------------------------------------------------ #
    # Decision-cutoff logic                                                #
    # ------------------------------------------------------------------ #
    # The team commits to their day-ahead purchase by 09:00 Europe/London
    # on D-1.  January 2026 is fully in GMT, so UTC == local time.
    # The backend endpoints accept an optional cutoff_hour query param to
    # support the "what-if" selector in the UI; this value is the default.
    DECISION_CUTOFF_HOUR: int = 9

    # ------------------------------------------------------------------ #
    # Temporal scope                                                       #
    # ------------------------------------------------------------------ #
    TIMEZONE: str = "Europe/London"
    START_DATE: date = date(2026, 1, 1)
    END_DATE: date = date(2026, 1, 31)

    # ------------------------------------------------------------------ #
    # Data paths                                                           #
    # ------------------------------------------------------------------ #
    # backend/data/ relative to this file:
    #   Path(__file__)        -> backend/app/config.py
    #   .parent               -> backend/app/
    #   .parent.parent        -> backend/
    #   .parent.parent/"data" -> backend/data/
    # In Docker, COPY . . puts backend/ contents at /app/, so data is /app/data/.
    # In Vercel, the repo is bundled intact, so the path resolves correctly.
    DATA_DIR: Path = Path(__file__).parent.parent / "data"

    # ------------------------------------------------------------------ #
    # Validation                                                           #
    # ------------------------------------------------------------------ #
    @field_validator("DECISION_CUTOFF_HOUR")
    @classmethod
    def cutoff_must_be_sensible(cls, v: int) -> int:
        """Reject cutoff hours outside the meaningful 00-23 window."""
        if not 0 <= v <= 23:
            raise ValueError("DECISION_CUTOFF_HOUR must be 0–23")
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
