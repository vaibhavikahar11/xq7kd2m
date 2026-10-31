/**
 * client.ts – Typed API client for the Wind Forecast Portal.
 *
 * All fetch calls use the relative path /api/... so they are transparently
 * proxied by the Vite dev server (→ localhost:8000) and routed by Vercel in
 * production (→ the Python serverless function).
 *
 * Never import `fetch` wrappers from libraries here – keeping this vanilla
 * makes the bundle smaller and the types explicit.
 */

import type {
  AccuracyByDateResponse,
  AccuracyByHorizonResponse,
  AccuracyByHourResponse,
  AccuracySummaryResponse,
  ConfigResponse,
  DecisionResponse,
} from './types'

const API_BASE = '/api'

// ── Response types (health) ───────────────────────────────────────────────────

export interface ConfigSnapshot {
  decision_cutoff_hour: number
  timezone: string
  start_date: string
  end_date: string
}

export interface HealthResponse {
  status: string
  version: string
  config: ConfigSnapshot
}

// ── Core fetch helper ─────────────────────────────────────────────────────────

/** Perform a GET request and parse JSON, throwing on non-2xx responses. */
async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    let detail = `API error ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      // ignore parse error; use default message
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

// ── Endpoint helpers ──────────────────────────────────────────────────────────

/** Fetch backend health status and active configuration. */
export async function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>('/health')
}

/** Fetch the active API configuration (date range, cutoff defaults). */
export async function fetchConfig(): Promise<ConfigResponse> {
  return getJson<ConfigResponse>('/config')
}

/**
 * Fetch the 48-row decision-time forecast for one delivery day.
 *
 * @param date        YYYY-MM-DD delivery date (within 2026-01-01–2026-01-31)
 * @param cutoffHour  Decision cutoff hour in Europe/London (0–23, default 9)
 */
export async function fetchDecision(
  date: string,
  cutoffHour: number = 9,
): Promise<DecisionResponse> {
  return getJson<DecisionResponse>(
    `/decision?date=${date}&cutoff_hour=${cutoffHour}`,
  )
}

/**
 * Fetch overall decision-time accuracy for a date range.
 *
 * @param start       YYYY-MM-DD start (inclusive)
 * @param end         YYYY-MM-DD end (inclusive)
 * @param cutoffHour  Decision cutoff hour (default 9)
 */
export async function fetchAccuracySummary(
  start: string,
  end: string,
  cutoffHour: number = 9,
): Promise<AccuracySummaryResponse> {
  return getJson<AccuracySummaryResponse>(
    `/accuracy/summary?start=${start}&end=${end}&cutoff_hour=${cutoffHour}`,
  )
}

/**
 * Fetch decision-time accuracy grouped by hour of day (0–23 Europe/London).
 */
export async function fetchAccuracyByHour(
  start: string,
  end: string,
  cutoffHour: number = 9,
): Promise<AccuracyByHourResponse> {
  return getJson<AccuracyByHourResponse>(
    `/accuracy/by-hour?start=${start}&end=${end}&cutoff_hour=${cutoffHour}`,
  )
}

/**
 * Fetch decision-time accuracy grouped by delivery date.
 */
export async function fetchAccuracyByDate(
  start: string,
  end: string,
  cutoffHour: number = 9,
): Promise<AccuracyByDateResponse> {
  return getJson<AccuracyByDateResponse>(
    `/accuracy/by-date?start=${start}&end=${end}&cutoff_hour=${cutoffHour}`,
  )
}

/**
 * Fetch accuracy grouped by forecast-horizon bucket.
 * Uses ALL publishTimes (no cutoff_hour).
 */
export async function fetchAccuracyByHorizon(
  start: string,
  end: string,
): Promise<AccuracyByHorizonResponse> {
  return getJson<AccuracyByHorizonResponse>(
    `/accuracy/by-horizon?start=${start}&end=${end}`,
  )
}
