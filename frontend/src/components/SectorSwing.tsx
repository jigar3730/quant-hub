import { useQuery } from '@tanstack/react-query'
import { TrendingDown, TrendingUp, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { fetchSwingScan, isNotFoundError, type SwingScanReport, type SwingTicker } from '@/lib/api'
import {
  daysSince,
  DEFAULT_EQUITY,
  DEFAULT_RISK_PCT,
  fmtPrice,
  loadSizing,
  saveSizing,
  SWING_REASON_LABEL,
  swingHeadline,
  type SizingInputs,
} from '@/lib/swing'
import { cn } from '@/lib/utils'
import { SwingHelp } from './SwingHelp'
import { SwingLeadersTable } from './SwingLeadersTable'
import { SwingPlanCard } from './SwingPlanCard'

// Beyond a long weekend plus a holiday, an as-of date this old is worth a nudge
// even if the scanner itself did not flag it.
const STALE_AFTER_DAYS = 4

function StatusBanner({ report }: { report: SwingScanReport }) {
  const r = report.market_regime
  const passed = r.regime_gate_passed
  const Icon = passed ? TrendingUp : TrendingDown
  const age = daysSince(r.as_of_price)
  const freshnessIssue = r.data_freshness !== 'fresh' && r.data_freshness !== 'refreshed'

  return (
    <div className="space-y-2">
      <div
        className={cn(
          'flex items-start gap-3 rounded-lg border px-3 py-2',
          passed ? 'border-success/30 bg-success/10' : 'border-destructive/30 bg-destructive/10',
        )}
      >
        <Icon className="mt-0.5 size-5 shrink-0 text-foreground" />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-foreground">
              {passed ? 'Regime gate passed' : 'Regime gate off — no new trade plans'}
            </span>
            <Badge variant={passed ? 'success' : 'destructive'}>{passed ? 'PASS' : 'FAIL'}</Badge>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            SPY {fmtPrice(r.spy_price)} vs SMA50 {fmtPrice(r.sma50)} and SMA200 {fmtPrice(r.sma200)}
            {' · '}
            {r.gate_rule}
          </p>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Prices as of <span className="font-medium text-foreground">{r.as_of_price}</span> · scan{' '}
        {report.scan_date} · data {r.data_freshness.replace('_', ' ')}
      </p>
      {(freshnessIssue || age > STALE_AFTER_DAYS) && (
        <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-foreground">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <span>
            {freshnessIssue
              ? `This scan ran with ${r.data_freshness.replace('_', ' ')} price data.`
              : `Price data is ${age} days old.`}{' '}
            Do not treat these levels as current.
          </span>
        </div>
      )}
    </div>
  )
}

const HEADLINE_TONE = {
  success: 'border-success/40 bg-success/10',
  warning: 'border-warning/40 bg-warning/10',
  destructive: 'border-destructive/40 bg-destructive/10',
  neutral: 'border-border bg-muted/40',
} as const

// The one-sentence answer to "what does today's scan mean?".
function Headline({ tickers, gatePassed }: { tickers: SwingTicker[]; gatePassed: boolean }) {
  const h = swingHeadline(tickers, gatePassed)
  return (
    <div className={cn('rounded-lg border px-4 py-3', HEADLINE_TONE[h.tone])}>
      <p className="text-base font-semibold text-foreground">{h.title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{h.detail}</p>
    </div>
  )
}

function SizingPanel({
  inputs,
  onChange,
  invalid,
}: {
  inputs: SizingInputs
  onChange: (next: SizingInputs) => void
  invalid: boolean
}) {
  return (
    <div className="flex flex-wrap items-end gap-4 rounded-lg border border-border p-3">
      <label className="text-xs font-medium text-muted-foreground">
        Account equity ($)
        <Input
          className="mt-1 w-36"
          inputMode="decimal"
          value={inputs.equity}
          onChange={(e) => onChange({ ...inputs, equity: e.target.value })}
        />
      </label>
      <label className="text-xs font-medium text-muted-foreground">
        Risk per trade (%)
        <Input
          className="mt-1 w-24"
          inputMode="decimal"
          value={inputs.riskPct}
          onChange={(e) => onChange({ ...inputs, riskPct: e.target.value })}
        />
      </label>
      <p className="min-w-48 flex-1 text-xs text-muted-foreground">
        {invalid
          ? `Enter positive numbers — showing zero shares until then (defaults are $${DEFAULT_EQUITY.toLocaleString('en-US')} / ${DEFAULT_RISK_PCT}%).`
          : `Placeholders until you set your own; stored in this browser only. Shares come from the plan's per-share risk, capped at 30% of equity per position.`}
      </p>
    </div>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold text-foreground">{title}</h2>
      {hint && <p className="mt-0.5 text-sm text-muted-foreground">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  )
}

export function SectorSwing() {
  const scan = useQuery({ queryKey: ['swing', 'latest'], queryFn: fetchSwingScan })
  const [sizing, setSizing] = useState<SizingInputs>(loadSizing)
  useEffect(() => saveSizing(sizing), [sizing])

  if (scan.isLoading) return <p className="text-sm text-muted-foreground">Loading sector swing scan…</p>
  if (scan.isError) {
    if (isNotFoundError(scan.error)) {
      return (
        <p className="text-sm text-muted-foreground">
          No sector swing scan yet. It runs weekdays at 5:20 AM ET, or run{' '}
          <code className="rounded bg-muted px-1">quant-sector-swing --force-refresh</code>.
        </p>
      )
    }
    return (
      <p className="text-sm text-destructive">
        Failed to load the sector swing scan: {(scan.error as Error).message}
      </p>
    )
  }

  const { report } = scan.data!
  const equity = Number(sizing.equity.replace(/,/g, ''))
  const riskPct = Number(sizing.riskPct)
  const invalid = !(equity > 0) || !(riskPct > 0)

  const inTier = (tier: string): SwingTicker[] =>
    report.tickers
      .filter((t) => t.tier === tier)
      .sort((a, b) => (a.summary.rs_rank ?? 99) - (b.summary.rs_rank ?? 99))
  const plans = inTier('Tier 1').filter((t) => t.trade_plan)
  const watch = inTier('Tier 2')
  const breakdown = Object.entries(report.scan_summary.filter_breakdown ?? {})

  return (
    <div className="space-y-4">
      <SwingHelp />
      <Headline tickers={report.tickers} gatePassed={report.market_regime.regime_gate_passed} />
      <StatusBanner report={report} />

      <Section
        title="Trade plans"
        hint="Long swing setups: leader vs SPY, pullback turning up, defined stop."
      >
        <SizingPanel inputs={sizing} onChange={setSizing} invalid={invalid} />
        {plans.length === 0 ? (
          <p className="mt-4 text-sm text-muted-foreground">
            No trigger setups today
            {report.market_regime.regime_gate_passed ? '' : ' — the regime gate is off'}. Leaders that
            are close appear in the watchlist below; the table shows what stopped each ETF.
          </p>
        ) : (
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {plans.map((t) => (
              <SwingPlanCard key={t.ticker} ticker={t} equity={equity} riskPct={riskPct} />
            ))}
          </div>
        )}
      </Section>

      <Section title="Watchlist" hint="Leaders in a trend with a pullback in progress but no trigger yet.">
        {watch.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing on the watchlist.</p>
        ) : (
          <ul className="space-y-2">
            {watch.map((t) => (
              <li key={t.ticker} className="rounded-lg border border-border px-3 py-2 text-sm">
                <span className="font-medium text-foreground">{t.ticker}</span>
                <span className="ml-2 text-xs text-muted-foreground">
                  RS #{t.summary.rs_rank} · {t.eligibility.summary}
                </span>
                {t.regime_blocked && t.trade_plan && (
                  <span className="mt-1 block text-xs text-muted-foreground">
                    Informational only — entry {fmtPrice(t.trade_plan.entry_ref)}, stop{' '}
                    {fmtPrice(t.trade_plan.stop)}, 2R {fmtPrice(t.trade_plan.target_2r)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="All ETFs, ranked"
        hint="Relative strength vs SPY with per-rule results. Grey chips were not evaluated because an earlier rule failed."
      >
        <SwingLeadersTable tickers={report.tickers} />
        {breakdown.length > 0 && (
          <p className="mt-3 text-xs text-muted-foreground">
            Filtered:{' '}
            {breakdown.map(([reason, n]) => `${SWING_REASON_LABEL[reason] ?? reason} ${n}`).join(' · ')}
          </p>
        )}
      </Section>

      <p className="mt-10 border-t border-border pt-4 text-xs text-muted-foreground">
        Research tool only — not investment advice and not a trading bot. No orders are placed, and
        nothing here is a return target. Plans are computed from Yahoo daily bars.
      </p>
    </div>
  )
}
