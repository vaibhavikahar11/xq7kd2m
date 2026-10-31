"""FastAPI application factory.

Keep this module thin: wire up middleware, routers, and startup events here,
but put all business logic in dedicated modules (config, routers, services).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.data_cache import startup
from app.routers import accuracy, config, decision, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load the compressed CSV snapshots into module-level memory at startup.

    On Vercel, this runs during the cold start.  Warm invocations skip it
    entirely because the in-memory DataFrames persist across requests within
    the same function instance.
    """
    startup()
    yield


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
    lifespan=lifespan,
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
app.include_router(config.router, prefix="/api")
app.include_router(decision.router, prefix="/api")
app.include_router(accuracy.router, prefix="/api")
