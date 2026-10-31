/**
 * MetricCard.tsx – Displays a single labelled metric value.
 *
 * Renders "—" (en-dash) for null values so missing metrics are explicit,
 * never confused with zero.
 */

interface Props {
  label: string
  value: number | null | undefined
  /** Number of decimal places (default 0) */
  decimals?: number
  /** Unit string appended after the value, e.g. "MW" or "%" */
  unit?: string
  /** Optional CSS class for the value text (e.g. coloured highlights) */
  valueClass?: string
}

export default function MetricCard({
  label,
  value,
  decimals = 0,
  unit,
  valueClass = 'text-white',
}: Props) {
  const formatted =
    value == null ? '—' : value.toLocaleString('en-GB', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })

  return (
    <div className="bg-slate-800 rounded-lg px-4 py-3 flex flex-col gap-1 min-w-[130px]">
      <span className="text-xs text-slate-400 uppercase tracking-wide leading-tight">
        {label}
      </span>
      <span className={`text-lg font-semibold leading-none ${valueClass}`}>
        {formatted}
        {value != null && unit ? (
          <span className="text-sm font-normal text-slate-400 ml-1">{unit}</span>
        ) : null}
      </span>
    </div>
  )
}
