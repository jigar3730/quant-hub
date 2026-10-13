import { fmtPrice, type LadderKind, type LadderLevel } from '@/lib/swing'
import { cn } from '@/lib/utils'

const BAR_CLASS: Record<LadderKind, string> = {
  target: 'bg-success',
  chase: 'bg-warning',
  entry: 'bg-foreground',
  average: 'bg-muted-foreground/40',
  stop: 'bg-destructive',
}

// Sorted price levels with a proportional bar and distance from the entry
// reference. A ladder rather than an overlaid chart: the API carries no
// candles, and levels a fraction of a percent apart (entry / chase / EMA10)
// would collide on a real price axis.
export function PriceLadder({ levels }: { levels: LadderLevel[] }) {
  if (levels.length === 0) return null
  const prices = levels.map((l) => l.price)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const span = max - min || 1
  const entry = levels.find((l) => l.kind === 'entry')?.price

  return (
    <ul className="space-y-1" aria-label="Price levels, highest first">
      {levels.map((level) => {
        const width = 6 + ((level.price - min) / span) * 94
        const distance = entry ? ((level.price - entry) / entry) * 100 : null
        return (
          <li key={level.label} className="grid grid-cols-[9.5rem_1fr_5.5rem] items-center gap-2 text-xs">
            <span
              className={cn(
                'truncate',
                level.kind === 'average' ? 'text-muted-foreground' : 'font-medium text-foreground',
              )}
            >
              {level.label}
            </span>
            <span className="h-2 rounded-full bg-muted" aria-hidden="true">
              <span
                className={cn('block h-2 rounded-full', BAR_CLASS[level.kind])}
                style={{ width: `${width}%` }}
              />
            </span>
            <span className="text-right tabular-nums text-foreground">
              {fmtPrice(level.price)}
              {distance != null && level.kind !== 'entry' && (
                <span className="ml-1 text-muted-foreground">
                  {distance >= 0 ? '+' : ''}
                  {distance.toFixed(1)}%
                </span>
              )}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
