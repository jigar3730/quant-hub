import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { SwingTicker } from '@/lib/api'
import {
  fmtPrice,
  fmtSigned,
  SWING_RULES,
  SWING_TIER_LABEL,
  swingOutcomeLabel,
  swingTierTone,
} from '@/lib/swing'
import { SwingRuleChips } from './SwingRuleChips'

// Rank order; ETFs that never got a rank (no price data, bad data) sort last.
function byRank(a: SwingTicker, b: SwingTicker): number {
  const ra = a.summary.rs_rank ?? Number.POSITIVE_INFINITY
  const rb = b.summary.rs_rank ?? Number.POSITIVE_INFINITY
  return ra === rb ? a.ticker.localeCompare(b.ticker) : ra - rb
}

// Every ETF in the universe, ranked, with per-rule pass/fail so it is clear
// why a leader is not a signal yet and what knocked out each of the rest.
export function SwingLeadersTable({ tickers }: { tickers: SwingTicker[] }) {
  const rows = [...tickers].sort(byRank)

  return (
    <>
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-10">RS</TableHead>
          <TableHead>ETF</TableHead>
          <TableHead className="text-right" title="How many percentage points the ETF has beaten SPY by (average of the last 63 and 126 trading days)">
            RS score
          </TableHead>
          <TableHead className="text-right">63d %</TableHead>
          <TableHead className="text-right">126d %</TableHead>
          <TableHead title="Hover a chip for the value and threshold; legend below the table">
            Checks
          </TableHead>
          <TableHead title="Trend strength: 20 or more counts as a real trend">ADX</TableHead>
          <TableHead>Outcome</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((t) => (
          <TableRow key={t.ticker}>
            <TableCell className="tabular-nums text-muted-foreground">
              {t.summary.rs_rank ?? '—'}
            </TableCell>
            <TableCell className="font-medium text-foreground">{t.ticker}</TableCell>
            <TableCell className="text-right tabular-nums">{fmtSigned(t.summary.rs_score_pct)}</TableCell>
            <TableCell className="text-right tabular-nums">{fmtSigned(t.summary.ret_63d_pct)}</TableCell>
            <TableCell className="text-right tabular-nums">{fmtSigned(t.summary.ret_126d_pct)}</TableCell>
            <TableCell>
              <SwingRuleChips ticker={t} />
            </TableCell>
            <TableCell className="tabular-nums text-muted-foreground">
              {t.indicators ? fmtPrice(t.indicators.adx14) : '—'}
            </TableCell>
            <TableCell>
              <div className="flex items-center gap-2">
                <Badge variant={swingTierTone(t.tier)}>{SWING_TIER_LABEL[t.tier] ?? t.tier}</Badge>
                {t.tier === 'filtered' || t.regime_blocked ? (
                  <span className="text-xs text-muted-foreground">{swingOutcomeLabel(t)}</span>
                ) : null}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
    <div className="mt-3 rounded-md bg-muted/40 p-3 text-xs text-muted-foreground">
      <p className="mb-1.5 font-medium text-foreground">
        Reading the chips — green passed, red failed, grey not checked (an earlier check failed)
      </p>
      <ul className="grid gap-x-6 gap-y-0.5 sm:grid-cols-2">
        {SWING_RULES.map((rule) => (
          <li key={rule.id}>
            <span className="font-medium text-foreground">
              {rule.short} {rule.label}:
            </span>{' '}
            {rule.plain}
          </li>
        ))}
      </ul>
      <p className="mt-1.5">
        RS score = how many percentage points the ETF has beaten SPY by (63- and 126-day average).
        ADX = trend strength; 20 or more counts as a real trend.
      </p>
    </div>
    </>
  )
}
