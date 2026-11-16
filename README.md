# Gridbricks — Wind Forecast Portal

A web application for a UK energy utility's day-ahead power buying team.
It shows which WINDFOR forecast was available at the team's decision cutoff
on D-1, compares it against half-hourly FUELHH actuals for every delivery
day in January 2026, and quantifies forecast accuracy across time-of-day,
date, and horizon dimensions — all from publicly available Elexon BMRS data.

**Live:** [gridbricks-one.vercel.app](https://gridbricks-one.vercel.app/)

> **AI disclosure:** This project was built with Google Antigravity (AGY)
> under my direction. I reviewed and tested the code and can explain it.

---

## Screenshots

_Coming soon — placeholder for Decision and Accuracy page screenshots._

---

## Files and directories

```
.
├── api/                          Vercel serverless entry point
│   ├── index.py                  Mangum wrapper; imports FastAPI from backend/
│   └── requirements.txt          Python deps for the Vercel function
│
├── backend/                      FastAPI application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py             Settings: cutoff hour, timezone, dates, data path
│   │   ├── data_cache.py         Module-level cache; pre-warms at startup
│   │   ├── elexon.py             Typed Elexon BMRS API client
│   │   ├── main.py               App factory: CORS, routers, lifespan
│   │   ├── metrics.py            MAE, RMSE, bias, percentiles, horizon buckets
│   │   ├── selection.py          Forecast selection: cutoff, half-hour pairing
│   │   └── routers/
│   │       ├── accuracy.py       GET /api/accuracy/{summary,by-hour,by-date,by-horizon}
│   │       ├── config.py         GET /api/config
│   │       ├── decision.py       GET /api/decision
│   │       └── health.py         GET /api/health
│   ├── data/
│   │   ├── actuals.csv.gz        FUELHH wind actuals  (1,488 half-hours)
│   │   └── forecasts.csv.gz      WINDFOR forecasts    (18,080 rows)
│   ├── tests/
│   │   ├── conftest.py           Shared pytest fixtures
│   │   ├── test_api.py           API integration tests (46 tests)
│   │   ├── test_health.py        Health endpoint tests (9 tests)
│   │   ├── test_metrics.py       Metrics unit tests    (29 tests)
│   │   └── test_selection.py     Selection logic tests (19 tests)
│   ├── __init__.py               Makes backend/ a Python package for Vercel
│   ├── Dockerfile                python:3.11-slim, non-root user, uvicorn :8000
│   ├── .dockerignore
│   ├── pytest.ini
│   └── requirements.txt
│
├── frontend/                     Vite + React + TypeScript + Tailwind + Recharts
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts         Typed fetch helpers for all 6 endpoints
│   │   │   └── types.ts          TypeScript interfaces matching Pydantic models
│   │   ├── components/
│   │   │   ├── CutoffSelector.tsx  Cutoff hour dropdown (06–12)
│   │   │   └── MetricCard.tsx      Metric tile with null handling
│   │   ├── pages/
│   │   │   ├── AccuracyPage.tsx  4-tab dashboard: Summary, By Hour, By Date, By Horizon
│   │   │   ├── DecisionPage.tsx  Date picker, chart, 48-row table
│   │   │   └── HealthPage.tsx    Health check page
│   │   ├── App.tsx               React Router: / → Decision, /accuracy → Accuracy
│   │   ├── index.css             Tailwind base styles
│   │   └── main.tsx              App entry point
│   ├── index.html
│   ├── Dockerfile                Multi-stage: node build → nginx serve
│   ├── nginx.conf                Proxies /api → backend:8000, SPA fallback
│   ├── .dockerignore
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── vite.config.ts            Dev proxy: /api → localhost:8000
│
├── scripts/
│   ├── fetch_data.py             Downloads Elexon data → backend/data/*.csv.gz
│   ├── validate_metrics.py       Sanity-check metrics against known values
│   └── validate_selection.py     Sanity-check selection output
│
├── docker-compose.yml            backend :8000 + frontend :3000, healthcheck
├── vercel.json                   Build + rewrite config for Vercel deployment
├── PROJECT_BRIEF.md              Original certification brief
└── README.md
```

---

## How to run

### Option A — Docker Compose (recommended)

```bash
docker compose up --build
```

| Service  | URL |
|----------|-----|
| Frontend | http://localhost:3000 |
| Backend  | http://localhost:8000 |
| API docs | http://localhost:8000/api/docs |

The frontend nginx container proxies `/api/*` to the backend.
No `.env` file or secrets required.

### Option B — Without Docker

**Backend**

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend** (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server at http://localhost:5173 proxies `/api/*` to `localhost:8000`.

---

## Refresh the data snapshot

The committed CSVs in `backend/data/` are pre-fetched snapshots.
To re-fetch from the Elexon BMRS API:

```bash
python scripts/fetch_data.py            # fetch and overwrite
python scripts/fetch_data.py --dry-run  # print plan without fetching
```

No API key required. Outputs:
- `backend/data/actuals.csv.gz` — FUELHH WIND generation, 30-min resolution
- `backend/data/forecasts.csv.gz` — WINDFOR forecasts, every publishTime revision

---

## Key assumptions

| Assumption | Detail |
|---|---|
| **Decision cutoff** | D-1 at 09:00 Europe/London (default). Configurable via `DECISION_CUTOFF_HOUR` env var. The UI has a what-if selector (06–12) that changes all downstream metrics. |
| **Forecast selection** | Latest `publishTime ≤ cutoff` per `startTime`. Forecasts published after the cutoff are excluded — no look-ahead bias. |
| **Half-hour pairing** | WINDFOR is hourly; each hourly forecast is applied to **both** the `:00` and `:30` half-hours without interpolation. |
| **Error sign convention** | `error = forecast − actual`. Positive = over-forecast. |
| **No MAPE** | Actuals can be near zero, making MAPE undefined or misleading. MAE % of mean actual is used instead. |
| **Missing data** | Flagged explicitly (`missing_forecast = true`, `null` values). Never silently filled or imputed. Chart gaps are visible; tables show "No forecast available". |
| **January timezone** | January 2026 is entirely in GMT, so UTC == Europe/London local time. No DST edge cases. |

---

## Design decisions

**Committed snapshot, not live API calls.**
The backend serves pre-fetched compressed CSVs from `backend/data/`, never calling Elexon at request time. This makes the app fully reproducible, removes the Elexon API as a runtime dependency, and keeps response times under 50 ms on warm requests. To update the data, re-run `scripts/fetch_data.py`.

**Compressed CSV, not Parquet.**
The dataset is small (1,488 actuals + 18,080 forecasts). Gzipped CSV keeps the repo lightweight, needs no extra binary dependency, and pandas reads it natively.

**Docker for local, Vercel for production.**
Docker Compose gives a single-command local environment with nginx proxying. On Vercel, the frontend deploys as a static build and the FastAPI backend runs as a Python serverless function via Mangum (`api/index.py`).

**Cold-start note.**
On Vercel, the first request after a cold start loads the CSV snapshots into memory (~200–400 ms). Subsequent warm requests reuse the module-level cache.

---

## API reference

All endpoints return JSON. Interactive docs at `/api/docs` (Swagger) and `/api/redoc`.

### `GET /api/health`

Returns service status, version, and config.

```
GET /api/health
→ {"status": "ok", "version": "0.1.0", "config": {...}}
```

### `GET /api/config`

Returns application settings (cutoff hour, timezone, date range).

```
GET /api/config
→ {"decision_cutoff_hour": 9, "timezone": "Europe/London", ...}
```

### `GET /api/decision`

48 half-hourly rows for one delivery day plus a day summary.

| Param | Required | Default | Description |
|---|---|---|---|
| `date` | ✅ | — | Delivery date `YYYY-MM-DD` (2026-01-01 to 2026-01-31) |
| `cutoff_hour` | — | `9` | Decision cutoff hour 0–23 (Europe/London) |

```
GET /api/decision?date=2026-01-15&cutoff_hour=9
```

### `GET /api/accuracy/summary`

Overall accuracy metrics for a date range with a suggested reserve buffer.

| Param | Required | Default | Description |
|---|---|---|---|
| `start` | ✅ | — | Start date `YYYY-MM-DD` |
| `end` | ✅ | — | End date `YYYY-MM-DD` |
| `cutoff_hour` | — | `9` | Decision cutoff hour 0–23 |

```
GET /api/accuracy/summary?start=2026-01-01&end=2026-01-31&cutoff_hour=9
```

### `GET /api/accuracy/by-hour`

Accuracy grouped by hour of day (0–23, Europe/London). Same params as `/summary`.

```
GET /api/accuracy/by-hour?start=2026-01-01&end=2026-01-31
```

### `GET /api/accuracy/by-date`

Accuracy grouped by delivery date. Same params as `/summary`.

```
GET /api/accuracy/by-date?start=2026-01-01&end=2026-01-31
```

### `GET /api/accuracy/by-horizon`

Accuracy grouped by forecast horizon bucket (0–6 h, 6–12 h, 12–24 h, 24–36 h, 36–48 h, 48 h+).
Uses **all** publishTimes, not just the decision cutoff.

| Param | Required | Default | Description |
|---|---|---|---|
| `start` | ✅ | — | Start date `YYYY-MM-DD` |
| `end` | ✅ | — | End date `YYYY-MM-DD` |

```
GET /api/accuracy/by-horizon?start=2026-01-01&end=2026-01-31
```

---

## Testing

**103 tests** across 4 test files:

| File | Count | Scope |
|---|---|---|
| `test_health.py` | 9 | Health endpoint |
| `test_selection.py` | 19 | Cutoff logic, half-hour pairing, look-ahead bias |
| `test_metrics.py` | 29 | MAE, RMSE, bias, percentiles, horizon buckets, edge cases |
| `test_api.py` | 46 | All API endpoints, validation, response shapes |

```bash
# Run all tests
cd backend
pytest tests/ -v

# Windows (from repo root)
cd backend
.venv\Scripts\pytest.exe tests\ -v
```

Frontend type-check + build:
```bash
cd frontend
npm ci
npm run build   # runs tsc -b && vite build
```

---

## Known limitations

- **January 2026 only.** The data snapshot and date validation are scoped to
  2026-01-01 through 2026-01-31. Extending to other months requires re-running
  `fetch_data.py` and updating `START_DATE`/`END_DATE` in `config.py`.
- **Sparse horizons at month boundaries.** The 36–48 h and 48 h+ horizon
  buckets have fewer data points near the end of January because forecasts
  published after the month are not included.
- **UI date range is hard-coded.** The frontend date picker and accuracy page
  default to January 2026. A future version could read from `/api/config`.
- **No real-time updates.** Data is a static snapshot. There is no WebSocket or
  polling refresh.
- **Single month of data.** Accuracy metrics reflect one month of winter wind
  patterns and should not be generalised to other seasons.

---

## AI tools used

**Google Antigravity (AGY)** was used for code generation, architectural
decisions, and documentation drafting under my direction. I reviewed, tested,
and adapted all generated code and can explain every part of it.
