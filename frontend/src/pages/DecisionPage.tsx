/**
 * DecisionPage.tsx – Day-ahead wind forecast decision view.
 *
 * Shows the 48 half-hourly forecast vs actual series for one delivery day,
 * together with a day-summary panel and the underlying data table.
 *
 * Key UX choices:
 *   • connectNulls={false} on Recharts lines → missing data shows as a visible gap
 *   • Missing rows in the table show "No forecast available" explicitly
 *   • Date picker constrained to 2026-01-01..2026-01-31 (validated server-side too)
 *   • cutoff_hour selector propagates to both the fetch and the label
 */

import { useEffect, useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { fetchDecision } from '../api/client'
import type { DecisionResponse, HalfHourRow } from '../api/types'
import CutoffSelector from '../components/CutoffSelector'
import MetricCard from '../components/MetricCard'

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Format an ISO-8601 UTC timestamp to HH:MM (UTC). */
function toHHMM(iso: string): string {
  return iso.substring(11, 16)
}

/** Format an ISO date-string for the native date input. */
function isoDate(iso: string): string {
  return iso.substring(0, 10)
}

// ── Chart tooltip ─────────────────────────────────────────────────────────────

interface TooltipPayloadEntry {
  name: string
  value: number | null
  color: string
}

interface CustomTooltipProps {
  active?: boolean
  payload?: TooltipPayloadEntry[]
  label?: string
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-xs shadow-lg">
      <p className="text-slate-400 mb-1">{label} UTC</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}:{' '}
          <strong>
            {p.value == null ? 'missing' : `${p.value.toLocaleString('en-GB')} MW`}
          </strong>
        </p>
      ))}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function DecisionPage() {
  const [date, setDate] = useState('2026-01-15')
  const [cutoffHour, setCutoffHour] = useState(9)
  const [data, setData] = useState<DecisionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchDecision(date, cutoffHour)
      .then((d) => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [date, cutoffHour])

  // ── Chart data ─────────────────────────────────────────────────────────────
  const chartData = (data?.rows ?? []).map((r: HalfHourRow) => ({
    time: toHHMM(r.startTime),
    forecast: r.forecast_mw,
    actual: r.actual_mw,
  }))

  const summary = data?.summary

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      {/* ── Controls ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs text-slate-400 mb-1 uppercase tracking-wide">
            Delivery Date
          </label>
          <input
            type="date"
            min="2026-01-01"
            max="2026-01-31"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="rounded bg-slate-700 border border-slate-600 px-3 py-1.5
                       text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
        </div>
        <CutoffSelector value={cutoffHour} onChange={setCutoffHour} disabled={loading} />
        {data && (
          <p className="text-xs text-slate-500 self-end pb-1.5">
            Cutoff in use:{' '}
            <span className="text-slate-300 font-mono">
              {isoDate(data.cutoff_local)} {String(data.cutoff_hour).padStart(2, '0')}:00 Europe/London
            </span>{' '}
            ({data.cutoff_utc.substring(0, 16)} UTC)
          </p>
        )}
      </div>

      {/* ── Status ────────────────────────────────────────────────────────── */}
      {loading && (
        <p className="text-slate-400 text-sm animate-pulse">Loading forecast…</p>
      )}
      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded px-4 py-3 text-red-300 text-sm">
          {error}
        </div>
      )}

      {data && !loading && (
        <>
          {/* ── Day summary cards ────────────────────────────────────────── */}
          <div className="flex flex-wrap gap-3">
            <MetricCard label="Peak Forecast" value={summary?.peak_forecast_mw ?? null} unit="MW" valueClass="text-blue-300" />
            <MetricCard label="Avg Forecast" value={summary?.avg_forecast_mw ?? null} unit="MW" valueClass="text-blue-300" />
            <MetricCard label="Total Forecast" value={summary?.total_forecast_mwh ?? null} unit="MWh" valueClass="text-blue-300" />
            <MetricCard label="Peak Actual" value={summary?.peak_actual_mw ?? null} unit="MW" valueClass="text-emerald-300" />
            <MetricCard label="Avg Actual" value={summary?.avg_actual_mw ?? null} unit="MW" valueClass="text-emerald-300" />
            <MetricCard label="Total Actual" value={summary?.total_actual_mwh ?? null} unit="MWh" valueClass="text-emerald-300" />
            <MetricCard
              label="Missing Half-Hours"
              value={summary?.missing_half_hours ?? null}
              valueClass={summary?.missing_half_hours ? 'text-amber-400' : 'text-slate-300'}
            />
          </div>

          {/* ── Chart ────────────────────────────────────────────────────── */}
          <div className="bg-slate-800/60 rounded-xl p-4">
            <h2 className="text-sm font-medium text-slate-300 mb-3">
              Forecast vs Actual — {date}
            </h2>
            <ResponsiveContainer width="100%" height={340}>
              <ComposedChart data={chartData} margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                  dataKey="time"
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  tickLine={false}
                  interval={7}
                />
                <YAxis
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  unit=" MW"
                  width={72}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  formatter={(v: string) =>
                    <span className="text-xs text-slate-300">{v}</span>
                  }
                />
                {/* connectNulls={false} → visible gap where data is missing */}
                <Line
                  type="monotone"
                  dataKey="forecast"
                  name="Forecast"
                  stroke="#60a5fa"
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="actual"
                  name="Actual"
                  stroke="#34d399"
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* ── Data table ───────────────────────────────────────────────── */}
          <div className="overflow-x-auto rounded-xl border border-slate-700">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-800 text-slate-400 uppercase tracking-wide">
                <tr>
                  <th className="px-3 py-2">Time (UTC)</th>
                  <th className="px-3 py-2 text-right">Forecast (MW)</th>
                  <th className="px-3 py-2 text-right">Actual (MW)</th>
                  <th className="px-3 py-2 text-right">Error (MW)</th>
                  <th className="px-3 py-2 text-right">Horizon (h)</th>
                  <th className="px-3 py-2">Published</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {data.rows.map((r) => {
                  const error =
                    r.forecast_mw != null && r.actual_mw != null
                      ? r.forecast_mw - r.actual_mw
                      : null
                  const errorColor =
                    error == null
                      ? ''
                      : error > 0
                      ? 'text-amber-400'
                      : 'text-emerald-400'
                  return (
                    <tr
                      key={r.startTime}
                      className={`${r.missing_forecast ? 'bg-red-950/20' : 'hover:bg-slate-800/40'}`}
                    >
                      <td className="px-3 py-1.5 font-mono text-slate-300">
                        {toHHMM(r.startTime)}
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        {r.missing_forecast ? (
                          <span className="text-red-400 italic">No forecast available</span>
                        ) : (
                          <span className="text-blue-300">
                            {r.forecast_mw?.toLocaleString('en-GB')}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-right text-emerald-300">
                        {r.actual_mw?.toLocaleString('en-GB') ?? '—'}
                      </td>
                      <td className={`px-3 py-1.5 text-right font-medium ${errorColor}`}>
                        {error == null
                          ? '—'
                          : `${error > 0 ? '+' : ''}${error.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`}
                      </td>
                      <td className="px-3 py-1.5 text-right text-slate-400">
                        {r.horizon_hours?.toFixed(1) ?? '—'}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-slate-500">
                        {r.publishTime ? r.publishTime.substring(0, 16) : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
