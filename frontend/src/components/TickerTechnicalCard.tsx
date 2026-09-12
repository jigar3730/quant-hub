import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { fetchScanReport, fetchTickerHistory } from '@/lib/api'
import {
  finalScore,
  isActionable,
  orderedScoreKeys,
  scoreGrade,
  scoreLabel,
  tierBadgeVariant,
} from '@/lib/scoring'

const STRATEGY_ID = 'launchpad'

// Composite + per-factor letter grades (docs/FINANCIAL_UI_REIMAGINED.md
// §1.1) for a ticker's most recent Launchpad appearance. Finds the latest
// run via the same history query TickerAuditTrail uses (same queryKey ->
// deduped by React Query, not a second network round trip), then fetches
// that one run's full report to get the 5-factor breakdown (history rows
// only carry 3 of the 5 factors as flat fields, not the full {score,max}
// shape this needs).
export function TickerTechnicalCard({ ticker }: { ticker: string }) {
  const history = useQuery({
    queryKey: ['tickers', ticker, 'history', 'audit-trail'],
    queryFn: () => fetchTickerHistory(ticker, { actionableOnly: false, limit: 500, offset: 0 }),
  })

  const latestRun = history.data?.rows.find((r) => r.strategy_id === STRATEGY_ID)

  const report = useQuery({
    queryKey: ['scans', 'report', latestRun?.run_id],
    queryFn: () => fetchScanReport(latestRun!.run_id),
    enabled: latestRun != null,
  })

  if (history.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }
  if (!latestRun) {
    return (
      <p className="text-sm text-muted-foreground">
        No Launchpad appearances for {ticker}.
      </p>
    )
  }
  if (report.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading latest technical read…</p>
  }
  if (report.isError) {
    return (
      <p className="text-sm text-destructive">
        Failed to load report: {(report.error as Error).message}
      </p>
    )
  }

  const tickerDetail = report.data!.tickers.find((t) => t.ticker === ticker)
  if (!tickerDetail) {
    return <p className="text-sm text-muted-foreground">Ticker not found in latest report.</p>
  }

  const composite = finalScore(tickerDetail)
  const scores = tickerDetail.scores ?? {}

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-3xl font-semibold text-foreground">{scoreGrade(composite)}</span>
        <Badge variant={tierBadgeVariant(tickerDetail.tier)}>{tickerDetail.tier}</Badge>
        {isActionable(STRATEGY_ID, tickerDetail) && <Badge variant="success">Actionable</Badge>}
        <span className="text-sm text-muted-foreground">
          {composite != null ? composite.toFixed(1) : '—'} score · {latestRun.universe_id} ·{' '}
          {latestRun.scan_date}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {orderedScoreKeys(scores).map((key) => {
          const component = scores[key]
          const pct = component.max > 0 ? (component.score / component.max) * 100 : null
          return (
            <div
              key={key}
              className="rounded-md border border-border px-2.5 py-1.5 text-center"
              title={component.meaning}
            >
              <div className="text-[0.7rem] text-muted-foreground">
                {scoreLabel(key)}
              </div>
              <div className="text-lg font-semibold text-foreground">{scoreGrade(pct)}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
