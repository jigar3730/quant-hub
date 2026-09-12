import { useQuery } from '@tanstack/react-query'
import { fetchCommandCenter, type CommandCenterCoverage } from '@/lib/api'
import { LAUNCHPAD_UNIVERSES } from '@/lib/universes'
import { cn } from '@/lib/utils'

// docs/FINANCIAL_UI_REIMAGINED.md §3.3/§4.2 (build sequence item #7) —
// originally scoped for Plotly.js. Reversed that during implementation:
// `npm audit` found a critical XSS vulnerability in maplibre-gl, a
// transitive dependency of plotly.js, with no safe version combination --
// react-plotly.js requires plotly.js >=3.0.0, but every plotly.js version
// >=2.35.0 depends on the vulnerable maplibre-gl range. Rather than ship a
// large dependency with an unavoidable critical vulnerability for a
// strategy x universe grid this simple, built it the same way as every
// other visualization this session (FactorSparkbars, ScanFunnel,
// TickerAuditTrail): plain divs, zero new dependencies.
const STRATEGIES = [
  { id: 'launchpad', label: 'Launchpad' },
  { id: 'lynch', label: 'Lynch' },
]

function cellIntensityClass(count: number | undefined): string {
  if (count == null) return 'bg-muted/30'
  if (count === 0) return 'bg-muted'
  if (count <= 1) return 'bg-success/30'
  if (count <= 3) return 'bg-success/60'
  return 'bg-success'
}

function findCoverage(
  coverage: CommandCenterCoverage[],
  universeId: string,
  strategyId: string,
): CommandCenterCoverage | undefined {
  return coverage.find((c) => c.universe_id === universeId && c.strategy_id === strategyId)
}

export function CommandCenterHeatmap() {
  const commandCenter = useQuery({
    queryKey: ['command-center'],
    queryFn: () => fetchCommandCenter(),
  })

  if (commandCenter.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }
  if (commandCenter.isError) {
    return (
      <p className="text-sm text-destructive">
        Failed to load command center: {(commandCenter.error as Error).message}
      </p>
    )
  }

  const coverage = commandCenter.data!.coverage
  if (coverage.length === 0) {
    return <p className="text-sm text-muted-foreground">No scans have run yet today.</p>
  }

  // Every known universe, scanned today or not -- a coverage heatmap's
  // whole point is showing gaps (a universe that never scans), not just
  // where signal happens to exist. Anything covered today outside the
  // known list is appended rather than silently dropped.
  const knownIds = LAUNCHPAD_UNIVERSES.map((u) => u.id)
  const coveredIds = [...new Set(coverage.map((c) => c.universe_id))]
  const universeIds = [...knownIds, ...coveredIds.filter((id) => !knownIds.includes(id))]

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr>
          <th className="p-2 text-left font-medium text-muted-foreground">Universe</th>
          {STRATEGIES.map((s) => (
            <th key={s.id} className="p-2 text-center font-medium text-muted-foreground">
              {s.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {universeIds.map((universeId) => (
          <tr key={universeId} className="border-t border-border">
            <td className="p-2 text-foreground">{universeId}</td>
            {STRATEGIES.map((s) => {
              const entry = findCoverage(coverage, universeId, s.id)
              return (
                <td key={s.id} className="p-1">
                  <div
                    className={cn(
                      'mx-auto flex h-10 w-16 items-center justify-center rounded-md text-xs font-medium text-foreground',
                      cellIntensityClass(entry?.actionable_count),
                    )}
                    title={
                      entry
                        ? `${entry.actionable_count} actionable (Tier 1: ${entry.tier1_count})`
                        : 'No scan today'
                    }
                  >
                    {entry ? entry.actionable_count : '—'}
                  </div>
                </td>
              )
            })}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
