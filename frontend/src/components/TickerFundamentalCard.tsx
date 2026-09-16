import { useQuery } from '@tanstack/react-query'
import { LynchChecksList } from '@/components/LynchChecksList'
import { LynchScoreBar } from '@/components/LynchScoreBar'
import { Badge } from '@/components/ui/badge'
import { fetchScanReport, fetchTickerHistory } from '@/lib/api'
import { LYNCH_CATEGORY_LABELS, LYNCH_CATEGORY_VARIANT, lynchTierVariant } from '@/lib/lynch'

const STRATEGY_ID = 'lynch'

// Fundamental (Lynch) card — docs/FINANCIAL_UI_REIMAGINED.md §1.1/§1.2,
// corrected design (2026-09-12 research): Lynch has no per-factor
// {score,max} like Launchpad, just boolean pass/fail checks aggregated
// into one lynch_score percentage. So this renders a score gauge, tier +
// category badges, and the authoritative checks list directly — not
// invented letter grades or re-derived thresholds.
export function TickerFundamentalCard({ ticker }: { ticker: string }) {
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
    return <p className="text-sm text-muted-foreground">No Lynch appearances for {ticker}.</p>
  }
  if (report.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading latest fundamental read…</p>
  }
  if (report.isError) {
    return (
      <p className="text-sm text-destructive">
        Failed to load report: {(report.error as Error).message}
      </p>
    )
  }

  const detail = report.data!.tickers.find((t) => t.ticker === ticker)
  if (!detail) {
    return <p className="text-sm text-muted-foreground">Ticker not found in latest report.</p>
  }

  const categories = detail.categories ?? []
  const checks = detail.checks ?? []
  const score = detail.lynch_score ?? null

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-center gap-3">
        <LynchScoreBar score={score} barClassName="h-2 w-24" />
        <Badge variant={lynchTierVariant(detail.tier)}>{detail.tier}</Badge>
        {categories.map((c) => (
          <Badge key={c} variant={LYNCH_CATEGORY_VARIANT[c] ?? 'outline'}>
            {LYNCH_CATEGORY_LABELS[c] ?? c}
          </Badge>
        ))}
        <span className="text-sm text-muted-foreground">
          {detail.company_name ?? ticker}
          {detail.sector ? ` · ${detail.sector}` : ''}
        </span>
      </div>

      {detail.investor_summary && (
        <p className="mt-2 text-sm text-muted-foreground">{detail.investor_summary}</p>
      )}

      <div className="mt-3">
        <LynchChecksList checks={checks} />
      </div>
    </div>
  )
}
