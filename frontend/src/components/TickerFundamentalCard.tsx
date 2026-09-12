import { useQuery } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
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
        <div className="flex items-center gap-2">
          <div className="h-2 w-24 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-foreground/70"
              style={{ width: `${Math.max(0, Math.min(100, score ?? 0))}%` }}
            />
          </div>
          <span className="text-sm font-medium text-foreground tabular-nums">
            {score != null ? score.toFixed(0) : '—'}
          </span>
        </div>
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

      {checks.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {checks.map((c) => (
            <li
              key={c.rule}
              className="flex items-start gap-2 text-sm"
              title={c.why_it_matters}
            >
              {c.passed ? (
                <Check className="mt-0.5 size-3.5 shrink-0 text-success" />
              ) : (
                <X className="mt-0.5 size-3.5 shrink-0 text-destructive" />
              )}
              <span className="text-foreground">{c.label}</span>
              <span className="text-muted-foreground">— {c.plain_value}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
