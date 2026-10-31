/**
 * types.ts – TypeScript interfaces mirroring all backend Pydantic response models.
 *
 * Keep these in sync with:
 *   backend/app/routers/config.py
 *   backend/app/routers/decision.py
 *   backend/app/routers/accuracy.py
 */

// ── /api/config ──────────────────────────────────────────────────────────────

export interface DateRange {
  start: string // YYYY-MM-DD
  end: string
}

export interface CutoffHourRange {
  min: number
  max: number
}

export interface ConfigResponse {
  default_cutoff_hour: number
  timezone: string
  allowed_date_range: DateRange
  allowed_cutoff_hour_range: CutoffHourRange
}

// ── /api/decision ─────────────────────────────────────────────────────────────

export interface HalfHourRow {
  startTime: string         // ISO-8601 UTC
  forecast_mw: number | null
  actual_mw: number | null
  publishTime: string | null
  horizon_hours: number | null
  missing_forecast: boolean
}

export interface DaySummary {
  peak_forecast_mw: number | null
  avg_forecast_mw: number | null
  total_forecast_mwh: number | null
  peak_actual_mw: number | null
  avg_actual_mw: number | null
  total_actual_mwh: number | null
  missing_half_hours: number
}

export interface DecisionResponse {
  date: string          // YYYY-MM-DD
  cutoff_hour: number
  cutoff_utc: string    // ISO-8601 UTC
  cutoff_local: string  // ISO-8601 Europe/London
  rows: HalfHourRow[]
  summary: DaySummary
}

// ── /api/accuracy/* ───────────────────────────────────────────────────────────

export interface MetricSetResponse {
  n_matched: number
  n_excluded: number
  mae: number | null
  rmse: number | null
  bias: number | null
  mae_pct: number | null
  abs_p50: number | null
  abs_p90: number | null
  abs_p95: number | null
  signed_p5: number | null
  signed_p50: number | null
  signed_p95: number | null
}

export interface AccuracySummaryResponse {
  start: string
  end: string
  cutoff_hour: number
  metrics: MetricSetResponse
  suggested_buffer_mw: number | null
  suggested_buffer_explanation: string
}

export interface HourEntry {
  hour: number
  metrics: MetricSetResponse
}

export interface AccuracyByHourResponse {
  start: string
  end: string
  cutoff_hour: number
  by_hour: HourEntry[]
}

export interface DateEntry {
  date: string // YYYY-MM-DD
  metrics: MetricSetResponse
}

export interface AccuracyByDateResponse {
  start: string
  end: string
  cutoff_hour: number
  by_date: DateEntry[]
}

export interface HorizonEntry {
  bucket: string // "0-6h" | "6-12h" | "12-24h" | "24-36h" | "36-48h" | "48h+"
  metrics: MetricSetResponse
}

export interface AccuracyByHorizonResponse {
  start: string
  end: string
  by_horizon: HorizonEntry[]
}
