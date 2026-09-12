import { CompareTickers } from '@/components/CompareTickers'
import { OverlapMatrix } from '@/components/OverlapMatrix'
import { ScansTable } from '@/components/ScansTable'
import { TickerHistory } from '@/components/TickerHistory'
import { TodaysPriorities } from '@/components/TodaysPriorities'
import { UniverseTable } from '@/components/UniverseTable'

function App() {
  return (
    <div className="mx-auto max-w-5xl p-8">
      <h1 className="text-foreground text-2xl font-semibold">Quant Hub</h1>
      <p className="text-muted-foreground mt-1 text-sm">
        Phase 2 design-system scaffold — reading live data from the Phase 1 API.
      </p>

      <section className="mt-8">
        <h2 className="text-foreground text-lg font-semibold">Today's priorities</h2>
        <div className="mt-3">
          <TodaysPriorities />
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-foreground text-lg font-semibold">Multi-universe overlap</h2>
        <div className="mt-3">
          <OverlapMatrix />
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-foreground text-lg font-semibold">Universe explorer</h2>
        <div className="mt-3">
          <UniverseTable />
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-foreground text-lg font-semibold">Ticker history</h2>
        <div className="mt-3">
          <TickerHistory />
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-foreground text-lg font-semibold">Compare tickers</h2>
        <div className="mt-3">
          <CompareTickers />
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-foreground text-lg font-semibold">Recent scans</h2>
        <div className="mt-3">
          <ScansTable />
        </div>
      </section>
    </div>
  )
}

export default App
