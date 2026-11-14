/**
 * AccuracyPage.tsx – Forecast accuracy analysis view.
 *
 * Four sections accessible via tab buttons:
 *   Summary    – overall MetricSet + suggested buffer
 *   By Hour    – MAE bar chart by hour of day (0-23 Europe/London)
 *   By Date    – MAE line chart by delivery date + worst-day table
 *   By Horizon – MAE bar chart by forecast-horizon bucket
 *
 * All decision-time sections share the cutoff_hour selector.
 * By-Horizon uses all publishTimes (no cutoff).
 *
 * Error convention: error = forecast - actual (positive = over-forecast).
 */

import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  fetchAccuracyByDate,
  fetchAccuracyByHorizon,
  fetchAccuracyByHour,
  fetchAccuracySummary,
} from '../api/client'
import type {
  AccuracyByDateResponse,
  AccuracyByHorizonResponse,
  AccuracyByHourResponse,
  AccuracySummaryResponse,
  MetricSetResponse,
} from '../api/types'
import CutoffSelector from '../components/CutoffSelector'
import MetricCard from '../components/MetricCard'

// ── Constants ─────────────────────────────────────────────────────────────────

const START = '2026-01-01'
const END = '2026-01-31'

type Tab = 'summary' | 'by-hour' | 'by-date' | 'by-horizon'

// ── Shared sub-components ─────────────────────────────────────────────────────

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="bg-red-900/40 border border-red-700 rounded px-4 py-3 text-red-300 text-sm">
      {message}
    </div>
  )
}

function Loading() {
  return <p className="text-slate-400 text-sm animate-pulse">Loading…</p>
}

/** Metric grid used across all views. */
function MetricGrid({ ms }: { ms: MetricSetResponse }) {
  return (
    <div className="flex flex-wrap gap-3">
      <MetricCard label="MAE" value={ms.mae} unit="MW" />
      <MetricCard label="RMSE" value={ms.rmse} unit="MW" />
      <MetricCard
        label="Bias"
        value={ms.bias}
        unit="MW"
        valueClass={ms.bias == null ? 'text-white' : ms.bias > 0 ? 'text-amber-400' : 'text-emerald-400'}
      />
      <MetricCard label="MAE %" value={ms.mae_pct} unit="%" decimals={2} />
      <MetricCard label="P50 |err|" value={ms.abs_p50} unit="MW" />
      <MetricCard label="P90 |err|" value={ms.abs_p90} unit="MW" />
      <MetricCard label="P95 |err|" value={ms.abs_p95} unit="MW" />
      <MetricCard label="Signed P5" value={ms.signed_p5} unit="MW" valueClass="text-blue-300" />
      <MetricCard label="Signed P50" value={ms.signed_p50} unit="MW" />
      <MetricCard label="Signed P95" value={ms.signed_p95} unit="MW" valueClass="text-amber-400" />
      <MetricCard label="Matched" value={ms.n_matched} />
      <MetricCard label="Excluded" value={ms.n_excluded} />
    </div>
  )
}

// ── Tab: Summary ──────────────────────────────────────────────────────────────

function SummaryTab({ cutoffHour }: { cutoffHour: number }) {
  const [data, setData] = useState<AccuracySummaryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchAccuracySummary(START, END, cutoffHour)
      .then((d) => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch((e: unknown) => {
        if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setLoading(false) }
      })
    return () => { cancelled = true }
  }, [cutoffHour])

  if (loading) return <Loading />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  return (
    <div className="space-y-6">
      {/* Suggested buffer */}
      <div className="bg-emerald-900/30 border border-emerald-700/50 rounded-xl px-5 py-4">
        <p className="text-xs text-emerald-400 uppercase tracking-wide mb-1">
          Suggested Reserve Buffer
        </p>
        <p className="text-2xl font-bold text-emerald-300">
          {data.suggested_buffer_mw != null
            ? `${data.suggested_buffer_mw.toLocaleString('en-GB', { maximumFractionDigits: 0 })} MW`
            : '—'}
        </p>
        <p className="text-xs text-slate-400 mt-2">{data.suggested_buffer_explanation}</p>
      </div>

      <MetricGrid ms={data.metrics} />

      <p className="text-xs text-slate-500">
        Error convention: error = forecast − actual (positive = over-forecast).
        Signed P5 = 5th percentile of signed errors; −P5 = 95th percentile of
        under-forecast magnitude.
      </p>
    </div>
  )
}

// ── Tab: By Hour ──────────────────────────────────────────────────────────────

function ByHourTab({ cutoffHour }: { cutoffHour: number }) {
  const [data, setData] = useState<AccuracyByHourResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchAccuracyByHour(START, END, cutoffHour)
      .then((d) => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch((e: unknown) => {
        if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setLoading(false) }
      })
    return () => { cancelled = true }
  }, [cutoffHour])

  if (loading) return <Loading />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  const chartData = data.by_hour.map((e) => ({
    hour: `${String(e.hour).padStart(2, '0')}:00`,
    mae: e.metrics.mae,
    bias: e.metrics.bias,
  }))

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-slate-300">MAE &amp; Bias by Hour of Day (Europe/London)</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="hour" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} interval={1} />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} unit=" MW" width={72} />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 6, fontSize: 12 }}
            formatter={(value) => { const n = Number(value); return [Number.isFinite(n) ? `${n.toLocaleString('en-GB', { maximumFractionDigits: 0 })} MW` : '—'] }}
          />
          <Bar dataKey="mae" name="MAE" fill="#60a5fa" radius={[3, 3, 0, 0]} />
          <Bar dataKey="bias" name="Bias" fill="#fbbf24" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <p className="text-xs text-slate-500">Blue = MAE (always ≥ 0). Amber = Bias (positive = over-forecast).</p>
    </div>
  )
}

// ── Tab: By Date ──────────────────────────────────────────────────────────────

function ByDateTab({ cutoffHour }: { cutoffHour: number }) {
  const [data, setData] = useState<AccuracyByDateResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchAccuracyByDate(START, END, cutoffHour)
      .then((d) => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch((e: unknown) => {
        if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setLoading(false) }
      })
    return () => { cancelled = true }
  }, [cutoffHour])

  if (loading) return <Loading />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  const chartData = data.by_date.map((e) => ({
    date: e.date.substring(5), // MM-DD
    mae: e.metrics.mae,
  }))

  // Worst 5 days by MAE
  const worst = [...data.by_date]
    .filter((e) => e.metrics.mae != null)
    .sort((a, b) => (b.metrics.mae ?? 0) - (a.metrics.mae ?? 0))
    .slice(0, 5)

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-slate-300">MAE by Delivery Date</h3>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={chartData} margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} interval={4} />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} unit=" MW" width={72} />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 6, fontSize: 12 }}
            formatter={(value) => { const n = Number(value); return [Number.isFinite(n) ? `${n.toLocaleString('en-GB', { maximumFractionDigits: 0 })} MW` : '—'] }}
          />
          <Line
            type="monotone"
            dataKey="mae"
            name="MAE"
            stroke="#f87171"
            strokeWidth={2}
            dot={{ r: 3, fill: '#f87171' }}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>

      <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide mt-4">
        5 Worst Days by MAE
      </h4>
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-xs text-left">
          <thead className="bg-slate-800 text-slate-400">
            <tr>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2 text-right">MAE (MW)</th>
              <th className="px-3 py-2 text-right">Bias (MW)</th>
              <th className="px-3 py-2 text-right">n matched</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {worst.map((e) => (
              <tr key={e.date} className="hover:bg-slate-800/40">
                <td className="px-3 py-1.5 font-mono text-slate-300">{e.date}</td>
                <td className="px-3 py-1.5 text-right text-red-400 font-semibold">
                  {e.metrics.mae?.toLocaleString('en-GB', { maximumFractionDigits: 0 }) ?? '—'}
                </td>
                <td className={`px-3 py-1.5 text-right font-medium ${(e.metrics.bias ?? 0) > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {e.metrics.bias != null
                    ? `${e.metrics.bias > 0 ? '+' : ''}${e.metrics.bias.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`
                    : '—'}
                </td>
                <td className="px-3 py-1.5 text-right text-slate-400">{e.metrics.n_matched}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Tab: By Horizon ───────────────────────────────────────────────────────────

function ByHorizonTab() {
  const [data, setData] = useState<AccuracyByHorizonResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchAccuracyByHorizon(START, END)
      .then((d) => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch((e: unknown) => {
        if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setLoading(false) }
      })
    return () => { cancelled = true }
  }, [])

  if (loading) return <Loading />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  const chartData = data.by_horizon.map((e) => ({
    bucket: e.bucket,
    mae: e.metrics.mae,
    bias: e.metrics.bias,
    n: e.metrics.n_matched,
  }))

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-slate-300">MAE &amp; Bias by Forecast Horizon (all publishTimes)</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="bucket" tick={{ fill: '#94a3b8', fontSize: 11 }} tickLine={false} />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} unit=" MW" width={72} />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 6, fontSize: 12 }}
            formatter={(value) => { const n = Number(value); return [Number.isFinite(n) ? `${n.toLocaleString('en-GB', { maximumFractionDigits: 0 })} MW` : '—'] }}
          />
          <Bar dataKey="mae" name="MAE" fill="#818cf8" radius={[3, 3, 0, 0]} />
          <Bar dataKey="bias" name="Bias" fill="#fbbf24" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>

      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-xs text-left">
          <thead className="bg-slate-800 text-slate-400">
            <tr>
              <th className="px-3 py-2">Bucket</th>
              <th className="px-3 py-2 text-right">n</th>
              <th className="px-3 py-2 text-right">MAE (MW)</th>
              <th className="px-3 py-2 text-right">Bias (MW)</th>
              <th className="px-3 py-2 text-right">RMSE (MW)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {data.by_horizon.map((e) => (
              <tr key={e.bucket} className="hover:bg-slate-800/40">
                <td className="px-3 py-1.5 font-mono text-slate-300">{e.bucket}</td>
                <td className="px-3 py-1.5 text-right text-slate-400">{e.metrics.n_matched}</td>
                <td className="px-3 py-1.5 text-right text-indigo-300">
                  {e.metrics.mae?.toLocaleString('en-GB', { maximumFractionDigits: 0 }) ?? '—'}
                </td>
                <td className={`px-3 py-1.5 text-right font-medium ${(e.metrics.bias ?? 0) > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {e.metrics.bias != null
                    ? `${e.metrics.bias > 0 ? '+' : ''}${e.metrics.bias.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`
                    : '—'}
                </td>
                <td className="px-3 py-1.5 text-right text-slate-400">
                  {e.metrics.rmse?.toLocaleString('en-GB', { maximumFractionDigits: 0 }) ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function AccuracyPage() {
  const [tab, setTab] = useState<Tab>('summary')
  const [cutoffHour, setCutoffHour] = useState(9)

  const tabs: { id: Tab; label: string }[] = [
    { id: 'summary', label: 'Summary' },
    { id: 'by-hour', label: 'By Hour' },
    { id: 'by-date', label: 'By Date' },
    { id: 'by-horizon', label: 'By Horizon' },
  ]

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-5">
      {/* ── Controls ──────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-base font-semibold text-slate-200">
          Forecast Accuracy — January 2026
        </h1>
        {tab !== 'by-horizon' && (
          <CutoffSelector value={cutoffHour} onChange={setCutoffHour} />
        )}
      </div>

      {/* ── Tabs ──────────────────────────────────────────────────────────── */}
      <div className="flex gap-1 border-b border-slate-700 pb-0">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm rounded-t transition-colors ${
              tab === t.id
                ? 'bg-slate-800 text-white border border-b-slate-800 border-slate-700'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Tab content ───────────────────────────────────────────────────── */}
      <div className="pt-2">
        {tab === 'summary' && <SummaryTab cutoffHour={cutoffHour} />}
        {tab === 'by-hour' && <ByHourTab cutoffHour={cutoffHour} />}
        {tab === 'by-date' && <ByDateTab cutoffHour={cutoffHour} />}
        {tab === 'by-horizon' && <ByHorizonTab />}
      </div>
    </div>
  )
}
