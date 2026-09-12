// Mirrors `regime/market.py::regime_detail` — the only 3 labels the backend
// ever produces, each with a fixed score multiplier. Unknown/future labels
// fall back to a neutral "outline" treatment rather than guessing a color.
export const REGIME_META: Record<
  string,
  { variant: 'success' | 'warning' | 'destructive'; weight: string }
> = {
  strong: { variant: 'success', weight: 'Full score weight' },
  neutral: { variant: 'warning', weight: 'Scores discounted 15%' },
  weak: { variant: 'destructive', weight: 'Scores discounted 40%' },
}

export type RegimeVariant = 'success' | 'warning' | 'destructive' | 'outline'

export function regimeVariant(label: string | null | undefined): RegimeVariant {
  return (label && REGIME_META[label]?.variant) || 'outline'
}
