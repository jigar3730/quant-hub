// Presentation helpers for the sector-ETF swing page. Rule ids, reasons and
// the position cap mirror src/quant_hub/sector_swing/config.py.
import type { EligibilityCheck, SwingTicker } from './api'

// Mirrors SwingParams.max_position_pct -- not carried in the payload.
export const MAX_POSITION_PCT = 0.3

// Placeholders, shown as such; the user's real values are stored locally.
export const DEFAULT_EQUITY = 50_000
export const DEFAULT_RISK_PCT = 1

export type BadgeTone = 'success' | 'warning' | 'destructive' | 'secondary' | 'outline'

export const SWING_RULES = [
  {
    id: 'R1_regime',
    short: 'R1',
    label: 'Market gate',
    plain: 'Is the overall market healthy? (SPY above its 50- and 200-day averages)',
  },
  {
    id: 'R2_leadership',
    short: 'R2',
    label: 'Leader',
    plain: 'Is this ETF beating SPY, and among the top 4 that do?',
  },
  {
    id: 'R3_trend',
    short: 'R3',
    label: 'Uptrend',
    plain: 'Is it in a real uptrend? (above its 50-day average, with trend strength ADX of 20+)',
  },
  {
    id: 'R4_pullback',
    short: 'R4',
    label: 'Pullback',
    plain: 'Has it dipped back to its 20-day average recently? (a "buy the dip" entry, not a chase)',
  },
  {
    id: 'R5_trigger',
    short: 'R5',
    label: 'Turning up',
    plain: "Did it just close above yesterday's high and its 10-day average? (the dip is reversing)",
  },
  {
    id: 'R6_stop',
    short: 'R6',
    label: 'Stop distance',
    plain: 'Can it be protected with a stop that is not too far away? (within 2.5× its typical daily move)',
  },
  {
    id: 'R7_sizing',
    short: 'R7',
    label: 'Size',
    plain: 'Does that stop leave room for at least 1 share within your risk budget?',
  },
] as const

export const SWING_TIER_LABEL: Record<string, string> = {
  'Tier 1': 'Trigger',
  'Tier 2': 'Watch',
  'Tier 3': 'Extended',
  filtered: 'Filtered',
}

export function swingTierTone(tier: string): BadgeTone {
  if (tier === 'Tier 1') return 'success'
  if (tier === 'Tier 2') return 'warning'
  if (tier === 'Tier 3') return 'secondary'
  return 'outline'
}

export const SWING_REASON_LABEL: Record<string, string> = {
  no_price_data: 'No price data',
  insufficient_history: 'Not enough history',
  data_quality: 'Data-quality failure',
  illiquid: 'Illiquid',
  not_leader: 'Not a leader',
  trend_fail: 'Trend filter failed',
  stop_too_wide: 'Stop too wide',
  correlated: 'Correlated with a higher-ranked plan',
  size_zero: 'Zero shares at this risk',
  signal_cap: 'Signal cap reached',
  already_open: 'Already holding this ETF',
  position_limit: 'Open-position limit reached',
  compute_error: 'Computation error',
}

export function swingOutcomeLabel(t: SwingTicker): string {
  if (t.tier === 'filtered') {
    const reason = t.eligibility.fail_reason
    return (reason && SWING_REASON_LABEL[reason]) || reason || 'Filtered'
  }
  if (t.regime_blocked) return 'Watch — regime gate off'
  return SWING_TIER_LABEL[t.tier] ?? t.tier
}

export interface PositionSize {
  shares: number
  riskDollars: number
  positionDollars: number
  // True when the max-position cap, not the risk budget, set the share count.
  capBound: boolean
}

// Same rule as sector_swing/sizing.py::position_size:
// floor(min(equity * risk / R, equity * cap / entry)).
export function sizePosition(
  equity: number,
  riskPct: number,
  entry: number,
  riskPerShare: number,
): PositionSize {
  if (!(equity > 0) || !(entry > 0) || !(riskPerShare > 0) || !(riskPct > 0)) {
    return { shares: 0, riskDollars: 0, positionDollars: 0, capBound: false }
  }
  const riskLimited = (equity * (riskPct / 100)) / riskPerShare
  const capLimited = (equity * MAX_POSITION_PCT) / entry
  const shares = Math.max(0, Math.floor(Math.min(riskLimited, capLimited) + 1e-9))
  return {
    shares,
    riskDollars: shares * riskPerShare,
    positionDollars: shares * entry,
    capBound: capLimited < riskLimited,
  }
}

export type LadderKind = 'target' | 'chase' | 'entry' | 'average' | 'stop'

export interface LadderLevel {
  label: string
  price: number
  kind: LadderKind
}

// Price levels for one plan, highest first. The API carries no candles, so
// the moving averages come from the stored indicator snapshot.
export function ladderLevels(t: SwingTicker): LadderLevel[] {
  const plan = t.trade_plan
  if (!plan) return []
  const levels: LadderLevel[] = [
    { label: '2R target', price: plan.target_2r, kind: 'target' },
    { label: 'Chase limit', price: plan.chase_limit, kind: 'chase' },
    { label: 'Entry ref (last close)', price: plan.entry_ref, kind: 'entry' },
    { label: 'Stop / invalidation', price: plan.stop, kind: 'stop' },
  ]
  const ind = t.indicators
  if (ind) {
    levels.push(
      { label: 'EMA10', price: ind.ema10, kind: 'average' },
      { label: 'EMA20', price: ind.ema20, kind: 'average' },
      { label: 'SMA50', price: ind.sma50, kind: 'average' },
    )
  }
  return levels.sort((a, b) => b.price - a.price)
}

function formatCheckValue(value: unknown): string {
  if (typeof value === 'number') return value.toFixed(2)
  if (value == null) return '—'
  return String(value)
}

// One line describing a rule result, used for chip tooltips and the audit list.
export function checkSummary(label: string, check: EligibilityCheck | undefined): string {
  if (!check) return `${label}: not evaluated (an earlier rule failed)`
  return `${label}: ${check.passed ? 'pass' : 'fail'} — ${formatCheckValue(check.value)} (${check.threshold})`
}

export function fmtPrice(n: number | null | undefined): string {
  return n == null ? '—' : n.toFixed(2)
}

export function fmtSigned(n: number | null | undefined, digits = 1): string {
  if (n == null) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}`
}

export function fmtMoney(n: number): string {
  return `$${Math.round(n).toLocaleString('en-US')}`
}

// Whole calendar days between an ISO date and today (local), for the stale hint.
export function daysSince(iso: string, now: Date = new Date()): number {
  const then = new Date(`${iso}T00:00:00`)
  return Math.floor((now.getTime() - then.getTime()) / 86_400_000)
}

const SIZING_KEY = 'quant-hub.swing.sizing'

export interface SizingInputs {
  equity: string
  riskPct: string
}

// localStorage can throw (private windows, blocked storage) -- never rely on it.
export function loadSizing(): SizingInputs {
  const fallback = { equity: String(DEFAULT_EQUITY), riskPct: String(DEFAULT_RISK_PCT) }
  try {
    const raw = window.localStorage.getItem(SIZING_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<SizingInputs>
    return {
      equity: typeof parsed.equity === 'string' ? parsed.equity : fallback.equity,
      riskPct: typeof parsed.riskPct === 'string' ? parsed.riskPct : fallback.riskPct,
    }
  } catch {
    return fallback
  }
}

export function saveSizing(inputs: SizingInputs): void {
  try {
    window.localStorage.setItem(SIZING_KEY, JSON.stringify(inputs))
  } catch {
    /* storage unavailable: keep the in-memory value */
  }
}

// Mirrors SwingParams.max_hold_days / the R8 exit guidance in the spec.
export const MAX_HOLD_DAYS = 10

export const SWING_GLOSSARY: { term: string; meaning: string }[] = [
  {
    term: 'Relative strength (RS)',
    meaning:
      "How much an ETF has beaten SPY over the last 63 and 126 trading days (averaged), in percentage points. RS +5 means it out-gained SPY by about 5 points. Leaders are the top 4 with RS above 0.",
  },
  {
    term: 'Regime gate / market gate',
    meaning:
      "A market-wide safety switch. It is ON only when SPY (the S&P 500) is above both its 50-day and 200-day average. When it is off, the scanner issues no new plans.",
  },
  {
    term: 'Moving averages (SMA50, EMA10, EMA20)',
    meaning:
      'The average closing price over the last 50, 10 or 20 days. Price above them means an uptrend; a dip back to the 20-day is the "pullback" the scanner waits for.',
  },
  {
    term: 'ADX',
    meaning:
      'Trend strength, from 0 to 100. Under 20 means choppy and directionless; 20+ means a real trend. It says nothing about direction, so it is combined with the price checks.',
  },
  {
    term: 'ATR',
    meaning: "An ETF's typical daily price move. The scanner uses it to judge whether a stop is a sensible distance away.",
  },
  {
    term: 'Entry ref',
    meaning: "Yesterday's closing price, where the setup was measured. The plan is for this morning's session, so the real price will differ a little.",
  },
  {
    term: 'Stop / invalidation',
    meaning:
      'The price where the idea is wrong and you would exit. It is set below the recent pullback low, before you enter, and it determines how many shares you can buy.',
  },
  {
    term: 'R (risk per share)',
    meaning: 'Entry minus stop: what you lose per share if the stop is hit. "2R" means a profit of twice that.',
  },
  {
    term: '2R target',
    meaning: 'A price where the gain per share equals twice the risk per share. The plan sells half here and trails the rest.',
  },
  {
    term: 'Chase limit',
    meaning: "The highest price worth paying. If the stock opens above it, the good risk/reward is gone: skip the trade rather than chase.",
  },
]

export const SWING_TIER_HELP: { tier: string; name: string; meaning: string }[] = [
  {
    tier: 'Tier 1',
    name: 'Trigger',
    meaning: 'A full trade plan: leader, uptrend, dipped and turning back up, with a sensible stop. This is the only actionable tier.',
  },
  {
    tier: 'Tier 2',
    name: 'Watch',
    meaning: 'A leader in an uptrend that is dipping but has not turned up yet. Nothing to do today; it may trigger in the coming days.',
  },
  {
    tier: 'Tier 3',
    name: 'Extended',
    meaning: "A leader in an uptrend that has not pulled back. Buying now would be chasing, so the scanner waits for a dip.",
  },
  {
    tier: 'filtered',
    name: 'Filtered',
    meaning: 'Did not qualify. The Outcome column says which check stopped it.',
  },
]

export interface SwingHeadline {
  tone: 'success' | 'warning' | 'destructive' | 'neutral'
  title: string
  detail: string
}

function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join('')
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many
}

// One plain-English sentence pair answering "what does today's scan mean?".
export function swingHeadline(tickers: SwingTicker[], gatePassed: boolean): SwingHeadline {
  const plans = tickers.filter((t) => t.tier === 'Tier 1' && t.trade_plan)
  if (!gatePassed) {
    return {
      tone: 'destructive',
      title: 'No new trades today — the market filter is off',
      detail:
        'SPY is below its 50- or 200-day average, so the scanner issues no trade plans. Anything listed as watch is for information only.',
    }
  }
  if (plans.length > 0) {
    const names = joinNames(plans.map((t) => t.ticker))
    return {
      tone: 'success',
      title: `${plans.length} trade ${plural(plans.length, 'plan', 'plans')} ready: ${names}`,
      detail:
        'Each plan below has an entry reference, a stop and a size. These come from yesterday\'s close, so check the open against each plan\'s chase limit and stop before acting.',
    }
  }

  const leaders = tickers.filter((t) =>
    t.eligibility.checks.some((c) => c.rule === 'R2_leadership' && c.passed),
  )
  if (leaders.length === 0) {
    return {
      tone: 'neutral',
      title: 'No trade today — no ETF is clearly leading SPY',
      detail: 'The market gate is on, but none of the ETFs is beating SPY by enough to qualify as a leader.',
    }
  }
  const trendFail = leaders.filter((t) => t.eligibility.fail_reason === 'trend_fail').length
  const watching = leaders.filter((t) => t.tier === 'Tier 2').length
  const extended = leaders.filter((t) => t.tier === 'Tier 3').length
  const stopIssue = leaders.filter((t) =>
    ['stop_too_wide', 'size_zero', 'correlated', 'signal_cap'].includes(t.eligibility.fail_reason ?? ''),
  ).length
  const blockedByBook = leaders.filter((t) =>
    ['already_open', 'position_limit'].includes(t.eligibility.fail_reason ?? ''),
  ).length
  const parts: string[] = []
  if (watching) parts.push(`${watching} ${plural(watching, 'is', 'are')} pulling back but ${plural(watching, 'has', 'have')} not turned up yet`)
  if (extended) parts.push(`${extended} ${plural(extended, 'is', 'are')} extended and would be a chase`)
  if (trendFail) parts.push(`${trendFail} failed the uptrend check (weak trend strength or below the 50-day average)`)
  if (stopIssue) parts.push(`${stopIssue} had a setup but no usable stop or size`)
  if (blockedByBook) parts.push(`${blockedByBook} had a setup but you already hold it or your open-position limit is reached`)
  return {
    tone: watching ? 'warning' : 'neutral',
    title: watching ? 'No trade yet — leaders are being watched' : 'No trade today',
    detail: `${leaders.length} ${plural(leaders.length, 'ETF is', 'ETFs are')} beating SPY: ${parts.join('; ')}. Doing nothing is a normal outcome — the scanner only flags setups with a defined stop.`,
  }
}

// The one-line summary of a plan, in the words a person would use.
export function planSentence(
  ticker: string,
  plan: { entry_ref: number; chase_limit: number; stop: number; target_2r: number },
  size: PositionSize,
): string {
  const buy =
    size.shares > 0
      ? `buy about ${size.shares.toLocaleString('en-US')} shares of ${ticker}`
      : `enter ${ticker}`
  const risk = size.shares > 0 ? ` — roughly ${fmtMoney(size.riskDollars)} at risk` : ''
  return (
    `This plan would ${buy} near ${fmtPrice(plan.entry_ref)} (no higher than ${fmtPrice(plan.chase_limit)}), ` +
    `and exit if the price falls to ${fmtPrice(plan.stop)}${risk}. ` +
    `First target: ${fmtPrice(plan.target_2r)}, twice the amount risked.`
  )
}
