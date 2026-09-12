import { useState, type ComponentType } from 'react'
import { Columns3, History, LayoutDashboard, Menu, Search, Table2 } from 'lucide-react'
import { NavLink, Outlet } from 'react-router'
import { cn } from '@/lib/utils'

const PRIMARY_NAV = [
  { to: '/', label: "Today's Priorities", icon: LayoutDashboard, end: true },
  { to: '/universe', label: 'Universe Explorer', icon: Table2 },
  { to: '/ticker', label: 'Ticker 360', icon: Search },
  { to: '/compare', label: 'Compare', icon: Columns3 },
]

const SECONDARY_NAV = [{ to: '/scans', label: 'Recent Scans', icon: History }]

function NavItem({
  to,
  label,
  icon: Icon,
  end,
  mobileExpanded,
}: {
  to: string
  label: string
  icon: ComponentType<{ className?: string }>
  end?: boolean
  mobileExpanded: boolean
}) {
  return (
    <NavLink
      to={to}
      end={end}
      title={label}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-3 rounded-md py-2 text-sm font-medium transition-colors',
          mobileExpanded ? 'px-3' : 'px-2 md:px-3',
          isActive
            ? 'bg-secondary text-secondary-foreground'
            : 'text-muted-foreground hover:bg-muted hover:text-foreground',
        )
      }
    >
      <Icon className="size-5 shrink-0" />
      <span className={cn('truncate', mobileExpanded ? 'inline' : 'hidden md:inline')}>
        {label}
      </span>
    </NavLink>
  )
}

// A persistent sidebar workspace switcher rather than one long stacked
// page — each item is a distinct destination (a home briefing, a
// drill-down table, a ticker profile, a comparison tool), not a section
// of the same document. Real routes (not in-memory tab state) so a
// ticker can be linked to directly from anywhere it appears.
//
// Mobile: an icon-only rail, always visible and directly tappable — no
// drawer to open first. The hamburger only toggles whether labels are
// shown alongside the icons, it's not a gate on navigation (a slide-in
// drawer would cost an extra tap just to see the nav, worse for 5 flat
// destinations than a persistent icon rail). Desktop keeps the full
// labeled sidebar regardless of this toggle.
export function AppLayout() {
  const [mobileExpanded, setMobileExpanded] = useState(false)

  return (
    <div className="flex min-h-screen">
      <nav
        className={cn(
          'flex shrink-0 flex-col border-r border-border transition-[width] duration-150 md:w-56 md:p-4',
          mobileExpanded ? 'w-56 p-4' : 'w-14 p-2',
        )}
      >
        <div className="mb-4 flex items-center justify-between">
          <span
            className={cn(
              'truncate text-lg font-semibold text-foreground',
              mobileExpanded ? 'inline' : 'hidden md:inline',
            )}
          >
            Quant Hub
          </span>
          <button
            type="button"
            onClick={() => setMobileExpanded((v) => !v)}
            aria-label={mobileExpanded ? 'Collapse navigation labels' : 'Expand navigation labels'}
            aria-expanded={mobileExpanded}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground md:hidden"
          >
            <Menu className="size-5" />
          </button>
        </div>
        <div className="space-y-1">
          {PRIMARY_NAV.map((item) => (
            <NavItem key={item.to} {...item} mobileExpanded={mobileExpanded} />
          ))}
        </div>
        <div className="mt-6 space-y-1 border-t border-border pt-4">
          {SECONDARY_NAV.map((item) => (
            <NavItem key={item.to} {...item} mobileExpanded={mobileExpanded} />
          ))}
        </div>
      </nav>
      <main className="min-w-0 flex-1 overflow-auto p-4 md:p-8">
        <Outlet />
      </main>
    </div>
  )
}
