import type { ScoreComponent, TickerDetail } from '@/lib/api'
import { humanizeKey } from '@/lib/utils'

// Mirrors `history/actionable.py::ACTIONABLE_TIERS` — the single source of
// truth for which tiers count as actionable. Lynch's real tier values are
// fast_grower/stalwart/asset_play/passed/filtered (lib/lynch.ts); "actionable"
// there is any non-filtered tier -- equivalent to the backend's own
// `tier != "filtered"` rule since those are the only 5 possible values.
const ACTIONABLE_TIERS: Record<string, Set<string>> = {
  launchpad: new Set(['Tier 1', 'Tier 2']),
  lynch: new Set(['fast_grower', 'stalwart', 'asset_play', 'passed']),
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

// Preferred ordering for the 5 known factors regardless of key order in
// the JSONB payload.
export const SCORE_ORDER = [
  'macd_zero_line',
  'squeeze_intensity',
  'tightness_percentile',
  'volume_vacuum_depth',
  'trend_proximity_match',
]

// MetricGrid generalization (docs/FINANCIAL_UI_REIMAGINED.md §1.4): a new
// factor added to `detail.scores` on the backend shows up here too, in a
// reasonable place, instead of being silently dropped because it isn't in
// SCORE_ORDER. Known keys keep their curated order; anything else is
// appended in the order the payload itself has (no arbitrary invented
// ordering for factors this frontend doesn't know about yet).
export function orderedScoreKeys(scores: Record<string, ScoreComponent> | undefined): string[] {
  if (!scores) return []
  const known = SCORE_ORDER.filter((key) => key in scores)
  const unknown = Object.keys(scores).filter((key) => !SCORE_ORDER.includes(key))
  return [...known, ...unknown]
}

export function scoreLabel(key: string): string {
  return SCORE_LABELS[key] ?? humanizeKey(key)
}

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

// Frontend-only presentational mapping (docs/FINANCIAL_UI_REIMAGINED.md
// §1.1) over scores the backend already computes — no new scoring concept,
// same category as tierBadgeVariant. Thresholds are a starting point to
// revisit once real score distributions have been reviewed.
const GRADE_THRESHOLDS: [number, string][] = [
  [90, 'A+'],
  [80, 'A'],
  [70, 'B+'],
  [60, 'B'],
  [50, 'C+'],
  [40, 'C'],
]

export function scoreGrade(pct: number | null | undefined): string {
  if (pct == null || Number.isNaN(pct)) return '—'
  for (const [min, grade] of GRADE_THRESHOLDS) {
    if (pct >= min) return grade
  }
  return 'D'
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
