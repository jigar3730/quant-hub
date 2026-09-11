import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
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
import { fetchLatestScan, fetchScanReport, type TickerDetail } from '@/lib/api'
import { LAUNCHPAD_UNIVERSES } from '@/lib/universes'
import {
  SCORE_LABELS,
  SCORE_ORDER,
  filterReason,
  finalScore,
  isActionable,
} from '@/lib/scoring'
import { cn } from '@/lib/utils'

const STRATEGY_ID = 'launchpad'

function tierBadgeVariant(tier: string): 'default' | 'secondary' | 'outline' {
  if (tier === 'Tier 1') return 'default'
  if (tier === 'Tier 2') return 'secondary'
  return 'outline'
}

function ScoreBar({ score, max }: { score: number; max: number }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (score / max) * 100)) : 0
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-foreground/70" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">
        {score}/{max}
      </span>
    </div>
  )
}

function TickerDrawer({ ticker }: { ticker: TickerDetail }) {
  const scores = ticker.scores ?? {}
  return (
    <div className="grid gap-4 bg-muted/30 px-4 py-4 sm:grid-cols-2">
      <div>
        <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Score breakdown
        </h4>
        <dl className="mt-2 space-y-2">
          {SCORE_ORDER.filter((key) => scores[key]).map((key) => {
            const component = scores[key]
            return (
              <div key={key} className="flex items-center justify-between gap-3">
                <dt className="text-sm text-foreground">{SCORE_LABELS[key] ?? key}</dt>
                <dd className="flex items-center gap-2">
                  <ScoreBar score={component.score} max={component.max} />
                </dd>
              </div>
            )
          })}
        </dl>
      </div>
      <div>
        <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Detail
        </h4>
        <dl className="mt-2 space-y-1 text-sm">
          {ticker.tier_reason && (
            <div>
              <dt className="text-xs text-muted-foreground">Tier reason</dt>
              <dd className="text-foreground">{ticker.tier_reason}</dd>
            </div>
          )}
          {ticker.sector_etf && (
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Sector ETF</dt>
              <dd className="text-foreground">{ticker.sector_etf}</dd>
            </div>
          )}
          {!ticker.eligible && filterReason(ticker) && (
            <div>
              <dt className="text-xs text-muted-foreground">Filter reason</dt>
              <dd className="text-foreground">{filterReason(ticker)}</dd>
            </div>
          )}
          {Object.entries(scores).map(([key, component]) => (
            <div key={key} className="pt-1 text-xs text-muted-foreground">
              {SCORE_LABELS[key] ?? key}: {component.meaning}
            </div>
          ))}
        </dl>
      </div>
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
            Latest scan: {latestScan.data.scan_date} · {latestScan.data.regime_label}
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
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Ticker</TableHead>
                <TableHead>Tier</TableHead>
                <TableHead>Final score</TableHead>
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
                      <TableCell className="max-w-xs truncate text-muted-foreground">
                        {!ticker.eligible ? filterReason(ticker) : '—'}
                      </TableCell>
                    </TableRow>
                    {isOpen && (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={5} className="p-0">
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
