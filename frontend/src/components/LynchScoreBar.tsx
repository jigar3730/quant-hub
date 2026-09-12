import { cn } from '@/lib/utils'

// lynch_score is already a single 0-100 percentage (passed_checks/total*100)
// -- render it as one gauge, not decomposed into per-factor bars the way
// Launchpad's FactorSparkbars does, since there's no per-factor {score,max}
// to decompose (docs/FINANCIAL_UI_REIMAGINED.md §1.1). Shared between
// TickerFundamentalCard and UniverseTable's Lynch row/drawer.
export function LynchScoreBar({
  score,
  barClassName = 'h-1.5 w-16',
}: {
  score: number | null | undefined
  barClassName?: string
}) {
  const pct = Math.max(0, Math.min(100, score ?? 0))
  return (
    <div className="flex items-center gap-2">
      <div className={cn('overflow-hidden rounded-full bg-muted', barClassName)}>
        <div className="h-full rounded-full bg-foreground/70" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted-foreground tabular-nums">
        {score != null ? score.toFixed(0) : '—'}
      </span>
    </div>
  )
}
