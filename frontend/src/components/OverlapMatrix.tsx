import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { fetchCommandCenter, type ActionableTicker } from '@/lib/api'
import { tierBadgeVariant } from '@/lib/scoring'

const STRATEGY_ID = 'launchpad'

// No backend query for this exists (verified — see
// docs/FINANCIAL_UI_REIMAGINED.md §2.2) but it doesn't need one: every
// actionable ticker across every universe for today is already in
// /command-center's `actionable_tickers`. Grouping by ticker and keeping
// only tickers that appear under more than one universe_id *is* the
// overlap matrix, entirely client-side.
function groupOverlaps(tickers: ActionableTicker[]) {
  const byTicker = new Map<string, ActionableTicker[]>()
  for (const t of tickers) {
    const rows = byTicker.get(t.ticker) ?? []
    rows.push(t)
    byTicker.set(t.ticker, rows)
  }

  return [...byTicker.entries()]
    .map(([ticker, rows]) => ({
      ticker,
      universes: [...new Set(rows.map((r) => r.universe_id))],
      best: rows.reduce((best, row) =>
        (row.final_score ?? -Infinity) > (best.final_score ?? -Infinity) ? row : best,
      ),
    }))
    .filter((row) => row.universes.length > 1)
    .sort((a, b) => (b.best.final_score ?? -Infinity) - (a.best.final_score ?? -Infinity))
}

export function OverlapMatrix() {
  const commandCenter = useQuery({
    queryKey: ['command-center'],
    queryFn: () => fetchCommandCenter(),
  })

  if (commandCenter.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }
  if (commandCenter.isError) {
    return (
      <p className="text-sm text-destructive">
        Failed to load command center: {(commandCenter.error as Error).message}
      </p>
    )
  }

  const tickers = commandCenter.data!.actionable_tickers.filter(
    (t) => t.strategy_id === STRATEGY_ID,
  )
  const overlaps = groupOverlaps(tickers)

  if (overlaps.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No ticker qualified as actionable in more than one universe today.
      </p>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Ticker</TableHead>
          <TableHead>Universes</TableHead>
          <TableHead>Best tier</TableHead>
          <TableHead>Best score</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {overlaps.map((row) => (
          <TableRow key={row.ticker}>
            <TableCell className="font-medium text-foreground">
              <Link to={`/ticker/${row.ticker}`} className="hover:underline">
                {row.ticker}
              </Link>
            </TableCell>
            <TableCell>
              <div className="flex flex-wrap gap-1">
                {row.universes.map((u) => (
                  <Badge key={u} variant="outline">
                    {u}
                  </Badge>
                ))}
              </div>
            </TableCell>
            <TableCell>
              <Badge variant={tierBadgeVariant(row.best.tier)}>{row.best.tier}</Badge>
            </TableCell>
            <TableCell className="tabular-nums">
              {row.best.final_score != null ? row.best.final_score.toFixed(1) : '—'}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
