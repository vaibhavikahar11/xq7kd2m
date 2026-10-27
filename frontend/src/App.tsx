import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import HealthPage from './pages/HealthPage'

/**
 * Root component.
 *
 * Routing is kept here so future pages (DecisionView, AccuracyView) are
 * added simply by appending <Route> entries and NavLinks.
 */
export default function App() {
  return (
    <BrowserRouter>
      <nav className="bg-slate-800 border-b border-slate-700 px-6 py-3 flex items-center gap-6">
        <span className="text-white font-bold tracking-tight">🌬️ Wind Forecast Portal</span>
        <NavLink
          to="/"
          className={({ isActive }) =>
            isActive
              ? 'text-emerald-400 text-sm font-medium'
              : 'text-slate-400 text-sm hover:text-slate-200'
          }
        >
          Status
        </NavLink>
        {/* Phase 3 – Decision and Accuracy links go here */}
      </nav>

      <Routes>
        <Route path="/" element={<HealthPage />} />
      </Routes>
    </BrowserRouter>
  )
}
