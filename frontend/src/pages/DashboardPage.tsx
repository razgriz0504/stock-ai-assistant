import { useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardHeader, Badge, Button } from '@/components/ui'
import { useDashboardStore, type DashAlert, type DashSectorItem, type DashTopStock } from '@/stores/dashboardStore'
import { getCnName, getCnSector } from '@/data/cnNames'

// ────────────────────────────────────────────────────────────────
// 工具
// ────────────────────────────────────────────────────────────────

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

function pctClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'text-gray-400'
  return v >= 0 ? 'text-success' : 'text-danger'
}

function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return `$${v.toFixed(2)}`
}

function relativeTime(iso?: string | null): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (!t) return '—'
  const diff = Date.now() - t
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  return `${d} 天前`
}

const flowLabel: Record<string, { text: string; cls: string }> = {
  strong_inflow: { text: '强流入', cls: 'text-success font-semibold' },
  inflow: { text: '流入', cls: 'text-success' },
  neutral: { text: '中性', cls: 'text-gray-400' },
  outflow: { text: '流出', cls: 'text-danger' },
  strong_outflow: { text: '强流出', cls: 'text-danger font-semibold' },
}

// ────────────────────────────────────────────────────────────────
// 子组件
// ────────────────────────────────────────────────────────────────

function HeroHeader({ generatedAt, loading, onRefresh }: { generatedAt?: string; loading: boolean; onRefresh: () => void }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          Morning Briefing
        </span>
        <h1 className="page-title">
          投研<span className="text-copper">工作台</span>
        </h1>
        <p className="text-sm text-gray-500 mt-2">
          {generatedAt ? `数据更新于 ${relativeTime(generatedAt)}` : '美股 AI 投研日报与监控聚合'}
        </p>
      </div>
      <Button variant="secondary" size="sm" onClick={onRefresh} disabled={loading}>
        {loading ? '刷新中…' : '刷新数据'}
      </Button>
    </div>
  )
}

function AlertList({ alerts }: { alerts: DashAlert[] }) {
  if (alerts.length === 0) {
    return (
      <Card>
        <CardHeader title="今日提醒" label="ALERTS" description="暂无重要事件,继续保持关注" />
        <div className="text-sm text-gray-400 py-2">😌 一切平静,可以专心研究</div>
      </Card>
    )
  }
  const levelMap = {
    info: 'default',
    success: 'success',
    warn: 'warning',
    danger: 'danger',
  } as const
  return (
    <Card>
      <CardHeader title="今日提醒" label="ALERTS" description={`共 ${alerts.length} 条事件`} />
      <ul className="space-y-3">
        {alerts.map((a, i) => (
          <li key={i}>
            <Link
              to={a.link}
              className="flex items-start gap-3 p-3 rounded-md border border-cream-200 hover:border-copper/40 hover:bg-cream-50 transition-colors"
            >
              <Badge variant={levelMap[a.level] || 'default'}>{a.type}</Badge>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-gray-900">{a.title}</div>
                <div className="text-xs text-gray-500 mt-0.5">{a.desc}</div>
              </div>
              <span className="text-copper text-sm">›</span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function SectorSpotlight({ gainers, losers }: { gainers: DashSectorItem[]; losers: DashSectorItem[] }) {
  const renderRow = (s: DashSectorItem) => (
    <li key={s.symbol} className="flex items-center justify-between py-2 border-b border-cream-200 last:border-0 text-sm">
      <div className="min-w-0">
        <span className="font-mono font-semibold mr-2">{s.symbol}</span>
        <span className="text-gray-600">{s.name}</span>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <span className={`font-mono text-xs ${pctClass(s.chg_5d)}`}>{fmtPct(s.chg_5d)}</span>
        {s.flow_direction && (
          <span className={`text-xs ${flowLabel[s.flow_direction]?.cls || 'text-gray-400'}`}>
            {flowLabel[s.flow_direction]?.text || s.flow_direction}
          </span>
        )}
      </div>
    </li>
  )
  return (
    <Card>
      <CardHeader
        title="板块强度·近 5 日"
        label="SECTOR SPOTLIGHT"
        action={
          <Link to="/sector-strength" className="text-xs font-mono text-copper hover:underline">
            查看雷达 →
          </Link>
        }
      />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="text-xs font-mono text-success mb-2">领涨 TOP 3</div>
          {gainers.length === 0 ? (
            <div className="text-xs text-gray-400 py-2">暂无数据</div>
          ) : (
            <ul>{gainers.map(renderRow)}</ul>
          )}
        </div>
        <div>
          <div className="text-xs font-mono text-danger mb-2">领跌 TOP 3</div>
          {losers.length === 0 ? (
            <div className="text-xs text-gray-400 py-2">暂无数据</div>
          ) : (
            <ul>{losers.map(renderRow)}</ul>
          )}
        </div>
      </div>
    </Card>
  )
}

function ScreenerCard({
  recentRuns,
  topStocks,
  latestId,
}: {
  recentRuns: number
  topStocks: DashTopStock[]
  latestId: number | null
}) {
  return (
    <Card>
      <CardHeader
        title="最新选股结果"
        label="SCREENER"
        description={recentRuns > 0 ? `近 24h 共运行 ${recentRuns} 次` : '近 24h 未运行'}
        action={
          <Link to="/screener" className="text-xs font-mono text-copper hover:underline">
            打开选股器 →
          </Link>
        }
      />
      {topStocks.length === 0 ? (
        <div className="text-sm text-gray-400 py-4 text-center">
          暂无选股结果 ·{' '}
          <Link to="/screener" className="text-copper hover:underline">
            立即开始选股
          </Link>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs font-mono text-gray-500 border-b border-cream-200">
                <th className="py-2 pr-2">代码</th>
                <th className="py-2 px-2">名称</th>
                <th className="py-2 px-2">板块</th>
                <th className="py-2 px-2 text-right">评分</th>
                <th className="py-2 px-2 text-right">现价</th>
                <th className="py-2 pl-2 text-right">涨跌</th>
              </tr>
            </thead>
            <tbody>
              {topStocks.map((s) => (
                <tr key={s.symbol} className="border-b border-cream-200 last:border-0 hover:bg-cream-50">
                  <td className="py-2 pr-2 font-mono font-semibold text-xs">{s.symbol}</td>
                  <td className="py-2 px-2 text-xs text-gray-600">{getCnName(s.symbol, s.name)}</td>
                  <td className="py-2 px-2 text-xs text-gray-500">{getCnSector(s.sector)}</td>
                  <td className="py-2 px-2 text-right">
                    <Badge variant={(s.score ?? 0) >= 4 ? 'success' : (s.score ?? 0) >= 3 ? 'warning' : 'default'}>
                      {s.score?.toFixed(1) || '-'}
                    </Badge>
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-xs">{fmtPrice(s.price)}</td>
                  <td className={`py-2 pl-2 text-right font-mono text-xs ${pctClass(s.change_pct)}`}>
                    {fmtPct(s.change_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {latestId && (
        <div className="mt-3 text-right">
          <Link to="/screener" className="text-xs font-mono text-gray-500 hover:text-copper">
            完整结果 (run #{latestId}) →
          </Link>
        </div>
      )}
    </Card>
  )
}

function XMonitorCard({
  total24h,
  distribution,
  topAssets,
  latestTweet,
}: {
  total24h: number
  distribution: { bullish: number; bearish: number; neutral: number }
  topAssets: { ticker: string; count: number }[]
  latestTweet: { username: string; text_zh: string; text: string; sentiment: string; created_at: string } | null
}) {
  return (
    <Card>
      <CardHeader
        title="X 舆情·近 24h"
        label="X SENTIMENT"
        description={`共 ${total24h} 条推文`}
        action={
          <Link to="/x-monitor" className="text-xs font-mono text-copper hover:underline">
            打开 X 监控 →
          </Link>
        }
      />
      {total24h === 0 ? (
        <div className="text-sm text-gray-400 py-4 text-center">近 24h 暂无新推文</div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="text-center p-3 rounded bg-green-50">
              <div className="text-xl font-bold text-success">{distribution.bullish}</div>
              <div className="text-[10px] font-mono text-success/80 mt-0.5">BULLISH</div>
            </div>
            <div className="text-center p-3 rounded bg-cream-100">
              <div className="text-xl font-bold text-gray-600">{distribution.neutral}</div>
              <div className="text-[10px] font-mono text-gray-500 mt-0.5">NEUTRAL</div>
            </div>
            <div className="text-center p-3 rounded bg-red-50">
              <div className="text-xl font-bold text-danger">{distribution.bearish}</div>
              <div className="text-[10px] font-mono text-danger/80 mt-0.5">BEARISH</div>
            </div>
          </div>
          {topAssets.length > 0 && (
            <div className="mb-3">
              <div className="text-xs font-mono text-gray-500 mb-2">热议标的</div>
              <div className="flex flex-wrap gap-2">
                {topAssets.map((a) => (
                  <span
                    key={a.ticker}
                    className="text-xs font-mono px-2 py-1 rounded bg-cream-100 border border-cream-200"
                  >
                    {a.ticker}
                    <span className="text-copper font-semibold ml-1">{a.count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
          {latestTweet && (
            <div className="mt-3 p-3 rounded border border-cream-200 bg-cream-50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold">@{latestTweet.username}</span>
                <span className="text-xs text-gray-400">{relativeTime(latestTweet.created_at)}</span>
              </div>
              <div className="text-sm text-gray-700 line-clamp-3">
                {latestTweet.text_zh || latestTweet.text}
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  )
}

function ReportCard({
  latest,
  isRunning,
}: {
  latest: { id: number; version: number; report_date: string | null; model_name: string; trigger: string } | null
  isRunning: boolean
}) {
  if (!latest) {
    return (
      <Card>
        <CardHeader title="投研周报" label="WEEKLY REPORT" description={isRunning ? '正在生成中…' : '暂无已完成周报'} />
        <Link to="/report-admin" className="text-sm text-copper hover:underline">
          前往管理页生成 →
        </Link>
      </Card>
    )
  }
  const dateStr = latest.report_date ? latest.report_date.slice(0, 10) : ''
  return (
    <Card>
      <CardHeader
        title="投研周报"
        label="WEEKLY REPORT"
        description={`v${latest.version} · ${dateStr}`}
        action={
          <Link to="/report" className="text-xs font-mono text-copper hover:underline">
            查看周报 →
          </Link>
        }
      />
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">模型</span>
          <span className="font-mono text-xs">{latest.model_name || '—'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">触发方式</span>
          <span className="font-mono text-xs">{latest.trigger === 'scheduled' ? '定时' : '手动'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">状态</span>
          <Badge variant={isRunning ? 'warning' : 'success'}>{isRunning ? '生成中' : '已完成'}</Badge>
        </div>
      </div>
    </Card>
  )
}

function WatchlistCard({ count, stocks }: { count: number; stocks: string[] }) {
  return (
    <Card>
      <CardHeader
        title="关注列表"
        label="WATCHLIST"
        description={`共 ${count} 只股票`}
        action={
          <Link to="/watchlist" className="text-xs font-mono text-copper hover:underline">
            管理 →
          </Link>
        }
      />
      {stocks.length === 0 ? (
        <div className="text-sm text-gray-400 py-2">
          暂无关注股票 ·{' '}
          <Link to="/watchlist" className="text-copper hover:underline">
            立即添加
          </Link>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {stocks.map((s) => (
            <span key={s} className="text-xs font-mono px-2 py-1 rounded bg-cream-100 border border-cream-200">
              {s}
              <span className="text-gray-400 ml-1">{getCnName(s) !== s ? getCnName(s) : ''}</span>
            </span>
          ))}
        </div>
      )}
    </Card>
  )
}

const QUICK_LINKS = [
  { path: '/screener', title: '选股器', desc: 'S&P 500 + Nasdaq 100 智能筛选', icon: '🔍', color: 'text-blue-600' },
  { path: '/sector-strength', title: '板块雷达', desc: '41 ETF 相对强度 & 资金流', icon: '📡', color: 'text-purple-600' },
  { path: '/backtest', title: '策略回测', desc: 'Python 策略回测引擎', icon: '📈', color: 'text-green-600' },
  { path: '/x-monitor', title: 'X 舆情', desc: '关键账号 AI 翻译 & 情绪分析', icon: '🐦', color: 'text-sky-500' },
  { path: '/chat', title: 'AI 对话', desc: '与 AI 交流市场观点', icon: '💬', color: 'text-amber-600' },
  { path: '/settings', title: '设置', desc: '模型与系统配置', icon: '⚙️', color: 'text-gray-600' },
]

function QuickLinks() {
  return (
    <div>
      <div className="section-label flex items-center gap-2 mb-4">
        <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
        Quick Access
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {QUICK_LINKS.map((mod) => (
          <Link key={mod.path} to={mod.path} className="block group">
            <Card hover className="h-full !p-4">
              <div className={`text-xl mb-2 ${mod.color}`}>{mod.icon}</div>
              <h3 className="font-heading text-sm font-semibold mb-0.5 group-hover:text-copper transition-colors">
                {mod.title}
              </h3>
              <p className="text-[11px] text-gray-500 leading-snug">{mod.desc}</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────
// 主页面
// ────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { data, loading, error, fetchSummary } = useDashboardStore()

  useEffect(() => {
    fetchSummary()
    // 5 分钟自动后台刷新
    const t = setInterval(() => fetchSummary({ silent: true }), 5 * 60 * 1000)
    return () => clearInterval(t)
  }, [fetchSummary])

  const sectorData = useMemo(
    () => ({
      gainers: data?.sector?.top_gainers || [],
      losers: data?.sector?.top_losers || [],
    }),
    [data],
  )

  return (
    <div>
      <HeroHeader generatedAt={data?.generated_at} loading={loading} onRefresh={() => fetchSummary()} />

      {error && (
        <div className="mb-6 p-3 rounded border border-danger/30 bg-red-50 text-sm text-danger">
          数据加载失败:{error}
        </div>
      )}

      {!data && loading && (
        <div className="flex items-center justify-center py-20">
          <div className="w-6 h-6 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            <div className="lg:col-span-2">
              <AlertList alerts={data.alerts} />
            </div>
            <ReportCard latest={data.report.latest} isRunning={data.report.is_running} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <SectorSpotlight gainers={sectorData.gainers} losers={sectorData.losers} />
            <XMonitorCard
              total24h={data.x_monitor.total_24h}
              distribution={data.x_monitor.sentiment_distribution}
              topAssets={data.x_monitor.top_assets}
              latestTweet={data.x_monitor.latest_tweet}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
            <div className="lg:col-span-2">
              <ScreenerCard
                recentRuns={data.screener.recent_24h_runs}
                topStocks={data.screener.top_stocks}
                latestId={data.screener.latest_completed_id}
              />
            </div>
            <WatchlistCard count={data.watchlist.count} stocks={data.watchlist.stocks} />
          </div>

          <QuickLinks />
        </>
      )}
    </div>
  )
}
