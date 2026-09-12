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
// One Lynch screening rule (lynch/explain.py::enrich_checks). `passed` is
// already phrased so true always means "good" from the user's point of
// view (e.g. the `wall_street_neglect` rule's own label is "Not
// over-owned by Wall Street") -- render this directly rather than
// re-deriving per-field thresholds, since some fields (institutional_pct,
// analyst_count) are lower-is-better and a naive color scale would
// mislead.
export interface LynchCheck {
  rule: string
  label: string
  value: unknown
  detail: string
  passed: boolean
  threshold: string
  plain_value: string
  result_text: string
  why_it_matters: string
}

export interface TickerDetail {
  ticker: string
  // Launchpad-only; not present on Lynch tickers (confirmed live, run id 3).
  verdict?: 'eligible' | 'excluded' | string
  eligible: boolean
  tier: 'Tier 1' | 'Tier 2' | 'Tier 3' | 'filtered' | string
  tier_reason?: string
  sector_etf?: string
  eligibility?: EligibilityDetail
  scores?: Record<string, ScoreComponent>
  summary?: ScoreSummary
  // Lynch-only extras (lynch/runner.py::_evaluate). `categories` is a
  // non-exclusive set -- a ticker can be more than one at once -- distinct
  // from `tier`, which picks just the first matching category or falls
  // back to "passed"/"filtered".
  categories?: string[]
  lynch_score?: number | null
  company_name?: string | null
  sector?: string | null
  investor_summary?: string | null
  checks?: LynchCheck[]
  pe_ratio?: number | null
  peg_ratio?: number | null
  eps_growth_5y_pct?: number | null
  eps_growth_ttm_pct?: number | null
  debt_to_equity?: number | null
  institutional_pct?: number | null
  analyst_count?: number | null
  market_cap?: number | null
  dividend_yield?: number | null
  price_to_book?: number | null
  net_cash?: number | null
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

// Mirrors `digest/command_center.py::build_command_center_payload`.
export interface CommandCenterCoverage {
  strategy_id: string
  strategy_label: string
  universe_id: string
  run_id: number
  actionable_count: number
  tier1_count: number
  tier2_count: number
  regime_label: string | null
  scan_time: string | null
}

// The lightweight `list_actionable_tickers_for_run` projection — ticker,
// tier, eligible, sector_etf, final_score — with run/universe/regime
// context added. No per-factor score breakdown at this level (no JSONB
// load); drill into GET /scans/{run_id}/report for that.
export interface ActionableTicker {
  ticker: string
  tier: string
  eligible: boolean
  sector_etf: string | null
  final_score: number | null
  strategy_id: string
  universe_id: string
  run_id: number
  regime_label: string | null
  scan_time: string | null
}

export interface CommandCenterPayload {
  scan_date: string
  generated_at: string
  regime_label: string | null
  regime_multiplier: number | null
  run_count: number
  per_strategy: Record<string, { actionable: number; tier1: number; universes: number }>
  coverage: CommandCenterCoverage[]
  actionable_tickers: ActionableTicker[]
  overlap_count: number
}

// Mirrors `api/schemas.py::OutcomeRow`. strategy_id/universe_id/scan_date
// are only populated by the ticker-filtered query (a join to scan_runs) --
// null when fetched by run_id instead.
export interface OutcomeRow {
  run_id: number
  ticker: string
  horizon_days: number
  anchor_date: string | null
  forward_return_pct: number | null
  forward_max_gain_pct: number | null
  forward_max_drawdown_pct: number | null
  spy_forward_return_pct: number | null
  excess_return_pct: number | null
  label_binary: boolean | null
  label_status: string
  computed_at: string | null
  strategy_id: string | null
  universe_id: string | null
  scan_date: string | null
}

export function fetchOutcomesForTicker(
  ticker: string,
  params: { strategyId?: string; horizonDays?: number; limit?: number } = {},
): Promise<OutcomeRow[]> {
  const search = new URLSearchParams()
  search.set('ticker', ticker)
  if (params.strategyId) search.set('strategy_id', params.strategyId)
  if (params.horizonDays != null) search.set('horizon_days', String(params.horizonDays))
  search.set('limit', String(params.limit ?? 50))
  return apiGet<OutcomeRow[]>(`/outcomes?${search.toString()}`)
}

export function fetchCommandCenter(scanDate?: string): Promise<CommandCenterPayload> {
  const search = scanDate ? `?scan_date=${scanDate}` : ''
  return apiGet<CommandCenterPayload>(`/command-center${search}`)
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
