import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { fetchScanReport, fetchTickerHistory } from '@/lib/api'
import { SCORE_LABELS, SCORE_ORDER, finalScore, scoreGrade, tierBadgeVariant } from '@/lib/scoring'

const STRATEGY_ID = 'launchpad'
const MAX_TICKERS = 4

// docs/FINANCIAL_UI_REIMAGINED.md §3.5 (Compare, carried forward from the
// old dashboard's session-only Compare tab). Built as aligned factor bars
// across independently-fetched ticker columns rather than a merged table
// or radar chart -- see the build-sequence note for why (no charting
// library yet; a hand-rolled SVG radar would be thrown away once Plotly
// lands for item #7). Fixed SCORE_ORDER per column keeps each factor's
// row position identical across tickers, which is what makes this
// comparable at a glance despite each column fetching independently.
function CompareColumn({ ticker }: { ticker: string }) {
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
    return (
      <div className="min-w-[160px] flex-1 rounded-lg border border-border p-3">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    )
  }
  if (!latestRun) {
    return (
      <div className="min-w-[160px] flex-1 rounded-lg border border-border p-3">
        <div className="font-medium text-foreground">{ticker}</div>
        <p className="mt-1 text-sm text-muted-foreground">No Launchpad appearances.</p>
      </div>
    )
  }
  if (report.isLoading || report.isError || !report.data) {
    return (
      <div className="min-w-[160px] flex-1 rounded-lg border border-border p-3">
        <div className="font-medium text-foreground">{ticker}</div>
        <p className="mt-1 text-sm text-muted-foreground">
          {report.isError ? 'Failed to load.' : 'Loading…'}
        </p>
      </div>
    )
  }

  const detail = report.data.tickers.find((t) => t.ticker === ticker)
  if (!detail) {
    return (
      <div className="min-w-[160px] flex-1 rounded-lg border border-border p-3">
        <div className="font-medium text-foreground">{ticker}</div>
        <p className="mt-1 text-sm text-muted-foreground">Not found in latest report.</p>
      </div>
    )
  }

  const scores = detail.scores ?? {}
  const composite = finalScore(detail)

  return (
    <div className="min-w-[160px] flex-1 rounded-lg border border-border p-3">
      <div className="flex items-center gap-2">
        <span className="font-medium text-foreground">{ticker}</span>
        <Badge variant={tierBadgeVariant(detail.tier)}>{detail.tier}</Badge>
      </div>
      <div className="mt-1 text-2xl font-semibold text-foreground">{scoreGrade(composite)}</div>
      <div className="text-xs text-muted-foreground">
        {composite != null ? composite.toFixed(1) : '—'} · {latestRun.universe_id} ·{' '}
        {latestRun.scan_date}
      </div>
      <div className="mt-3 space-y-2">
        {SCORE_ORDER.map((key) => {
          const component = scores[key]
          const pct = component && component.max > 0 ? (component.score / component.max) * 100 : 0
          return (
            <div key={key} title={component?.meaning}>
              <div className="text-[0.7rem] text-muted-foreground">
                {SCORE_LABELS[key] ?? key}
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-foreground/70"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function CompareTickers() {
  const [input, setInput] = useState('')
  const [tickers, setTickers] = useState<string[]>([])

  function submit(e: FormEvent) {
    e.preventDefault()
    const parsed = [
      ...new Set(
        input
          .split(',')
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean),
      ),
    ].slice(0, MAX_TICKERS)
    setTickers(parsed)
  }

  return (
    <div>
      <form onSubmit={submit} className="flex flex-wrap items-center gap-3">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Tickers, comma-separated (e.g. AAPL, MSFT, GOOGL)"
          className="w-80"
          aria-label="Tickers to compare"
        />
        <Button type="submit" variant="outline">
          Compare
        </Button>
      </form>

      {tickers.length === 0 && (
        <p className="mt-3 text-sm text-muted-foreground">
          Enter up to {MAX_TICKERS} tickers to compare their latest Launchpad read side by side.
        </p>
      )}

      {tickers.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-3">
          {tickers.map((t) => (
            <CompareColumn key={t} ticker={t} />
          ))}
        </div>
      )}
    </div>
  )
}
