import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { fetchOutcomesForTicker } from '@/lib/api'

const STRATEGY_ID = 'launchpad'

function pct(value: number | null): string {
  if (value == null) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`
}

// docs/FINANCIAL_UI_REIMAGINED.md §1.2 (ML Outcomes card), corrected during
// build: the real distinction in signal_outcomes.label_status isn't
// "pending vs finalized" (ml/constants.py has no "pending" value — every
// inserted row already has "ok"/"no_price"/"insufficient_future_bars"/
// "invalid_anchor"). The actual "still waiting" case is simply no row
// existing yet for that run/horizon, which this renders as its own empty
// state rather than a fabricated "pending" status.
export function TickerOutcomesCard({ ticker }: { ticker: string }) {
  const outcomes = useQuery({
    queryKey: ['outcomes', ticker, STRATEGY_ID],
    queryFn: () => fetchOutcomesForTicker(ticker, { strategyId: STRATEGY_ID }),
  })

  if (outcomes.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading ML outcomes…</p>
  }
  if (outcomes.isError) {
    return (
      <p className="text-sm text-destructive">
        Failed to load outcomes: {(outcomes.error as Error).message}
      </p>
    )
  }
  if (outcomes.data!.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No ML outcomes computed yet for {ticker} — labeling runs once each
        signal's forward-return horizon has elapsed.
      </p>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Scan date</TableHead>
          <TableHead>Universe</TableHead>
          <TableHead>Horizon</TableHead>
          <TableHead>Forward return</TableHead>
          <TableHead>Excess vs SPY</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {outcomes.data!.map((row) => (
          <TableRow key={`${row.run_id}-${row.horizon_days}`}>
            <TableCell>{row.scan_date ?? '—'}</TableCell>
            <TableCell className="text-muted-foreground">{row.universe_id ?? '—'}</TableCell>
            <TableCell>{row.horizon_days}d</TableCell>
            <TableCell className="tabular-nums">
              {row.label_status === 'ok' ? pct(row.forward_return_pct) : '—'}
            </TableCell>
            <TableCell className="tabular-nums">
              {row.label_status === 'ok' ? pct(row.excess_return_pct) : '—'}
            </TableCell>
            <TableCell>
              {row.label_status === 'ok' ? (
                <Badge variant="success">ok</Badge>
              ) : (
                <Badge variant="outline">{row.label_status}</Badge>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
