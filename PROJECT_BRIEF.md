# PROJECT BRIEF: Wind Forecast Decision & Accuracy Portal

## 1. Context
I am a product developer building a customized web app for a UK energy utility.
The client's team buys electricity from the UK day-ahead market. They must decide
the day before delivery (D-1) how much power to buy beyond what wind will supply.
Wind generation is weather-dependent, so they rely on forecasts.

## 2. What the app must do
1. Show the LATEST wind generation forecast available at the time the team must
   make the day-ahead purchase decision (D-1 cutoff), for each half-hour of
   delivery day D.
2. Quantitatively evaluate forecast accuracy against actual wind generation, so
   the team can include the expected error in their decisions.

## 3. Data (Elexon only, no other data)
Use the Elexon Insights API (base URL https://data.elexon.co.uk/bmrs/api/v1,
no API key needed). Confirm exact endpoints and parameters in the Swagger docs
at https://developer.data.elexon.co.uk/
- Actuals: dataset FUELHH, filter fuelType == "WIND".
  Fields: startTime (30-min resolution), generation (MW).
- Forecasts: dataset WINDFOR.
  Fields: startTime, publishTime (when the forecast was created), generation (MW).
- Scope: purchase decisions for delivery days in January 2026 (1-31 Jan 2026).
  Forecasts published in late December 2025 may be needed for early January.

## 4. Tech requirements
- Frontend: React (Vite + TypeScript, Tailwind, Recharts)
- Backend: Python (FastAPI, pandas)
- Docker for local run (docker compose up --build)
- Deployed on Vercel (frontend static + FastAPI as Python serverless function)
- Public GitHub repo with an anonymous name
- README must contain: files/directories, how to start the app, Vercel link,
  and an explicit disclosure of AI tools used (Google Antigravity)
- Time cap: 16 hours total

## 5. My assumptions (state these in README and video)
- Decision cutoff: D-1 at 09:00 UK time (Europe/London). Configurable in config.py.
  January is GMT, so UK time equals UTC.
- "Latest forecast available" = for each startTime on delivery day D, the forecast
  with the greatest publishTime that is <= cutoff. Anything published after the
  cutoff must be excluded (no look-ahead bias).
- error = forecast - actual (positive = over-forecast).
- Metrics: MAE, RMSE, bias, P50/P90/P95 of absolute error, MAE as % of mean actual.
  No MAPE (actuals can be near zero).
- Accuracy breakdowns: by hour of day, by delivery date, by forecast horizon
  (startTime - publishTime).
- Missing data is flagged explicitly, never silently filled.

## 6. Pages
- Decision View: pick delivery date, see the cutoff, a 48-point forecast chart,
  optional actuals overlay, table with publish time used per half-hour.
- Accuracy View: KPI cards, forecast vs actual chart, error by hour, error by
  horizon, daily MAE trend, plain-English "buffer" recommendation for buyers.

## 7. Deliverables
- Unlisted YouTube video, max 10 min total:
  Part 1 (max 5 min) client pitch. Part 2 (max 5 min) tech lead review.
- Public GitHub repo + README
- Live Vercel deployment
- Submission form (verify every link in incognito)

## 8. Working rules for the AI agent
- Work in small steps, one phase at a time, and explain what you did.
- Clean, typed code with docstrings. Tests for all core logic.
- Never invent API endpoints or parameters: verify against Elexon Swagger.
- No secrets or API keys anywhere in the repo.