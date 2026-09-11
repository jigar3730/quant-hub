import { ScansTable } from '@/components/ScansTable'

function App() {
  return (
    <div className="mx-auto max-w-5xl p-8">
      <h1 className="text-foreground text-2xl font-semibold">Quant Hub</h1>
      <p className="text-muted-foreground mt-1 text-sm">
        Phase 2 design-system scaffold — reading live data from the Phase 1 API.
      </p>
      <div className="mt-6">
        <ScansTable />
      </div>
    </div>
  )
}

export default App
