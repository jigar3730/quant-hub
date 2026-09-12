import { NavLink, Outlet } from 'react-router'
import { cn } from '@/lib/utils'

const PRIMARY_NAV = [
  { to: '/', label: "Today's Priorities", end: true },
  { to: '/universe', label: 'Universe Explorer' },
  { to: '/ticker', label: 'Ticker 360' },
  { to: '/compare', label: 'Compare' },
]

const SECONDARY_NAV = [{ to: '/scans', label: 'Recent Scans' }]

function NavItem({ to, label, end }: { to: string; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          'block rounded-md px-3 py-2 text-sm font-medium transition-colors',
          isActive
            ? 'bg-secondary text-secondary-foreground'
            : 'text-muted-foreground hover:bg-muted hover:text-foreground',
        )
      }
    >
      {label}
    </NavLink>
  )
}

// A persistent sidebar workspace switcher rather than one long stacked
// page — each item is a distinct destination (a home briefing, a
// drill-down table, a ticker profile, a comparison tool), not a section
// of the same document. Real routes (not in-memory tab state) so a
// ticker can be linked to directly from anywhere it appears.
export function AppLayout() {
  return (
    <div className="flex min-h-screen">
      <nav className="flex w-56 shrink-0 flex-col border-r border-border p-4">
        <div className="mb-4 px-3 text-lg font-semibold text-foreground">Quant Hub</div>
        <div className="space-y-1">
          {PRIMARY_NAV.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </div>
        <div className="mt-6 space-y-1 border-t border-border pt-4">
          {SECONDARY_NAV.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </div>
      </nav>
      <main className="min-w-0 flex-1 overflow-auto p-8">
        <Outlet />
      </main>
    </div>
  )
}
