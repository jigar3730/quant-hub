import { useQuery } from '@tanstack/react-query'
import { fetchTickerHistory, type TickerHistoryRow } from '@/lib/api'
import { tierHeatClass } from '@/lib/scoring'

// Zero new backend work (docs/FINANCIAL_UI_REIMAGINED.md §1.3) — reuses
// /tickers/{ticker}/history (actionable_only=false, so filtered/Tier 3
// appearances show too, not just actionable ones) and groups appearances
// by universe into a chronological strip rather than a true calendar grid:
// Launchpad (daily) and Lynch (weekly) run on very different cadences, so
// aligning both to one shared date axis would leave the sparser strategy
// mostly empty cells. A per-universe strip stays honest about that instead
// of implying a density that isn't there.
export function TickerAuditTrail({ ticker }: { ticker: string }) {
  const history = useQuery({
    queryKey: ['tickers', ticker, 'history', 'audit-trail'],
    queryFn: () => fetchTickerHistory(ticker, { actionableOnly: false, limit: 500, offset: 0 }),
  })

  if (history.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading audit trail…</p>
  }
  if (history.isError) {
    return (
      <p className="text-sm text-destructive">
        Failed to load audit trail: {(history.error as Error).message}
      </p>
    )
  }
  if (history.data!.rows.length === 0) {
    return <p className="text-sm text-muted-foreground">No scan history for {ticker}.</p>
  }

  const byUniverse = new Map<string, TickerHistoryRow[]>()
  for (const row of history.data!.rows) {
    const key = `${row.strategy_id}:${row.universe_id}`
    const rows = byUniverse.get(key) ?? []
    rows.push(row)
    byUniverse.set(key, rows)
  }

  return (
    <div className="space-y-3">
      {[...byUniverse.entries()].map(([key, rows]) => {
        // API returns newest-first; reverse for oldest -> newest, left to right.
        const chronological = [...rows].reverse()
        const first = rows[0]
        return (
          <div key={key}>
            <div className="mb-1 text-xs text-muted-foreground">
              {first.strategy_label ?? first.strategy_id} · {first.universe_id}
            </div>
            <div className="flex flex-wrap gap-1">
              {chronological.map((row) => (
                <div
                  key={row.run_id}
                  className={`size-4 rounded-[3px] ${tierHeatClass(row.tier)}`}
                  title={`${row.scan_date}: ${row.tier_label ?? row.tier ?? 'no tier'}`}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
