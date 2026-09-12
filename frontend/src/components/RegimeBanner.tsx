import { TrendingUp, Minus, TrendingDown } from 'lucide-react'
import type { ComponentType } from 'react'
import { Badge } from '@/components/ui/badge'
import type { MarketRegimeDetail } from '@/lib/api'
import { regimeVariant } from '@/lib/regime'
import { cn } from '@/lib/utils'

// Only label + multiplier are guaranteed everywhere the banner is used —
// /command-center's cross-universe payload has just those two; the full
// meaning/SPY detail only exists on a single scan run's /scans/{id}/report.
export type RegimeBannerData = Pick<MarketRegimeDetail, 'label' | 'multiplier'> &
  Partial<Omit<MarketRegimeDetail, 'label' | 'multiplier'>>

const TONE_CLASSES: Record<string, string> = {
  success: 'border-success/30 bg-success/10',
  warning: 'border-warning/30 bg-warning/10',
  destructive: 'border-destructive/30 bg-destructive/10',
  outline: 'border-border bg-muted/30',
}

const ICONS: Record<string, ComponentType<{ className?: string }>> = {
  strong: TrendingUp,
  neutral: Minus,
  weak: TrendingDown,
}

// A can't-miss regime indicator — the multiplier here rescales every score
// on the page (0.6x-1.0x), so this is read-this-first context, not a footnote.
export function RegimeBanner({ regime }: { regime: RegimeBannerData }) {
  const variant = regimeVariant(regime.label)
  const Icon = ICONS[regime.label] ?? Minus
  const hasDetail = regime.spy_price != null && regime.return_63d_pct != null

  return (
    <div className={cn('flex items-center gap-3 rounded-lg border px-3 py-2', TONE_CLASSES[variant])}>
      <Icon className="size-5 shrink-0 text-foreground" />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-foreground capitalize">
            {regime.label} regime
          </span>
          <Badge variant={variant}>{regime.multiplier.toFixed(2)}×</Badge>
          {hasDetail && (
            <span className="text-xs text-muted-foreground">
              SPY {regime.spy_price!.toFixed(2)} · {regime.return_63d_pct! >= 0 ? '+' : ''}
              {regime.return_63d_pct!.toFixed(1)}% (63d)
            </span>
          )}
        </div>
        {regime.meaning && (
          <p className="mt-0.5 text-xs text-muted-foreground">{regime.meaning}</p>
        )}
      </div>
    </div>
  )
}
