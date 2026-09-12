import type { ScanSummary } from '@/lib/api'
import { cn } from '@/lib/utils'

// docs/FINANCIAL_UI_REIMAGINED.md §2.1 — zero new backend work. scan_summary
// has been fetched and typed since the report/regime work earlier this
// session; it just wasn't rendered anywhere yet. Plain div bars (same
// technique as FactorSparkbars), not a chart library, per the blueprint's
// own recommendation for this one view.
function humanizeReason(code: string): string {
  return code.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

// tier_counts/filter_breakdown are peer partitions of the universe, not a
// sequential narrowing chain -- every bar's width is relative to the same
// `universe_size` scale so they stay visually comparable to each other.
function FunnelBar({
  label,
  count,
  total,
  strong,
}: {
  label: string
  count: number
  total: number
  strong?: boolean
}) {
  const pct = total > 0 ? Math.min(100, (count / total) * 100) : 0
  return (
    <div className="flex items-center gap-3">
      <div className="w-36 shrink-0 truncate text-sm text-foreground">{label}</div>
      <div className="h-4 flex-1 overflow-hidden rounded-sm bg-muted">
        <div
          className={cn('h-full rounded-sm', strong ? 'bg-foreground/80' : 'bg-foreground/40')}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="w-12 shrink-0 text-right text-sm text-muted-foreground tabular-nums">
        {count}
      </div>
    </div>
  )
}

const TIER_ORDER = ['Tier 1', 'Tier 2', 'Tier 3']

export function ScanFunnel({ summary }: { summary: ScanSummary }) {
  const total = summary.universe_size
  const tierEntries = TIER_ORDER.filter((tier) => summary.tier_counts[tier] != null)
  const filterEntries = Object.entries(summary.filter_breakdown).sort((a, b) => b[1] - a[1])

  return (
    <div className="space-y-4 rounded-lg border border-border p-4">
      <div className="space-y-1.5">
        <FunnelBar label="Universe" count={summary.universe_size} total={total} strong />
        <FunnelBar label="Eligible" count={summary.eligible_count} total={total} strong />
      </div>

      {tierEntries.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            By tier
          </div>
          <div className="space-y-1.5">
            {tierEntries.map((tier) => (
              <FunnelBar key={tier} label={tier} count={summary.tier_counts[tier]} total={total} />
            ))}
          </div>
        </div>
      )}

      {filterEntries.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Filtered out ({summary.excluded_count})
          </div>
          <div className="space-y-1.5">
            {filterEntries.map(([reason, count]) => (
              <FunnelBar key={reason} label={humanizeReason(reason)} count={count} total={total} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
