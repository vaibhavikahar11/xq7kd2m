/**
 * App.tsx – Root component with top-nav and React Router routes.
 *
 * Pages:
 *   /          → DecisionPage  (day-ahead forecast view)
 *   /accuracy  → AccuracyPage (accuracy analysis view)
 *   /health    → HealthPage   (backend status / dev)
 */

import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'

import AccuracyPage from './pages/AccuracyPage'
import DecisionPage from './pages/DecisionPage'
import HealthPage from './pages/HealthPage'

const navClass = ({ isActive }: { isActive: boolean }) =>
  isActive
    ? 'text-emerald-400 text-sm font-semibold border-b-2 border-emerald-400 pb-0.5'
    : 'text-slate-400 text-sm hover:text-slate-200 transition-colors'

export default function App() {
  return (
    <BrowserRouter>
      {/* ── Top navigation ─────────────────────────────────────────────── */}
      <nav className="bg-slate-900 border-b border-slate-700 px-6 py-3 flex items-center gap-6 sticky top-0 z-10">
        <span className="text-white font-bold tracking-tight flex items-center gap-2">
          <span className="text-emerald-400">⚡</span>
          Wind Forecast Portal
        </span>

        <NavLink to="/" end className={navClass}>
          Decision View
        </NavLink>
        <NavLink to="/accuracy" className={navClass}>
          Accuracy
        </NavLink>
        <NavLink to="/health" className={navClass}>
          Status
        </NavLink>
      </nav>

      {/* ── Main content ───────────────────────────────────────────────── */}
      <main className="min-h-screen bg-slate-950 text-slate-100">
        <Routes>
          <Route path="/" element={<DecisionPage />} />
          <Route path="/accuracy" element={<AccuracyPage />} />
          <Route path="/health" element={<HealthPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
