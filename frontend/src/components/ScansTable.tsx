import { useQuery } from '@tanstack/react-query'
import { createColumnHelper, tableFeatures, useTable } from '@tanstack/react-table'
import { Link } from 'react-router'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { fetchScans, type ScanRunSummary } from '@/lib/api'
import { regimeVariant } from '@/lib/regime'

const features = tableFeatures({})
const columnHelper = createColumnHelper<typeof features, ScanRunSummary>()

// Correction (was wrong in an earlier pass): tier1_count/tier2_count on a
// Lynch scan_runs row are NOT meaningless for Lynch -- repository.py's
// _tier_counts_from_run repurposes those exact columns for Lynch's
// fast_grower/stalwart counts respectively (confirmed at
// infrastructure/postgres/repository.py:80-81, and the FG=/ST=/AP= legend
// in dashboard/app.py:87). tier2_count=4 on the Lynch run used to verify
// this literally means 4 stalwart tickers. So each column needs the
// tier value that's actually correct for the row's own strategy, not a
// single hardcoded literal used regardless of strategy.
function tierCell(row: ScanRunSummary, count: number, launchpadTier: string, lynchTier: string) {
  const tier = row.strategy_id === 'lynch' ? lynchTier : launchpadTier
  const params = new URLSearchParams({
    strategy: row.strategy_id,
    universe: row.universe_id,
    date: row.scan_date,
    tier,
  })
  return (
    <Link to={`/universe?${params.toString()}`} className="hover:underline">
      {count}
    </Link>
  )
}

// Actionable is genuinely strategy-agnostic (list_actionable_tickers_for_run
// works the same way for both strategies, and actionable_count sums
// correctly against the real tier breakdown for both -- verified live for
// the Lynch case above: stalwart 4 + passed 1 = actionable_count 5). Links
// for any strategy, unlike tierCell above.
function actionableCell(row: ScanRunSummary, count: number) {
  const params = new URLSearchParams({
    strategy: row.strategy_id,
    universe: row.universe_id,
    date: row.scan_date,
    tier: 'actionable',
  })
  return (
    <Link to={`/universe?${params.toString()}`} className="hover:underline">
      {count}
    </Link>
  )
}

const columns = columnHelper.columns([
  columnHelper.accessor('scan_date', { header: 'Scan date' }),
  columnHelper.accessor('strategy_id', { header: 'Strategy' }),
  columnHelper.accessor('universe_id', { header: 'Universe' }),
  columnHelper.accessor('regime_label', {
    header: 'Regime',
    cell: (info) => (
      <Badge variant={regimeVariant(info.getValue())}>{info.getValue()}</Badge>
    ),
  }),
  columnHelper.accessor('tier1_count', {
    header: () => <span title="Launchpad: Tier 1. Lynch: Fast Grower.">Tier 1</span>,
    cell: (info) => tierCell(info.row.original, info.getValue(), 'Tier 1', 'fast_grower'),
  }),
  columnHelper.accessor('tier2_count', {
    header: () => <span title="Launchpad: Tier 2. Lynch: Stalwart.">Tier 2</span>,
    cell: (info) => tierCell(info.row.original, info.getValue(), 'Tier 2', 'stalwart'),
  }),
  columnHelper.accessor('actionable_count', {
    header: 'Actionable',
    cell: (info) => actionableCell(info.row.original, info.getValue()),
  }),
])

const EMPTY_SCANS: ScanRunSummary[] = []

export function ScansTable() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['scans', { limit: 20 }],
    queryFn: () => fetchScans({ limit: 20 }),
  })

  const table = useTable({ features, columns, data: data ?? EMPTY_SCANS })

  if (isLoading) return <p className="text-muted-foreground text-sm">Loading scans…</p>
  if (isError) {
    return (
      <p className="text-destructive text-sm">
        Failed to load /scans: {(error as Error).message}
      </p>
    )
  }
  if (data && data.length === 0) {
    return <p className="text-muted-foreground text-sm">No scan runs found.</p>
  }

  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((headerGroup) => (
          <TableRow key={headerGroup.id}>
            {headerGroup.headers.map((header) => (
              <TableHead key={header.id}>
                {header.isPlaceholder ? null : <table.FlexRender header={header} />}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => (
          <TableRow key={row.id}>
            {row.getAllCells().map((cell) => (
              <TableCell key={cell.id}>
                <table.FlexRender cell={cell} />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
