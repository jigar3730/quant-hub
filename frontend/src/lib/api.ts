// Thin client for the Phase 1 read-only API (docs/API_RUNBOOK.md).
// Requests go through Vite's dev proxy at /api — see vite.config.ts.

export interface ScanRunSummary {
  id: number
  scan_date: string
  scan_time: string
  strategy_id: string
  universe_id: string
  universe_size: number
  tier1_count: number
  tier2_count: number
  tier3_count: number
  filtered_count: number
  actionable_count: number
  regime_label: string
  regime_multiplier: number
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) {
    throw new Error(`${path} responded ${res.status}`)
  }
  return res.json() as Promise<T>
}

export function fetchScans(
  params: { limit?: number; strategyId?: string; universeId?: string } = {},
): Promise<ScanRunSummary[]> {
  const search = new URLSearchParams()
  if (params.limit) search.set('limit', String(params.limit))
  if (params.strategyId) search.set('strategy_id', params.strategyId)
  if (params.universeId) search.set('universe_id', params.universeId)
  const qs = search.toString()
  return apiGet<ScanRunSummary[]>(`/scans${qs ? `?${qs}` : ''}`)
}

export function fetchLatestScan(params: {
  strategyId?: string
  universeId?: string
}): Promise<ScanRunSummary> {
  const search = new URLSearchParams()
  search.set('strategy_id', params.strategyId ?? 'launchpad')
  if (params.universeId) search.set('universe_id', params.universeId)
  return apiGet<ScanRunSummary>(`/scans/latest?${search.toString()}`)
}

// One named component of the Launchpad score, e.g. `scores.squeeze_intensity`.
// `raw` varies per component (see docs/MODERNIZATION_AUDIT.md §3.3) so it's
// kept as an untyped record rather than a strict union.
export interface ScoreComponent {
  score: number
  max: number
  raw: Record<string, unknown>
  meaning: string
}

export interface EligibilityCheck {
  rule: string
  passed: boolean
  value: unknown
  threshold: string
}

export interface EligibilityDetail {
  passed: boolean
  fail_reason: string | null
  checks: EligibilityCheck[]
  summary: string
}

export interface ScoreSummary {
  raw_score: number
  normalized_score: number
  regime_multiplier: number
  final_adjusted_score: number
}

// Mirrors the real `detail` JSONB shape built by
// `report/builder.py::build_ticker_report` — broader than the API's
// `TickerDetail` Pydantic model, which only declares a few stable fields
// and passes the rest through untouched (`extra="allow"`).
export interface TickerDetail {
  ticker: string
  verdict: 'eligible' | 'excluded' | string
  eligible: boolean
  tier: 'Tier 1' | 'Tier 2' | 'Tier 3' | 'filtered' | string
  tier_reason?: string
  sector_etf?: string
  eligibility?: EligibilityDetail
  scores?: Record<string, ScoreComponent>
  summary?: ScoreSummary
}

// Mirrors `regime/market.py::regime_detail`'s return dict exactly.
export interface MarketRegimeDetail {
  label: string
  multiplier: number
  meaning: string
  spy_price: number
  sma50: number
  sma200: number
  high_52w: number
  return_63d_pct: number
  pct_below_52w_high: number
}

// Mirrors `report/builder.py`'s `scan_summary` (sibling to `tickers`, not
// per-ticker) — tier_counts/filter_breakdown keys vary by strategy, so they
// stay loosely typed rather than an exhaustive union.
export interface ScanSummary {
  universe_size: number
  eligible_count: number
  excluded_count: number
  actionable_count: number
  tier_counts: Record<string, number>
  filter_breakdown: Record<string, number>
}

export interface ScanReport {
  strategy_id: string
  universe_id: string
  scan_date: string
  scan_time: string | null
  scan_summary: ScanSummary
  market_regime: MarketRegimeDetail
  tickers: TickerDetail[]
}

export function fetchScanReport(runId: number): Promise<ScanReport> {
  return apiGet<ScanReport>(`/scans/${runId}/report`)
}

// One appearance of a ticker in a scan run, from
// `history/ticker_projection.py::project_row`. The 5 base fields are typed
// on the API's `TickerHistoryRow` model; everything else is `extra="allow"`
// and varies by `strategy_id` (launchpad vs. lynch) — kept optional here
// rather than split into two types since a caller may not filter by strategy.
export interface TickerHistoryRow {
  run_id: number
  scan_date: string
  strategy_id: string
  universe_id: string
  ticker: string
  strategy_label?: string
  tier?: string | null
  tier_label?: string | null
  eligible?: boolean | null
  filter_reason?: string | null
  sector_etf?: string | null
  regime_label?: string | null
  regime_multiplier?: number | null
  final_score?: number | null
  // launchpad-only
  tier_reason?: string | null
  normalized_score?: number | null
  // lynch-only
  lynch_score?: number | null
  passed?: boolean | null
  categories?: string | null
  company_name?: string | null
}

export interface TickerHistoryPage {
  ticker: string
  total: number
  limit: number
  offset: number
  rows: TickerHistoryRow[]
}

export function fetchTickerHistory(
  ticker: string,
  params: {
    actionableOnly?: boolean
    strategyId?: string
    universeId?: string
    limit?: number
    offset?: number
  } = {},
): Promise<TickerHistoryPage> {
  const search = new URLSearchParams()
  search.set('actionable_only', String(params.actionableOnly ?? true))
  if (params.strategyId) search.set('strategy_id', params.strategyId)
  if (params.universeId) search.set('universe_id', params.universeId)
  search.set('limit', String(params.limit ?? 20))
  search.set('offset', String(params.offset ?? 0))
  return apiGet<TickerHistoryPage>(
    `/tickers/${encodeURIComponent(ticker)}/history?${search.toString()}`,
  )
}
