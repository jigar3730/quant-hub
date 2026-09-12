import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { TickerAuditTrail } from '@/components/TickerAuditTrail'
import { TickerOutcomesCard } from '@/components/TickerOutcomesCard'
import { TickerTechnicalCard } from '@/components/TickerTechnicalCard'
import { fetchTickerHistory } from '@/lib/api'
import { regimeVariant } from '@/lib/regime'
import { tierBadgeVariant } from '@/lib/scoring'

const PAGE_SIZE = 20

export function TickerHistory() {
  const [input, setInput] = useState('')
  const [ticker, setTicker] = useState<string | null>(null)
  const [actionableOnly, setActionableOnly] = useState(true)
  const [offset, setOffset] = useState(0)

  const history = useQuery({
    queryKey: ['tickers', ticker, 'history', { actionableOnly, offset }],
    queryFn: () =>
      fetchTickerHistory(ticker!, { actionableOnly, limit: PAGE_SIZE, offset }),
    enabled: ticker != null,
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    const trimmed = input.trim().toUpperCase()
    if (!trimmed) return
    setOffset(0)
    setTicker(trimmed)
  }

  function toggleActionableOnly(checked: boolean) {
    setActionableOnly(checked)
    setOffset(0)
  }

  const total = history.data?.total ?? 0
  const hasPrev = offset > 0
  const hasNext = offset + PAGE_SIZE < total

  return (
    <div>
      <form onSubmit={submit} className="flex flex-wrap items-center gap-3">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ticker, e.g. AAPL"
          className="w-40"
          aria-label="Ticker symbol"
        />
        <Button type="submit" variant="outline">
          Look up
        </Button>
        <label className="flex items-center gap-2 text-sm text-foreground">
          <Checkbox
            checked={actionableOnly}
            onCheckedChange={(checked) => toggleActionableOnly(checked === true)}
          />
          Actionable appearances only
        </label>
      </form>

      {ticker != null && (
        <div className="mt-4">
          <TickerTechnicalCard ticker={ticker} />
        </div>
      )}

      {ticker != null && (
        <div className="mt-4">
          <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            ML outcomes
          </h3>
          <TickerOutcomesCard ticker={ticker} />
        </div>
      )}

      {ticker != null && (
        <div className="mt-4">
          <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Audit trail
          </h3>
          <TickerAuditTrail ticker={ticker} />
        </div>
      )}

      <div className="mt-4">
        {ticker == null && (
          <p className="text-sm text-muted-foreground">
            Look up a ticker to see every scan run it appeared in.
          </p>
        )}
        {history.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {history.isError && (
          <p className="text-sm text-destructive">
            Failed to load history: {(history.error as Error).message}
          </p>
        )}
        {history.data && history.data.rows.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No {actionableOnly ? 'actionable ' : ''}history found for {history.data.ticker}.
          </p>
        )}

        {history.data && history.data.rows.length > 0 && (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Scan date</TableHead>
                  <TableHead>Strategy</TableHead>
                  <TableHead>Universe</TableHead>
                  <TableHead>Tier</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Regime</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.data.rows.map((row) => (
                  <TableRow key={row.run_id}>
                    <TableCell>{row.scan_date}</TableCell>
                    <TableCell>{row.strategy_label ?? row.strategy_id}</TableCell>
                    <TableCell>{row.universe_id}</TableCell>
                    <TableCell>
                      {row.tier ? (
                        <Badge variant={tierBadgeVariant(row.tier)}>
                          {row.tier_label ?? row.tier}
                        </Badge>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {(row.final_score ?? row.lynch_score) != null
                        ? (row.final_score ?? row.lynch_score)!.toFixed(1)
                        : '—'}
                    </TableCell>
                    <TableCell>
                      {row.regime_label ? (
                        <Badge variant={regimeVariant(row.regime_label)}>
                          {row.regime_label}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
              <span>
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!hasPrev}
                  onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!hasNext}
                  onClick={() => setOffset((o) => o + PAGE_SIZE)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
