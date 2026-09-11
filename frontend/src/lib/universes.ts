// Mirrors data/universes.json's `name` fields. Kept as a small frontend
// constant rather than a new API endpoint — Phase 1's API surface is a
// read-only pass-through over the scan/ticker repositories and doesn't
// expose universe metadata yet (docs/MODERNIZATION_AUDIT.md §3.1).
export interface UniverseOption {
  id: string
  name: string
}

export const LAUNCHPAD_UNIVERSES: UniverseOption[] = [
  { id: 'sp500_index', name: 'S&P 500 (SPY holdings)' },
  { id: 'large_cap_growth', name: 'Large Cap Growth' },
  { id: 'mid_cap_growth', name: 'Mid Cap Growth' },
  { id: 'small_cap_growth', name: 'Small Cap Growth' },
  { id: 'dividend_growers', name: 'Dividend Growers' },
  { id: 'fintech_growth', name: 'Fintech & Digital Growth' },
  { id: 'most_actives', name: 'Most Actives' },
  { id: 'mega_runners', name: 'Mega Runners Watchlist' },
]
