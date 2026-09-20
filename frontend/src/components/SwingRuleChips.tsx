import type { SwingTicker } from '@/lib/api'
import { checkSummary, SWING_RULES } from '@/lib/swing'
import { cn } from '@/lib/utils'

// One chip per rule so it is obvious why a leader is not a signal yet: green
// passed, red failed, grey not evaluated (rules stop at the first failure).
export function SwingRuleChips({ ticker }: { ticker: SwingTicker }) {
  return (
    <div className="flex gap-1">
      {SWING_RULES.map((rule) => {
        const check = ticker.eligibility.checks.find((c) => c.rule === rule.id)
        const state = check ? (check.passed ? 'pass' : 'fail') : 'skipped'
        return (
          <span
            key={rule.id}
            title={checkSummary(rule.label, check)}
            className={cn(
              'inline-flex h-5 w-7 items-center justify-center rounded text-[10px] font-medium',
              state === 'pass' && 'bg-success/15 text-success',
              state === 'fail' && 'bg-destructive/15 text-destructive',
              state === 'skipped' && 'bg-muted text-muted-foreground',
            )}
          >
            {rule.short}
            <span className="sr-only">: {state}</span>
          </span>
        )
      })}
    </div>
  )
}
