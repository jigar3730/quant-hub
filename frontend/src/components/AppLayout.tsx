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
  collapsed,
}: {
  to: string
  label: string
  icon: ComponentType<{ className?: string }>
  end?: boolean
  collapsed: boolean
}) {
  return (
    <NavLink
      to={to}
      end={end}
      title={label}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-3 rounded-md py-2 text-sm font-medium transition-colors',
          collapsed ? 'px-2' : 'px-3',
          isActive
            ? 'bg-secondary text-secondary-foreground'
            : 'text-muted-foreground hover:bg-muted hover:text-foreground',
        )
      }
    >
      <Icon className="size-5 shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </NavLink>
  )
}

// A single collapse toggle (an "app rail" when collapsed), the same on
// every screen size -- not a mobile-only fallback. Starting state differs
// sensibly by device (collapsed on a narrow viewport, expanded on a wide
// one) but from there it's a manual, per-session user choice either way,
// same as VS Code's activity bar or Slack's app rail: resizing the window
// doesn't fight a choice you already made.
function initialCollapsed(): boolean {
  if (typeof window === 'undefined') return false
  return !window.matchMedia('(min-width: 768px)').matches
}

// A persistent sidebar workspace switcher rather than one long stacked
// page — each item is a distinct destination (a home briefing, a
// drill-down table, a ticker profile, a comparison tool), not a section
// of the same document. Real routes (not in-memory tab state) so a
// ticker can be linked to directly from anywhere it appears.
export function AppLayout() {
  const [collapsed, setCollapsed] = useState(initialCollapsed)

  return (
    <div className="flex min-h-screen">
      <nav
        className={cn(
          'flex shrink-0 flex-col border-r border-border transition-[width] duration-150',
          collapsed ? 'w-14 p-2' : 'w-56 p-4',
        )}
      >
        <div className={cn('mb-4 flex items-center', collapsed ? 'justify-center' : 'justify-between')}>
          {!collapsed && (
            <span className="truncate text-lg font-semibold text-foreground">Quant Hub</span>
          )}
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-expanded={!collapsed}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Menu className="size-5" />
          </button>
        </div>
        <div className="space-y-1">
          {PRIMARY_NAV.map((item) => (
            <NavItem key={item.to} {...item} collapsed={collapsed} />
          ))}
        </div>
        <div className="mt-6 space-y-1 border-t border-border pt-4">
          {SECONDARY_NAV.map((item) => (
            <NavItem key={item.to} {...item} collapsed={collapsed} />
          ))}
        </div>
      </nav>
      <main className="min-w-0 flex-1 overflow-auto p-4 md:p-8">
        <Outlet />
      </main>
    </div>
  )
}
