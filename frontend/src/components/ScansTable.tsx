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

// Only Launchpad uses the Tier 1/2/3 scheme. Verified live: a Lynch
// scan_runs row's tier1_count/tier2_count are NOT "N tickers with tier
// Tier 1/Tier 2" -- for run id=3 (lynch, most_actives), tier2_count=4 but
// the real tier breakdown is stalwart:4/passed:1 (no ticker's tier is
// literally "Tier 2", that string doesn't exist in Lynch's vocabulary).
// Linking those columns for a Lynch row would show a real count but land
// on a filter that finds zero matches -- worse than not linking at all.
// Plain count, not a link, for any other strategy.
function tierCell(row: ScanRunSummary, count: number, tier: string) {
  if (row.strategy_id !== 'launchpad') return count
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
    header: 'Tier 1',
    cell: (info) => tierCell(info.row.original, info.getValue(), 'Tier 1'),
  }),
  columnHelper.accessor('tier2_count', {
    header: 'Tier 2',
    cell: (info) => tierCell(info.row.original, info.getValue(), 'Tier 2'),
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
