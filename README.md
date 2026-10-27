# Wind Forecast Portal

A web application for a UK energy utility's day-ahead power buying team.
Shows wind generation forecasts (Elexon WINDFOR) and their accuracy against
actuals (Elexon FUELHH) for delivery days in January 2026.

> **AI disclosure**: This project was built with Google Antigravity (AGY).

---

## Directory structure

```
.
├── api/                   Vercel Python serverless entry point
│   ├── index.py           Mangum wrapper – imports FastAPI app from backend/
│   └── requirements.txt   Python deps for the Vercel function bundle
├── backend/               FastAPI application
│   ├── app/
│   │   ├── config.py      Settings (cutoff hour, timezone, date range, data path)
│   │   ├── main.py        ASGI app factory (middleware, routers)
│   │   └── routers/
│   │       └── health.py  GET /api/health
│   ├── tests/
│   │   └── test_health.py Pytest tests for the health endpoint
│   ├── Dockerfile
│   └── requirements.txt
├── data/                  Pre-fetched Elexon snapshots (compressed CSV)
│   ├── windfor.csv.gz     WINDFOR forecasts  – added in Phase 1
│   └── fuelhh_wind.csv.gz FUELHH actuals     – added in Phase 1
├── frontend/              Vite + React + TypeScript + Tailwind + Recharts
│   ├── src/
│   │   ├── api/client.ts  Typed fetch helpers
│   │   ├── pages/
│   │   │   └── HealthPage.tsx  Placeholder page (Phase 0)
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts     Proxies /api/* → backend:8000 in dev
├── scripts/
│   └── fetch_data.py      Downloads Elexon data and writes data/ snapshots
├── docker-compose.yml
├── vercel.json
└── README.md
```

---

## How to start the app

### Option A – Docker Compose (recommended, single command)

```bash
docker compose up --build
```

| Service  | URL                         |
|----------|-----------------------------|
| Frontend | http://localhost:5173       |
| Backend  | http://localhost:8000       |
| API docs | http://localhost:8000/api/docs |

The frontend Vite dev server proxies `/api/*` to the backend container, so
hot-reload works for both services.

**Cold-start note**: the Python backend loads the pre-fetched data snapshots
from `data/` into memory once at startup.  Subsequent warm requests are fast.
On Vercel, the first request after a cold-start may take 200-400 ms while the
serverless runtime initialises.

### Option B – Without Docker

**Backend**
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate  |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend** (separate terminal)
```bash
cd frontend
npm install
npm run dev
```

### Run backend tests

```bash
cd backend
pytest tests/ -v
```

---

## Refresh Elexon data

```bash
python scripts/fetch_data.py
```

Overwrites `data/windfor.csv.gz` and `data/fuelhh_wind.csv.gz`.

---

## Vercel deployment

Live URL: _to be added after first deploy_

The frontend is deployed as a static build; the FastAPI backend runs as a
Python serverless function (`api/index.py`) via Mangum.

---

## Key assumptions (per project brief §5)

| Assumption | Value |
|---|---|
| Decision cutoff | D-1 at **09:00 Europe/London** (configurable via `DECISION_CUTOFF_HOUR`) |
| January timezone | GMT == UTC (no DST) |
| "Latest forecast" | greatest `publishTime ≤ cutoff` per `startTime`; later publishes excluded (no look-ahead bias) |
| Error definition | `error = forecast − actual` (positive = over-forecast) |
| Metrics | MAE, RMSE, bias, P50/P90/P95 of \|error\|, MAE % of mean actual. No MAPE. |
| Missing data | Flagged explicitly; never silently filled. Gaps shown in charts, labelled in tables. |

---

## AI tools used

**Google Antigravity (AGY)** was used throughout this project for code
generation, architectural decisions, and documentation drafting.  All
generated code was reviewed, tested, and adapted by the developer.
