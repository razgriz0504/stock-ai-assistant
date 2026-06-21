import { NavLink, useLocation } from 'react-router-dom'

interface NavItem {
  path: string
  label: string
  icon: string
}

const navItems: NavItem[] = [
  { path: '/', label: '仪表盘', icon: '📊' },
  { path: '/report', label: '投研周报', icon: '📋' },
  { path: '/screener', label: '选股器', icon: '🔍' },
  { path: '/sector-strength', label: '板块雷达', icon: '📡' },
  { path: '/vcp-monitor', label: 'VCP 监控', icon: '📉' },
  { path: '/backtest', label: '策略回测', icon: '📈' },
  { path: '/x-monitor', label: 'X 舆情', icon: '🐦' },
  { path: '/watchlist', label: '关注列表', icon: '⭐' },
  { path: '/chat', label: 'AI 对话', icon: '💬' },
]

const bottomItems: NavItem[] = [
  { path: '/report-admin', label: '报告管理', icon: '⚙️' },
  { path: '/settings', label: '系统设置', icon: '🔧' },
]

export function Sidebar() {
  const location = useLocation()

  const linkClass = (path: string) => {
    const isActive = path === '/' 
      ? location.pathname === '/' 
      : location.pathname.startsWith(path)
    return `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm transition-all ${
      isActive
        ? 'bg-white/10 text-white font-medium'
        : 'text-gray-400 hover:text-white hover:bg-white/5'
    }`
  }

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-[220px] bg-sidebar flex flex-col z-50">
      {/* Logo */}
      <div className="px-5 py-6 border-b border-white/10">
        <h1 className="font-heading text-lg font-bold text-white tracking-tight">
          Stock AI
        </h1>
        <p className="text-xs text-gray-500 mt-0.5 font-mono">ASSISTANT v2.0</p>
      </div>

      {/* Main nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink key={item.path} to={item.path} className={linkClass(item.path)}>
            <span className="text-base w-5 text-center">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Bottom nav */}
      <div className="px-3 py-4 border-t border-white/10 space-y-1">
        {bottomItems.map((item) => (
          <NavLink key={item.path} to={item.path} className={linkClass(item.path)}>
            <span className="text-base w-5 text-center">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </div>
    </aside>
  )
}
