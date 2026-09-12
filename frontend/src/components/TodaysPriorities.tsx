import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { RegimeBanner } from '@/components/RegimeBanner'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { fetchCommandCenter } from '@/lib/api'
import { tierBadgeVariant } from '@/lib/scoring'

const STRATEGY_ID = 'launchpad'

// The cross-universe, ranked "what to look at today" home view. Unlike
// UniverseTable (one universe, everything in it, drill-down detail), this
// is meant for a fast morning scan: every actionable setup across all 8
// universes, ranked, no clicking required to see what matters.
export function TodaysPriorities() {
  const commandCenter = useQuery({
    queryKey: ['command-center'],
    queryFn: () => fetchCommandCenter(),
  })

  if (commandCenter.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading today's priorities…</p>
  }
  if (commandCenter.isError) {
    return (
      <p className="text-sm text-destructive">
        Failed to load command center: {(commandCenter.error as Error).message}
      </p>
    )
  }

  const data = commandCenter.data!
  const launchpad = data.per_strategy[STRATEGY_ID]
  const tickers = data.actionable_tickers.filter((t) => t.strategy_id === STRATEGY_ID)

  if (data.run_count === 0) {
    return <p className="text-sm text-muted-foreground">No scans have run yet today.</p>
  }

  return (
    <div>
      {data.regime_label && data.regime_multiplier != null && (
        <div className="mb-4">
          <RegimeBanner regime={{ label: data.regime_label, multiplier: data.regime_multiplier }} />
        </div>
      )}

      {launchpad && (
        <div className="mb-4 flex flex-wrap gap-6 text-sm">
          <div>
            <span className="text-2xl font-semibold text-foreground tabular-nums">
              {launchpad.universes}
            </span>
            <span className="ml-1.5 text-muted-foreground">universes scanned</span>
          </div>
          <div>
            <span className="text-2xl font-semibold text-foreground tabular-nums">
              {launchpad.actionable}
            </span>
            <span className="ml-1.5 text-muted-foreground">actionable setups</span>
          </div>
          <div>
            <span className="text-2xl font-semibold text-foreground tabular-nums">
              {launchpad.tier1}
            </span>
            <span className="ml-1.5 text-muted-foreground">Tier 1</span>
          </div>
        </div>
      )}

      {tickers.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No actionable setups across any universe today.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ticker</TableHead>
              <TableHead>Tier</TableHead>
              <TableHead>Score</TableHead>
              <TableHead>Universe</TableHead>
              <TableHead>Sector</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tickers.map((t) => (
              <TableRow key={`${t.universe_id}-${t.ticker}`}>
                <TableCell className="font-medium text-foreground">
                  <Link to={`/ticker/${t.ticker}`} className="hover:underline">
                    {t.ticker}
                  </Link>
                </TableCell>
                <TableCell>
                  <Badge variant={tierBadgeVariant(t.tier)}>{t.tier}</Badge>
                </TableCell>
                <TableCell className="tabular-nums">
                  {t.final_score != null ? t.final_score.toFixed(1) : '—'}
                </TableCell>
                <TableCell className="text-muted-foreground">{t.universe_id}</TableCell>
                <TableCell className="text-muted-foreground">{t.sector_etf ?? '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
