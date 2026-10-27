/**
 * Typed API client.
 *
 * All fetch calls use the relative path /api/... so they are transparently
 * proxied by the Vite dev server (→ localhost:8000) and routed by Vercel in
 * production (→ the Python serverless function).
 *
 * Never import `fetch` wrappers from libraries here – keeping this vanilla
 * makes the bundle smaller and the types explicit.
 */

const API_BASE = '/api'

// ─── Response types (mirror backend Pydantic schemas) ──────────────────────

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

// ─── Fetch helpers ──────────────────────────────────────────────────────────

/** Perform a GET request and parse JSON, throwing on non-2xx responses. */
async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    throw new Error(`API error ${res.status} on GET ${path}`)
  }
  return res.json() as Promise<T>
}

/** Fetch backend health status and active configuration. */
export async function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>('/health')
}
