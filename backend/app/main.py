"""FastAPI application factory.

Keep this module thin: wire up middleware, routers, and startup events here,
but put all business logic in dedicated modules (config, routers, services).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health

app = FastAPI(
    title="Wind Forecast Portal API",
    description=(
        "Day-ahead wind generation forecast and accuracy data for UK electricity buyers. "
        "Data source: Elexon Insights API (WINDFOR + FUELHH datasets). "
        "No API key required."
    ),
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Allow the Vite dev server (any port) and the Vercel deployment to call the
# API.  In production both live on the same Vercel domain, so the wildcard
# origin is only meaningful during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
