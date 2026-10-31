/**
 * CutoffSelector.tsx – Labeled dropdown for the decision cutoff hour.
 *
 * The UI allows 6–12 (Europe/London) per spec; other hours outside that
 * range are valid API values but not surfaced in the what-if selector.
 */

interface Props {
  value: number
  onChange: (hour: number) => void
  disabled?: boolean
}

const HOURS = [6, 7, 8, 9, 10, 11, 12]

export default function CutoffSelector({ value, onChange, disabled }: Props) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-300">
      <span className="whitespace-nowrap">Decision cutoff</span>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        className="rounded bg-slate-700 border border-slate-600 px-2 py-1
                   text-white text-sm focus:outline-none focus:ring-2
                   focus:ring-emerald-500 disabled:opacity-50"
      >
        {HOURS.map((h) => (
          <option key={h} value={h}>
            D-1 {String(h).padStart(2, '0')}:00 Europe/London
          </option>
        ))}
      </select>
    </label>
  )
}
