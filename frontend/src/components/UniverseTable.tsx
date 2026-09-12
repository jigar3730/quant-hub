import { useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  createColumnHelper,
  createSortedRowModel,
  rowSortingFeature,
  tableFeatures,
  useTable,
  type Row,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp, ChevronRight, ChevronsUpDown } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { RegimeBanner } from '@/components/RegimeBanner'
import { ScanFunnel } from '@/components/ScanFunnel'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  fetchLatestScan,
  fetchScanReport,
  fetchScans,
  type ScoreComponent,
  type TickerDetail,
} from '@/lib/api'
import { LAUNCHPAD_UNIVERSES } from '@/lib/universes'
import {
  filterReason,
  finalScore,
  isActionable,
  orderedScoreKeys,
  scoreLabel,
  tierBadgeVariant,
} from '@/lib/scoring'
import { cn } from '@/lib/utils'

const STRATEGY_ID = 'launchpad'

// Row content is hand-rendered from `row.original` (see below) rather than
// through TanStack's cell/FlexRender machinery — the row markup is too
// interactive (whole-row click-to-expand, badges, sparkbars) to decompose
// cleanly into independent per-column cells. Table is used only for what
// virtualization + sorting actually need: the sorted row model and
// per-column sort state/handlers. Column widths are plain Tailwind classes
// shared between the header and body row builders below, not TanStack's
// column-sizing feature — not needed for a fixed 6-column layout.
const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
})
const columnHelper = createColumnHelper<typeof features, TickerDetail>()

// Mirrors report/builder.py's tier ordering (Tier 1 best) rather than
// alphabetical, so "sort by tier" is actually meaningful.
const TIER_RANK: Record<string, number> = { 'Tier 1': 0, 'Tier 2': 1, 'Tier 3': 2, filtered: 3 }
function tierSortFn(rowA: Row<typeof features, TickerDetail>, rowB: Row<typeof features, TickerDetail>) {
  const a = TIER_RANK[rowA.original.tier] ?? 4
  const b = TIER_RANK[rowB.original.tier] ?? 4
  return a - b
}

// "All tiers" has to be a real sentinel, not "" -- Radix Select reserves
// the empty string for its own internal placeholder state.
const TIER_FILTER_OPTIONS = [
  { value: 'all', label: 'All tiers' },
  { value: 'actionable', label: 'Actionable (Tier 1 + 2)' },
  { value: 'Tier 1', label: 'Tier 1' },
  { value: 'Tier 2', label: 'Tier 2' },
  { value: 'Tier 3', label: 'Tier 3' },
  { value: 'filtered', label: 'Filtered' },
]

const columns = columnHelper.columns([
  columnHelper.accessor('ticker', { id: 'ticker' }),
  columnHelper.accessor('tier', { id: 'tier', sortFn: tierSortFn }),
  columnHelper.accessor((row) => finalScore(row) ?? -Infinity, { id: 'score' }),
])

const EMPTY_TICKERS: TickerDetail[] = []

const COL = {
  expand: 'w-8 shrink-0',
  ticker: 'w-40 shrink-0',
  tier: 'w-28 shrink-0',
  score: 'w-24 shrink-0',
  factors: 'w-36 shrink-0',
  filterReason: 'min-w-0 flex-1',
}

// Inline, always-visible — the old dashboard showed these as small
// multiples directly in its Overview table; hiding them behind a click
// (as an earlier pass here did) was a step backward, not an improvement.
function FactorSparkbars({ scores }: { scores: Record<string, ScoreComponent> | undefined }) {
  return (
    <div className="flex items-end gap-1">
      {orderedScoreKeys(scores).map((key) => {
        const component = scores?.[key]
        const pct =
          component && component.max > 0
            ? Math.max(6, Math.min(100, (component.score / component.max) * 100))
            : 0
        const label = scoreLabel(key)
        return (
          <div
            key={key}
            className="flex h-6 w-2 items-end overflow-hidden rounded-[2px] bg-muted"
            title={component ? `${label}: ${component.score}/${component.max}` : `${label}: n/a`}
          >
            <div className="w-full rounded-[2px] bg-foreground/70" style={{ height: `${pct}%` }} />
          </div>
        )
      })}
    </div>
  )
}

function TickerDrawer({ ticker }: { ticker: TickerDetail }) {
  const scores = ticker.scores ?? {}
  return (
    <div className="bg-muted/30 px-4 py-4">
      {ticker.tier_reason && (
        <p className="text-sm text-foreground">
          <span className="text-muted-foreground">Tier reason: </span>
          {ticker.tier_reason}
        </p>
      )}
      <div className="mt-2 grid gap-3 sm:grid-cols-2">
        {orderedScoreKeys(scores).map((key) => (
          <p key={key} className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{scoreLabel(key)}</span>
            {' '}({scores[key].score}/{scores[key].max}): {scores[key].meaning}
          </p>
        ))}
      </div>
      {(ticker.sector_etf || (!ticker.eligible && filterReason(ticker))) && (
        <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
          {ticker.sector_etf && <span>Sector ETF: {ticker.sector_etf}</span>}
          {!ticker.eligible && filterReason(ticker) && (
            <span>Filter reason: {filterReason(ticker)}</span>
          )}
        </div>
      )}
    </div>
  )
}

function SortIcon({ state }: { state: false | 'asc' | 'desc' }) {
  if (state === 'asc') return <ArrowUp className="size-3.5" />
  if (state === 'desc') return <ArrowDown className="size-3.5" />
  return <ChevronsUpDown className="size-3.5 text-muted-foreground/50" />
}

export function UniverseTable() {
  // universe/date/tier live in the URL (?universe=&date=&tier=), same
  // pattern as the ticker in Ticker 360 -- so a link from Recent Scans
  // ("Tier 2 has 2 candidates" -> click -> see them) works, and this page
  // stays linkable/bookmarkable rather than only reachable through its own
  // controls. Derived directly from searchParams every render (not a
  // separate useState that's only initialized once) so re-navigating here
  // with different params actually updates the page -- react-router
  // doesn't remount the component just because the query string changed
  // on the same route.
  const [searchParams, setSearchParams] = useSearchParams()
  const universeId = searchParams.get('universe') ?? LAUNCHPAD_UNIVERSES[0].id
  const selectedDate = searchParams.get('date')
  const tierFilter = searchParams.get('tier')

  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const scrollRef = useRef<HTMLDivElement>(null)

  function setUniverseId(id: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('universe', id)
      return next
    })
  }

  function setSelectedDate(date: string | null) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (date) next.set('date', date)
      else next.delete('date')
      return next
    })
  }

  function setTierFilter(tier: string | null) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (tier) next.set('tier', tier)
      else next.delete('tier')
      return next
    })
  }

  // null selectedDate -> latest scan (the original default); a picked date
  // looks up that day's run specifically instead, via the same /scans
  // endpoint the "Recent scans" list already uses (since/until filters).
  // A day with no run is a normal, expected outcome here (Lynch runs
  // weekly, Launchpad doesn't run every universe every day) -- resolves
  // to `null`, not an error, so it gets its own message rather than being
  // conflated with a real fetch failure.
  const scanRun = useQuery({
    queryKey: ['scans', 'for-universe', { strategyId: STRATEGY_ID, universeId, selectedDate }],
    queryFn: async () => {
      if (selectedDate) {
        const rows = await fetchScans({
          strategyId: STRATEGY_ID,
          universeId,
          since: selectedDate,
          until: selectedDate,
          limit: 1,
        })
        return rows[0] ?? null
      }
      return fetchLatestScan({ strategyId: STRATEGY_ID, universeId })
    },
  })

  const report = useQuery({
    queryKey: ['scans', 'report', scanRun.data?.id],
    queryFn: () => fetchScanReport(scanRun.data!.id),
    enabled: scanRun.data != null,
  })

  // Filters the underlying data, not just the rendered rows -- so counts,
  // sorting, and virtualization all operate on the actually-selected set.
  const filteredTickers = useMemo(() => {
    const all = report.data?.tickers ?? EMPTY_TICKERS
    if (!tierFilter) return all
    // "Actionable" spans Tier 1 + Tier 2 together (and requires eligible),
    // not a single tier value -- reuses the same isActionable() the row
    // badge already uses, rather than hardcoding "Tier 1 or Tier 2" here
    // and risking the two definitions drifting apart.
    if (tierFilter === 'actionable') {
      return all.filter((t) => isActionable(STRATEGY_ID, t))
    }
    return all.filter((t) => t.tier === tierFilter)
  }, [report.data, tierFilter])

  const table = useTable({
    features,
    columns,
    data: filteredTickers,
    initialState: { sorting: [{ id: 'score', desc: true }] },
  })
  const rows = table.getRowModel().rows

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 44,
    getItemKey: (index) => rows[index].id,
    overscan: 8,
  })

  function toggleRow(ticker: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(ticker)) next.delete(ticker)
      else next.add(ticker)
      return next
    })
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium text-foreground" htmlFor="universe-select">
          Universe
        </label>
        <Select value={universeId} onValueChange={setUniverseId}>
          <SelectTrigger id="universe-select" className="w-64">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LAUNCHPAD_UNIVERSES.map((universe) => (
              <SelectItem key={universe.id} value={universe.id}>
                {universe.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <label className="text-sm font-medium text-foreground" htmlFor="scan-date">
          Scan date
        </label>
        <Input
          id="scan-date"
          type="date"
          value={selectedDate ?? ''}
          onChange={(e) => setSelectedDate(e.target.value || null)}
          className="w-40"
        />
        {selectedDate && (
          <Button variant="outline" size="sm" onClick={() => setSelectedDate(null)}>
            Latest
          </Button>
        )}

        <label className="text-sm font-medium text-foreground" htmlFor="tier-filter">
          Tier
        </label>
        <Select
          value={tierFilter ?? 'all'}
          onValueChange={(value) => setTierFilter(value === 'all' ? null : value)}
        >
          <SelectTrigger id="tier-filter" className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TIER_FILTER_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {scanRun.data && (
          <span className="text-sm text-muted-foreground">
            Showing: {scanRun.data.scan_date}
          </span>
        )}
      </div>

      <div className="mt-4">
        {scanRun.isLoading && (
          <p className="text-sm text-muted-foreground">Loading scan…</p>
        )}
        {scanRun.isError && (
          <p className="text-sm text-destructive">
            No scan runs found for this universe yet.
          </p>
        )}
        {!scanRun.isLoading && !scanRun.isError && scanRun.data == null && (
          <p className="text-sm text-muted-foreground">
            No scan run found for {universeId} on {selectedDate}.
          </p>
        )}
        {report.isLoading && scanRun.data && (
          <p className="text-sm text-muted-foreground">Loading universe report…</p>
        )}
        {report.isError && (
          <p className="text-sm text-destructive">
            Failed to load report: {(report.error as Error).message}
          </p>
        )}

        {report.data && (
          <div className="mb-4">
            <RegimeBanner regime={report.data.market_regime} />
          </div>
        )}

        {report.data && (
          <div className="mb-4">
            <ScanFunnel summary={report.data.scan_summary} />
          </div>
        )}

        {report.data && rows.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {tierFilter
              ? `No ${tierFilter} tickers in this report.`
              : 'No tickers in this report.'}
          </p>
        )}

        {report.data && rows.length > 0 && (
          <div className="rounded-md border border-border">
            <div className="flex border-b border-border bg-muted/30 text-sm font-medium text-foreground">
              <div className={cn(COL.expand, 'px-2 py-2')} />
              {(
                [
                  { id: 'ticker', label: 'Ticker', className: COL.ticker },
                  { id: 'tier', label: 'Tier', className: COL.tier },
                  { id: 'score', label: 'Final score', className: COL.score },
                ] as const
              ).map(({ id, label, className }) => {
                const column = table.getColumn(id)
                return (
                  <button
                    key={id}
                    type="button"
                    className={cn(
                      'flex items-center gap-1 px-2 py-2 text-left hover:text-foreground',
                      className,
                    )}
                    onClick={column?.getToggleSortingHandler()}
                  >
                    {label}
                    <SortIcon state={column?.getIsSorted() ?? false} />
                  </button>
                )
              })}
              <div className={cn(COL.factors, 'px-2 py-2')}>Factors</div>
              <div className={cn(COL.filterReason, 'px-2 py-2')}>Filter reason</div>
            </div>

            <div ref={scrollRef} className="max-h-[600px] overflow-auto">
              <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
                {virtualizer.getVirtualItems().map((item) => {
                  const row = rows[item.index]
                  const ticker = row.original
                  const isOpen = expanded.has(ticker.ticker)
                  const actionable = isActionable(report.data!.strategy_id, ticker)
                  return (
                    <div
                      key={row.id}
                      data-index={item.index}
                      ref={virtualizer.measureElement}
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        transform: `translateY(${item.start}px)`,
                      }}
                    >
                      <div
                        className="flex cursor-pointer items-center border-b border-border hover:bg-muted/50"
                        aria-expanded={isOpen}
                        onClick={() => toggleRow(ticker.ticker)}
                      >
                        <div className={cn(COL.expand, 'flex items-center px-2 py-2')}>
                          <ChevronRight
                            className={cn(
                              'size-4 text-muted-foreground transition-transform',
                              isOpen && 'rotate-90',
                            )}
                          />
                        </div>
                        <div
                          className={cn(
                            COL.ticker,
                            'flex items-center gap-2 px-2 py-2 font-medium text-foreground',
                          )}
                        >
                          <Link
                            to={`/ticker/${ticker.ticker}`}
                            onClick={(e) => e.stopPropagation()}
                            className="hover:underline"
                          >
                            {ticker.ticker}
                          </Link>
                          {actionable && <Badge variant="success">Actionable</Badge>}
                        </div>
                        <div className={cn(COL.tier, 'flex items-center px-2 py-2')}>
                          <Badge variant={tierBadgeVariant(ticker.tier)}>{ticker.tier}</Badge>
                        </div>
                        <div className={cn(COL.score, 'flex items-center px-2 py-2 tabular-nums')}>
                          {finalScore(ticker) != null ? finalScore(ticker)!.toFixed(1) : '—'}
                        </div>
                        <div className={cn(COL.factors, 'flex items-center px-2 py-2')}>
                          <FactorSparkbars scores={ticker.scores} />
                        </div>
                        <div
                          className={cn(
                            COL.filterReason,
                            'flex items-center truncate px-2 py-2 text-muted-foreground',
                          )}
                        >
                          {!ticker.eligible ? filterReason(ticker) : '—'}
                        </div>
                      </div>
                      {isOpen && <TickerDrawer ticker={ticker} />}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
