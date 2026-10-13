import { Check, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { SwingTicker } from '@/lib/api'
import {
  checkSummary,
  fmtMoney,
  fmtPrice,
  fmtSigned,
  ladderLevels,
  MAX_HOLD_DAYS,
  planSentence,
  sizePosition,
} from '@/lib/swing'
import { PriceLadder } from './PriceLadder'

function Figure({
  label,
  value,
  hint,
  caption,
}: {
  label: string
  value: string
  hint?: string
  caption: string
}) {
  return (
    <div>
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="text-sm font-semibold tabular-nums text-foreground">
        {value}
        {hint && <span className="ml-1 text-xs font-normal text-muted-foreground">{hint}</span>}
      </dd>
      <dd className="text-[11px] leading-tight text-muted-foreground">{caption}</dd>
    </div>
  )
}

// One trade plan. Levels are the stored per-share values; the share count is
// recomputed from the viewer's equity / risk so it never shows someone else's
// (placeholder) account size.
export function SwingPlanCard({
  ticker,
  equity,
  riskPct,
}: {
  ticker: SwingTicker
  equity: number
  riskPct: number
}) {
  const plan = ticker.trade_plan
  if (!plan) return null
  const size = sizePosition(equity, riskPct, plan.entry_ref, plan.risk_per_share)

  return (
    <article className="rounded-lg border border-border p-4">
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-semibold text-foreground">{ticker.ticker}</h3>
        <Badge variant="success">Trigger</Badge>
        {ticker.summary.rs_rank != null && (
          <span className="text-xs text-muted-foreground">
            RS #{ticker.summary.rs_rank} · {fmtSigned(ticker.summary.rs_score_pct)} pp vs SPY
          </span>
        )}
      </header>

      <p className="mt-3 rounded-md bg-muted/50 px-3 py-2 text-sm text-foreground">
        <span className="font-medium">In plain English: </span>
        {planSentence(ticker.ticker, plan, size)}
      </p>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <Figure
          label="Entry ref"
          value={fmtPrice(plan.entry_ref)}
          caption="Yesterday's close, where the setup was measured"
        />
        <Figure
          label="Stop"
          value={fmtPrice(plan.stop)}
          hint={`${plan.stop_atr_multiple.toFixed(1)}× daily move`}
          caption="Exit here if wrong; this caps your loss"
        />
        <Figure
          label="2R target"
          value={fmtPrice(plan.target_2r)}
          caption="Gain of twice what you risk"
        />
        <Figure
          label="Chase limit"
          value={fmtPrice(plan.chase_limit)}
          caption="Skip the trade if it opens above this"
        />
        <Figure
          label="Shares"
          value={size.shares.toLocaleString('en-US')}
          caption="What fits your risk budget"
        />
        <Figure
          label="Money at risk"
          value={fmtMoney(size.riskDollars)}
          hint={`${riskPct}%`}
          caption="Lost if the stop is hit"
        />
        <Figure
          label="Position size"
          value={fmtMoney(size.positionDollars)}
          caption="Total spent on the shares"
        />
        <Figure
          label="Risk per share"
          value={fmtPrice(plan.risk_per_share)}
          caption="Entry minus stop (1R)"
        />
      </dl>

      {size.shares === 0 && (
        <p className="mt-2 text-xs text-warning-foreground">
          Zero shares at this equity and risk — the stop distance is too large for the budget.
        </p>
      )}
      {size.capBound && size.shares > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          Sized by the 30% max-position cap, not the risk budget.
        </p>
      )}

      <div className="mt-4">
        <p className="mb-1 text-xs font-medium text-muted-foreground">
          Price levels, highest first (green = target, red = stop, grey = moving averages)
        </p>
        <PriceLadder levels={ladderLevels(ticker)} />
      </div>

      <details open className="mt-3 rounded-md border border-border px-3 py-2">
        <summary className="cursor-pointer text-xs font-medium text-foreground">
          What to do with this plan
        </summary>
        <div className="mt-2 space-y-2 text-xs text-muted-foreground">
          <div>
            <p className="font-medium text-foreground">Before the open</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              <li>
                Look at the opening price. Skip the trade if it is above {fmtPrice(plan.chase_limit)}{' '}
                (too far from the plan) or at/below {fmtPrice(plan.stop)} (the idea is already wrong).
              </li>
              <li>
                These levels use yesterday's adjusted closing prices. Confirm them against a live
                quote before acting.
              </li>
              <li>Decide your exit first: the stop at {fmtPrice(plan.stop)}.</li>
            </ul>
          </div>
          <div>
            <p className="font-medium text-foreground">After entering</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              <li>Sell half at the target ({fmtPrice(plan.target_2r)}).</li>
              <li>
                Trail the rest: exit on a daily close below the 10-day average
                {ticker.indicators ? ` (now ${fmtPrice(ticker.indicators.ema10)})` : ''}.
              </li>
              <li>
                Time stop: if it has not gained 1× the risk within {MAX_HOLD_DAYS} trading days, exit
                at the close.
              </li>
            </ul>
          </div>
        </div>
      </details>

      <details className="mt-3">
        <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
          Why it qualifies ({ticker.eligibility.checks.length} checks passed)
        </summary>
        <ul className="mt-2 space-y-1">
          {ticker.eligibility.checks.map((check) => (
            <li key={check.rule} className="flex items-start gap-2 text-xs text-foreground">
              {check.passed ? (
                <Check className="mt-0.5 size-3.5 shrink-0 text-success" />
              ) : (
                <X className="mt-0.5 size-3.5 shrink-0 text-destructive" />
              )}
              <span>{checkSummary(check.rule, check)}</span>
            </li>
          ))}
        </ul>
      </details>
    </article>
  )
}
