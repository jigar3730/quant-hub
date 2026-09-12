import { useRef, useState } from 'react'
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
import { Link } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { RegimeBanner } from '@/components/RegimeBanner'
import { ScanFunnel } from '@/components/ScanFunnel'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { fetchLatestScan, fetchScanReport, type ScoreComponent, type TickerDetail } from '@/lib/api'
import { LAUNCHPAD_UNIVERSES } from '@/lib/universes'
import {
  SCORE_LABELS,
  SCORE_ORDER,
  filterReason,
  finalScore,
  isActionable,
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
      {SCORE_ORDER.map((key) => {
        const component = scores?.[key]
        const pct =
          component && component.max > 0
            ? Math.max(6, Math.min(100, (component.score / component.max) * 100))
            : 0
        const label = SCORE_LABELS[key] ?? key
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
        {SCORE_ORDER.filter((key) => scores[key]).map((key) => (
          <p key={key} className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{SCORE_LABELS[key] ?? key}</span>
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
  const [universeId, setUniverseId] = useState(LAUNCHPAD_UNIVERSES[0].id)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const scrollRef = useRef<HTMLDivElement>(null)

  const latestScan = useQuery({
    queryKey: ['scans', 'latest', { strategyId: STRATEGY_ID, universeId }],
    queryFn: () => fetchLatestScan({ strategyId: STRATEGY_ID, universeId }),
  })

  const report = useQuery({
    queryKey: ['scans', 'report', latestScan.data?.id],
    queryFn: () => fetchScanReport(latestScan.data!.id),
    enabled: latestScan.data != null,
  })

  const table = useTable({
    features,
    columns,
    data: report.data?.tickers ?? EMPTY_TICKERS,
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
      <div className="flex items-center gap-3">
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
        {latestScan.data && (
          <span className="text-sm text-muted-foreground">
            Scan date: {latestScan.data.scan_date}
          </span>
        )}
      </div>

      <div className="mt-4">
        {latestScan.isLoading && (
          <p className="text-sm text-muted-foreground">Loading latest scan…</p>
        )}
        {latestScan.isError && (
          <p className="text-sm text-destructive">
            No scan runs found for this universe yet.
          </p>
        )}
        {report.isLoading && latestScan.data && (
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
          <p className="text-sm text-muted-foreground">No tickers in this report.</p>
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
