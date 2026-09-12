import type { TickerDetail } from '@/lib/api'

// Mirrors `history/actionable.py::ACTIONABLE_TIERS` — the single source of
// truth for which tiers count as actionable. Launchpad is the only strategy
// wired into the frontend so far.
const ACTIONABLE_TIERS: Record<string, Set<string>> = {
  launchpad: new Set(['Tier 1', 'Tier 2']),
}

export function isActionable(strategyId: string, ticker: TickerDetail): boolean {
  if (!ticker.eligible) return false
  const tiers = ACTIONABLE_TIERS[strategyId]
  return tiers ? tiers.has(ticker.tier) : false
}

// Display labels for `detail.scores` keys (report/launchpad_diagnostics.py).
export const SCORE_LABELS: Record<string, string> = {
  macd_zero_line: 'MACD Zero Line',
  squeeze_intensity: 'Squeeze Intensity',
  tightness_percentile: 'Tightness Percentile',
  volume_vacuum_depth: 'Volume Vacuum Depth',
  trend_proximity_match: 'Trend / Proximity',
}

// Fixed, stable ordering for the score breakdown regardless of key order
// in the JSONB payload.
export const SCORE_ORDER = [
  'macd_zero_line',
  'squeeze_intensity',
  'tightness_percentile',
  'volume_vacuum_depth',
  'trend_proximity_match',
]

export function finalScore(ticker: TickerDetail): number | null {
  return ticker.summary?.final_adjusted_score ?? null
}

export function filterReason(ticker: TickerDetail): string | null {
  return ticker.eligibility?.summary ?? ticker.eligibility?.fail_reason ?? null
}

export function tierBadgeVariant(
  tier: string | null | undefined,
): 'default' | 'secondary' | 'outline' {
  if (tier === 'Tier 1') return 'default'
  if (tier === 'Tier 2') return 'secondary'
  return 'outline'
}

// Heatmap cell fill for the ticker audit-trail — the one place a green
// intensity scale earns its keep (a pass-rate heatmap is conventionally
// read that way), distinct from the tier badge's neutral monochrome scale.
export function tierHeatClass(tier: string | null | undefined): string {
  if (tier === 'Tier 1') return 'bg-success'
  if (tier === 'Tier 2') return 'bg-success/50'
  if (tier === 'Tier 3') return 'bg-muted-foreground/30'
  return 'bg-muted'
}
