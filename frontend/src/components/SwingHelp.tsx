import { CircleHelp } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { SWING_GLOSSARY, SWING_RULES, SWING_TIER_HELP, swingTierTone } from '@/lib/swing'

const SEEN_KEY = 'quant-hub.swing.help-seen'

// localStorage can throw (private windows, blocked storage) -- never rely on it.
function hasSeenHelp(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === '1'
  } catch {
    return false
  }
}

function markSeen(): void {
  try {
    window.localStorage.setItem(SEEN_KEY, '1')
  } catch {
    /* storage unavailable: the panel just opens again next visit */
  }
}

const STEPS = [
  {
    title: 'Check the headline',
    body: 'The coloured card at the top says in one sentence what today means: trade plans ready, something to watch, or nothing to do. "Nothing to do" is a normal, frequent answer.',
  },
  {
    title: 'Check the market gate',
    body: 'The green or red bar shows whether SPY (the S&P 500) is healthy. If it is red, no trade plans are issued at all, whatever the individual ETFs look like.',
  },
  {
    title: 'Read a trade plan (only if there is one)',
    body: 'Each card lists an entry price, a stop (where you would exit if wrong), a target, and a share count sized to your own risk budget. Read the "In plain English" line first, then follow the before-the-open checklist.',
  },
  {
    title: 'Use the ranked table to see why not',
    body: 'Every ETF is listed best to worst against SPY. The coloured chips show which of the 7 checks it passed (green) or failed (red); grey means an earlier check already rejected it.',
  },
]

export function SwingHelp() {
  const [open, setOpen] = useState<boolean>(() => !hasSeenHelp())

  function toggle() {
    setOpen((v) => !v)
    markSeen()
  }

  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium text-foreground hover:bg-muted/50"
      >
        <CircleHelp className="size-4 shrink-0 text-muted-foreground" />
        How to read this page
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          {open ? 'Hide' : 'Show'}
        </span>
      </button>

      {open && (
        <div className="space-y-6 border-t border-border p-4 text-sm">
          <p className="text-muted-foreground">
            This scanner looks for <span className="text-foreground">short swing trades (about 3–10 trading days)</span> in
            sector ETFs: funds that are already beating the market, have dipped, and are turning
            back up. Every plan comes with a stop set <em>before</em> you enter. It runs before the
            market opens each weekday, so all prices come from the previous close.
          </p>

          <section>
            <h3 className="font-semibold text-foreground">Four steps</h3>
            <ol className="mt-2 space-y-2">
              {STEPS.map((step, i) => (
                <li key={step.title} className="flex gap-3">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium text-secondary-foreground">
                    {i + 1}
                  </span>
                  <span>
                    <span className="font-medium text-foreground">{step.title}. </span>
                    <span className="text-muted-foreground">{step.body}</span>
                  </span>
                </li>
              ))}
            </ol>
          </section>

          <section>
            <h3 className="font-semibold text-foreground">What the labels mean</h3>
            <ul className="mt-2 space-y-2">
              {SWING_TIER_HELP.map((t) => (
                <li key={t.tier} className="flex items-start gap-3">
                  <Badge variant={swingTierTone(t.tier)} className="mt-0.5 w-20">
                    {t.name}
                  </Badge>
                  <span className="text-muted-foreground">{t.meaning}</span>
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h3 className="font-semibold text-foreground">The 7 checks (chips R1–R7)</h3>
            <p className="mt-1 text-muted-foreground">
              An ETF must pass them in order. The first failure decides the outcome and the rest
              turn grey.
            </p>
            <dl className="mt-2 grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
              {SWING_RULES.map((rule) => (
                <div key={rule.id} className="flex gap-2">
                  <dt className="w-16 shrink-0 font-medium text-foreground">
                    {rule.short} {rule.label}
                  </dt>
                  <dd className="text-muted-foreground">{rule.plain}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section>
            <h3 className="font-semibold text-foreground">Glossary</h3>
            <dl className="mt-2 space-y-2">
              {SWING_GLOSSARY.map((g) => (
                <div key={g.term}>
                  <dt className="font-medium text-foreground">{g.term}</dt>
                  <dd className="text-muted-foreground">{g.meaning}</dd>
                </div>
              ))}
            </dl>
          </section>

          <p className="border-t border-border pt-3 text-xs text-muted-foreground">
            Research tool only — not investment advice and not a trading bot. Nothing here places
            orders or promises a return; a plan is a set of levels to check against a live quote, and
            any trade can lose up to (and sometimes more than) the amount planned.
          </p>
        </div>
      )}
    </div>
  )
}
