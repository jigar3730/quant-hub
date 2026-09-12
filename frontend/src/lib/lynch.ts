// Mirrors `lynch/categories.py::assign_categories` — only 3 category
// values are ever assigned (this codebase implements half of Lynch's real
// 6-category taxonomy: no slow_grower/cyclical/turnaround). `categories`
// is a non-exclusive set; `tier` is a different axis (categories[0], or
// "passed"/"filtered" as a fallback) — see lynch/runner.py:154.
export const LYNCH_CATEGORY_LABELS: Record<string, string> = {
  fast_grower: 'Fast Grower',
  stalwart: 'Stalwart',
  asset_play: 'Asset Play',
}

// Mirrors the old dashboard's own convention (dashboard/viz/design_tokens.py)
// for recognizability, mapped onto this app's badge variants.
export const LYNCH_CATEGORY_VARIANT: Record<string, 'success' | 'default' | 'secondary'> = {
  fast_grower: 'success',
  stalwart: 'default',
  asset_play: 'secondary',
}

export function lynchTierVariant(
  tier: string | null | undefined,
): 'success' | 'default' | 'secondary' | 'outline' {
  if (!tier) return 'outline'
  return LYNCH_CATEGORY_VARIANT[tier] ?? 'outline'
}

export function lynchTierLabel(tier: string | null | undefined): string {
  if (!tier) return '—'
  return LYNCH_CATEGORY_LABELS[tier] ?? tier
}
