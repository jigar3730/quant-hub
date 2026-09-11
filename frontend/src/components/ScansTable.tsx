import { useQuery } from '@tanstack/react-query'
import { createColumnHelper, tableFeatures, useTable } from '@tanstack/react-table'
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

const features = tableFeatures({})
const columnHelper = createColumnHelper<typeof features, ScanRunSummary>()

const columns = columnHelper.columns([
  columnHelper.accessor('scan_date', { header: 'Scan date' }),
  columnHelper.accessor('strategy_id', { header: 'Strategy' }),
  columnHelper.accessor('universe_id', { header: 'Universe' }),
  columnHelper.accessor('regime_label', {
    header: 'Regime',
    cell: (info) => <Badge variant="outline">{info.getValue()}</Badge>,
  }),
  columnHelper.accessor('tier1_count', { header: 'Tier 1' }),
  columnHelper.accessor('tier2_count', { header: 'Tier 2' }),
  columnHelper.accessor('actionable_count', { header: 'Actionable' }),
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
