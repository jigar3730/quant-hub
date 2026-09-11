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

export function fetchScans(params: { limit?: number } = {}): Promise<ScanRunSummary[]> {
  const search = new URLSearchParams()
  if (params.limit) search.set('limit', String(params.limit))
  const qs = search.toString()
  return apiGet<ScanRunSummary[]>(`/scans${qs ? `?${qs}` : ''}`)
}
