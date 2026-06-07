import { Link } from 'react-router-dom'
import { Card } from '@/components/ui'

const modules = [
  { path: '/report', title: '投研周报', desc: '最新周报洞察与市场评分', icon: '📋', color: 'text-copper' },
  { path: '/screener', title: '选股器', desc: 'S&P 500 + Nasdaq 100 智能筛选', icon: '🔍', color: 'text-blue-600' },
  { path: '/sector-strength', title: '板块强度雷达', desc: '41 ETF 相对强度 & 资金流向', icon: '📡', color: 'text-purple-600' },
  { path: '/backtest', title: '策略回测', desc: 'Python 策略回测引擎', icon: '📈', color: 'text-green-600' },
  { path: '/x-monitor', title: 'X 舆情监控', desc: '关键账号 AI 翻译 & 情绪分析', icon: '🐦', color: 'text-sky-500' },
  { path: '/chat', title: 'AI 对话', desc: '与 AI 交流市场观点', icon: '💬', color: 'text-amber-600' },
]

export default function DashboardPage() {
  return (
    <div>
      {/* Header */}
      <div className="mb-10">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          Overview
        </span>
        <h1 className="page-title">
          Stock AI <span className="text-copper">Assistant</span>
        </h1>
        <p className="text-sm text-gray-500 mt-2">美股 AI 投研工作台</p>
      </div>

      {/* Module Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {modules.map((mod) => (
          <Link key={mod.path} to={mod.path} className="block group">
            <Card hover className="h-full">
              <div className={`text-2xl mb-3 ${mod.color}`}>{mod.icon}</div>
              <h3 className="font-heading text-base font-semibold mb-1 group-hover:text-copper transition-colors">
                {mod.title}
              </h3>
              <p className="text-sm text-gray-500">{mod.desc}</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
