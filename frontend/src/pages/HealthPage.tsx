import { useEffect, useState } from 'react'
import { fetchHealth, type HealthResponse } from '../api/client'

type LoadState = 'idle' | 'loading' | 'ok' | 'error'

/**
 * Placeholder landing page that calls /api/health on mount.
 *
 * This page serves as a wiring check: if the card turns green the frontend
 * can reach the backend and the active config is correct.  It will be
 * replaced by the Decision View in Phase 3.
 */
export default function HealthPage() {
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [data, setData] = useState<HealthResponse | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  useEffect(() => {
    setLoadState('loading')
    fetchHealth()
      .then((d) => {
        setData(d)
        setLoadState('ok')
      })
      .catch((e: unknown) => {
        setErrorMsg(e instanceof Error ? e.message : 'Unknown error')
        setLoadState('error')
      })
  }, [])

  return (
    <main className="min-h-screen bg-slate-900 text-slate-100 flex flex-col items-center justify-center p-8 gap-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold mb-1">Backend Status</h1>
        <p className="text-slate-400 text-sm">
          Verifies the API is reachable and shows the active configuration.
        </p>
      </div>

      {loadState === 'loading' && (
        <p className="text-yellow-400 animate-pulse">Connecting to backend…</p>
      )}

      {loadState === 'error' && (
        <div className="bg-red-900/40 border border-red-600 rounded-xl p-5 max-w-sm w-full text-center">
          <p className="text-red-300 font-semibold mb-1">Backend unreachable</p>
          <p className="text-red-400 text-sm font-mono">{errorMsg}</p>
          <p className="text-slate-400 text-xs mt-3">
            Make sure <code className="text-slate-300">uvicorn</code> is running on port 8000,
            or run <code className="text-slate-300">docker compose up --build</code>.
          </p>
        </div>
      )}

      {loadState === 'ok' && data && (
        <div className="bg-emerald-900/30 border border-emerald-600 rounded-xl p-6 max-w-md w-full">
          {/* Status badge */}
          <div className="flex items-center gap-3 mb-5">
            <span className="w-3 h-3 rounded-full bg-emerald-400 animate-pulse shrink-0" />
            <span className="font-semibold text-emerald-300 text-lg">
              API {data.status} &mdash; v{data.version}
            </span>
          </div>

          {/* Config table */}
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 text-sm">
            <dt className="text-slate-400">Decision cutoff</dt>
            <dd className="font-mono text-white">
              {String(data.config.decision_cutoff_hour).padStart(2, '0')}:00{' '}
              {data.config.timezone}
            </dd>

            <dt className="text-slate-400">Timezone</dt>
            <dd className="font-mono text-white">{data.config.timezone}</dd>

            <dt className="text-slate-400">Delivery period</dt>
            <dd className="font-mono text-white">
              {data.config.start_date} → {data.config.end_date}
            </dd>
          </dl>

          <p className="text-slate-500 text-xs mt-5">
            This page is a wiring check. Decision View and Accuracy View will be added in Phase 3.
          </p>
        </div>
      )}
    </main>
  )
}
