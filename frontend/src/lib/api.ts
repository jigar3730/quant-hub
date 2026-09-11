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

export interface ScanReport {
  strategy_id: string
  universe_id: string
  scan_date: string
  scan_time: string | null
  scan_summary: Record<string, unknown>
  market_regime: Record<string, unknown>
  tickers: TickerDetail[]
}

export function fetchScanReport(runId: number): Promise<ScanReport> {
  return apiGet<ScanReport>(`/scans/${runId}/report`)
}
