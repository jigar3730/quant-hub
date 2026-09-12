import { Route, Routes } from 'react-router'
import { AppLayout } from '@/components/AppLayout'
import { CompareTickers } from '@/components/CompareTickers'
import { OverlapMatrix } from '@/components/OverlapMatrix'
import { ScansTable } from '@/components/ScansTable'
import { TickerHistory } from '@/components/TickerHistory'
import { TodaysPriorities } from '@/components/TodaysPriorities'
import { UniverseTable } from '@/components/UniverseTable'

function PrioritiesPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-foreground">Today's priorities</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Every actionable setup across all universes today, ranked.
      </p>
      <div className="mt-4">
        <TodaysPriorities />
      </div>

      <section className="mt-10">
        <h2 className="text-lg font-semibold text-foreground">Multi-universe overlap</h2>
        <div className="mt-3">
          <OverlapMatrix />
        </div>
      </section>
    </div>
  )
}

function UniversePage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-foreground">Universe explorer</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Every ticker in one universe's latest scan.
      </p>
      <div className="mt-4">
        <UniverseTable />
      </div>
    </div>
  )
}

function TickerPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-foreground">Ticker 360</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Technical, fundamental, ML outcomes, and history for one ticker.
      </p>
      <div className="mt-4">
        <TickerHistory />
      </div>
    </div>
  )
}

function ComparePage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-foreground">Compare tickers</h1>
      <div className="mt-4">
        <CompareTickers />
      </div>
    </div>
  )
}

function ScansPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-foreground">Recent scans</h1>
      <div className="mt-4">
        <ScansTable />
      </div>
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<PrioritiesPage />} />
        <Route path="/universe" element={<UniversePage />} />
        <Route path="/ticker" element={<TickerPage />} />
        <Route path="/ticker/:symbol" element={<TickerPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/scans" element={<ScansPage />} />
      </Route>
    </Routes>
  )
}

export default App
