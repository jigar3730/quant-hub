import { Check, X } from 'lucide-react'
import type { LynchCheck } from '@/lib/api'

// The authoritative pass/fail rule list (already phrased so passed=true
// always means "good" -- see lib/api.ts's LynchCheck doc comment). Shared
// between TickerFundamentalCard and UniverseTable's Lynch row drawer
// rather than duplicated -- one place to get this right.
export function LynchChecksList({ checks }: { checks: LynchCheck[] }) {
  if (checks.length === 0) return null
  return (
    <ul className="space-y-1.5">
      {checks.map((c) => (
        <li key={c.rule} className="flex items-start gap-2 text-sm" title={c.why_it_matters}>
          {c.passed ? (
            <Check className="mt-0.5 size-3.5 shrink-0 text-success" />
          ) : (
            <X className="mt-0.5 size-3.5 shrink-0 text-destructive" />
          )}
          <span className="text-foreground">{c.label}</span>
          <span className="text-muted-foreground">— {c.plain_value}</span>
        </li>
      ))}
    </ul>
  )
}
