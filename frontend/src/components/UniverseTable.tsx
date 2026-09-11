import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { RegimeBanner } from '@/components/RegimeBanner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { fetchLatestScan, fetchScanReport, type ScoreComponent, type TickerDetail } from '@/lib/api'
import { LAUNCHPAD_UNIVERSES } from '@/lib/universes'
import {
  SCORE_LABELS,
  SCORE_ORDER,
  filterReason,
  finalScore,
  isActionable,
  tierBadgeVariant,
} from '@/lib/scoring'
import { cn } from '@/lib/utils'

const STRATEGY_ID = 'launchpad'

// Inline, always-visible — the old dashboard showed these as small
// multiples directly in its Overview table; hiding them behind a click
// (as an earlier pass here did) was a step backward, not an improvement.
function FactorSparkbars({ scores }: { scores: Record<string, ScoreComponent> | undefined }) {
  return (
    <div className="flex items-end gap-1">
      {SCORE_ORDER.map((key) => {
        const component = scores?.[key]
        const pct =
          component && component.max > 0
            ? Math.max(6, Math.min(100, (component.score / component.max) * 100))
            : 0
        const label = SCORE_LABELS[key] ?? key
        return (
          <div
            key={key}
            className="flex h-6 w-2 items-end overflow-hidden rounded-[2px] bg-muted"
            title={component ? `${label}: ${component.score}/${component.max}` : `${label}: n/a`}
          >
            <div className="w-full rounded-[2px] bg-foreground/70" style={{ height: `${pct}%` }} />
          </div>
        )
      })}
    </div>
  )
}

function TickerDrawer({ ticker }: { ticker: TickerDetail }) {
  const scores = ticker.scores ?? {}
  return (
    <div className="bg-muted/30 px-4 py-4">
      {ticker.tier_reason && (
        <p className="text-sm text-foreground">
          <span className="text-muted-foreground">Tier reason: </span>
          {ticker.tier_reason}
        </p>
      )}
      <div className="mt-2 grid gap-3 sm:grid-cols-2">
        {SCORE_ORDER.filter((key) => scores[key]).map((key) => (
          <p key={key} className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{SCORE_LABELS[key] ?? key}</span>
            {' '}({scores[key].score}/{scores[key].max}): {scores[key].meaning}
          </p>
        ))}
      </div>
      {(ticker.sector_etf || (!ticker.eligible && filterReason(ticker))) && (
        <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
          {ticker.sector_etf && <span>Sector ETF: {ticker.sector_etf}</span>}
          {!ticker.eligible && filterReason(ticker) && (
            <span>Filter reason: {filterReason(ticker)}</span>
          )}
        </div>
      )}
    </div>
  )
}

export function UniverseTable() {
  const [universeId, setUniverseId] = useState(LAUNCHPAD_UNIVERSES[0].id)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const latestScan = useQuery({
    queryKey: ['scans', 'latest', { strategyId: STRATEGY_ID, universeId }],
    queryFn: () => fetchLatestScan({ strategyId: STRATEGY_ID, universeId }),
  })

  const report = useQuery({
    queryKey: ['scans', 'report', latestScan.data?.id],
    queryFn: () => fetchScanReport(latestScan.data!.id),
    enabled: latestScan.data != null,
  })

  function toggleRow(ticker: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(ticker)) next.delete(ticker)
      else next.add(ticker)
      return next
    })
  }

  return (
    <div>
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-foreground" htmlFor="universe-select">
          Universe
        </label>
        <Select value={universeId} onValueChange={setUniverseId}>
          <SelectTrigger id="universe-select" className="w-64">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LAUNCHPAD_UNIVERSES.map((universe) => (
              <SelectItem key={universe.id} value={universe.id}>
                {universe.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {latestScan.data && (
          <span className="text-sm text-muted-foreground">
            Scan date: {latestScan.data.scan_date}
          </span>
        )}
      </div>

      <div className="mt-4">
        {latestScan.isLoading && (
          <p className="text-sm text-muted-foreground">Loading latest scan…</p>
        )}
        {latestScan.isError && (
          <p className="text-sm text-destructive">
            No scan runs found for this universe yet.
          </p>
        )}
        {report.isLoading && latestScan.data && (
          <p className="text-sm text-muted-foreground">Loading universe report…</p>
        )}
        {report.isError && (
          <p className="text-sm text-destructive">
            Failed to load report: {(report.error as Error).message}
          </p>
        )}

        {report.data && (
          <div className="mb-4">
            <RegimeBanner regime={report.data.market_regime} />
          </div>
        )}

        {report.data && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Ticker</TableHead>
                <TableHead>Tier</TableHead>
                <TableHead>Final score</TableHead>
                <TableHead>Factors</TableHead>
                <TableHead>Filter reason</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.data.tickers.map((ticker) => {
                const isOpen = expanded.has(ticker.ticker)
                const actionable = isActionable(report.data.strategy_id, ticker)
                return (
                  <Fragment key={ticker.ticker}>
                    <TableRow
                      className="cursor-pointer"
                      aria-expanded={isOpen}
                      onClick={() => toggleRow(ticker.ticker)}
                    >
                      <TableCell>
                        <ChevronRight
                          className={cn(
                            'size-4 text-muted-foreground transition-transform',
                            isOpen && 'rotate-90'
                          )}
                        />
                      </TableCell>
                      <TableCell className="font-medium text-foreground">
                        <div className="flex items-center gap-2">
                          {ticker.ticker}
                          {actionable && (
                            <Badge variant="success">Actionable</Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={tierBadgeVariant(ticker.tier)}>{ticker.tier}</Badge>
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {finalScore(ticker) != null ? finalScore(ticker)!.toFixed(1) : '—'}
                      </TableCell>
                      <TableCell>
                        <FactorSparkbars scores={ticker.scores} />
                      </TableCell>
                      <TableCell className="max-w-xs truncate text-muted-foreground">
                        {!ticker.eligible ? filterReason(ticker) : '—'}
                      </TableCell>
                    </TableRow>
                    {isOpen && (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={6} className="p-0">
                          <TickerDrawer ticker={ticker} />
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                )
              })}
            </TableBody>
          </Table>
        )}

        {report.data && report.data.tickers.length === 0 && (
          <p className="text-sm text-muted-foreground">No tickers in this report.</p>
        )}
      </div>
    </div>
  )
}
