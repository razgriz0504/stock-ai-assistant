import { Fragment, useState, useEffect, useMemo } from 'react'
import { Card, CardHeader, Button, Badge } from '@/components/ui'
import { Tabs } from '@/components/ui'
import { useVcpStore } from '@/stores/vcpStore'
import type { VcpScanResult, VcpScanRun } from '@/stores/vcpStore'
import VcpChart from '@/components/charts/VcpChart'
import { getCnSector } from '@/data/cnNames'

// ═══════════════════════════════════════════════════════════════
// 公共：状态排序与样式映射
// ═══════════════════════════════════════════════════════════════
const STATUS_ORDER: Record<string, number> = {
  breakout: 0,
  forming: 1,
  extended: 2,
  failed: 3,
}

const STATUS_LABEL: Record<string, string> = {
  breakout: '突破',
  forming: '构筑中',
  extended: '已延伸',
  failed: '失败',
}

const STATUS_BADGE: Record<string, 'default' | 'success' | 'danger' | 'warning' | 'copper'> = {
  breakout: 'success',
  forming: 'warning',
  extended: 'copper',
  failed: 'danger',
}

// ═══════════════════════════════════════════════════════════════
// 顶层页面：Tab 切换（默认进入扫描结果）
// ═══════════════════════════════════════════════════════════════
export default function VcpMonitorPage() {
  const [activeTab, setActiveTab] = useState('results')

  const tabs = [
    { id: 'results', label: '扫描结果' },
    { id: 'watchlist', label: '监控列表' },
    { id: 'alerts', label: '告警历史' },
  ]

  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          VCP Monitor
        </span>
        <h1 className="page-title">VCP <span className="text-copper">监控</span></h1>
        <p className="text-sm text-gray-500 mt-2">Volatility Contraction Pattern — 波动收缩形态入场监控</p>
      </div>

      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      <div className="mt-6">
        {activeTab === 'results' && <ResultsTab />}
        {activeTab === 'watchlist' && <WatchlistTab />}
        {activeTab === 'alerts' && <AlertsTab />}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// 主页：扫描结果（标的中心化）
// ═══════════════════════════════════════════════════════════════
function ResultsTab() {
  const {
    runs, results, watchlist, activeDetail, loading, scanning,
    fetchRuns, fetchResults, fetchDetail, fetchWatchlist,
    startScan, seedFromSepa, addSymbol,
  } = useVcpStore()

  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [onlyWatchlist, setOnlyWatchlist] = useState(false)
  const [newSymbol, setNewSymbol] = useState('')
  const [toast, setToast] = useState('')

  // 初次进入：拉 runs + watchlist
  useEffect(() => {
    fetchRuns()
    fetchWatchlist()
    // eslint-disable-next-line
  }, [])

  // runs 加载后自动选最新批次
  useEffect(() => {
    if (runs.length > 0 && selectedRunId === null) {
      const latest = runs[0]
      if (latest) {
        setSelectedRunId(latest.id)
        fetchResults(latest.id)
      }
    }
    // eslint-disable-next-line
  }, [runs])

  const flash = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  const handleSelectRun = (run: VcpScanRun) => {
    setSelectedRunId(run.id)
    fetchResults(run.id)
    setExpandedSymbol(null)
  }

  const handleExpand = (r: VcpScanResult) => {
    if (expandedSymbol === r.symbol) {
      setExpandedSymbol(null)
    } else {
      setExpandedSymbol(r.symbol)
      fetchDetail(r.symbol)
    }
  }

  const handleAddSymbol = async () => {
    const s = newSymbol.trim().toUpperCase()
    if (!s) return
    try {
      await addSymbol(s)
      setNewSymbol('')
      flash(`${s} 已加入监控`)
    } catch (e: any) {
      flash(`添加失败：${e?.response?.data?.detail || e?.message || '未知错误'}`)
    }
  }

  const handleScan = async () => {
    await startScan()
    await fetchRuns()
    flash('扫描完成，已切换到最新批次')
    // 让 runs 变化触发自动选最新
    setSelectedRunId(null)
  }

  const handleSeed = async () => {
    const added = await seedFromSepa()
    flash(`从 SEPA 导入 ${added} 只股票`)
  }

  // ── 过滤 + 排序 ──
  const watchlistSet = useMemo(
    () => new Set(watchlist.filter(w => w.enabled).map(w => w.symbol)),
    [watchlist],
  )

  const filteredSorted = useMemo(() => {
    let arr = [...results]
    if (statusFilter) arr = arr.filter(r => r.status === statusFilter)
    if (onlyWatchlist) arr = arr.filter(r => watchlistSet.has(r.symbol))
    arr.sort((a, b) => {
      const oa = STATUS_ORDER[a.status] ?? 9
      const ob = STATUS_ORDER[b.status] ?? 9
      if (oa !== ob) return oa - ob
      return (b.score || 0) - (a.score || 0)
    })
    return arr
  }, [results, statusFilter, onlyWatchlist, watchlistSet])

  // ── 状态摘要统计 ──
  const summary = useMemo(() => {
    const counts: Record<string, number> = { breakout: 0, forming: 0, extended: 0, failed: 0 }
    for (const r of results) {
      const cur = counts[r.status]
      if (cur !== undefined) counts[r.status] = cur + 1
    }
    return counts
  }, [results])

  const selectedRun = runs.find(r => r.id === selectedRunId)

  return (
    <div className="space-y-4">
      {/* ── 紧凑工具栏 ── */}
      <Card className="p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <Button size="sm" onClick={handleScan} disabled={scanning}>
            {scanning ? '扫描中...' : '立即扫描'}
          </Button>
          <Button size="sm" variant="secondary" onClick={handleSeed}>SEPA 种子</Button>
          <div className="h-5 w-px bg-cream-300 mx-1" />
          <input
            value={newSymbol}
            onChange={e => setNewSymbol(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleAddSymbol()}
            placeholder="代码 (如 NVDA)"
            className="px-2 py-1.5 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper w-32"
          />
          <Button size="sm" variant="ghost" onClick={handleAddSymbol}>+ 加入监控</Button>
          <div className="h-5 w-px bg-cream-300 mx-1" />
          <label className="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={onlyWatchlist}
              onChange={e => setOnlyWatchlist(e.target.checked)}
              className="w-3.5 h-3.5 accent-copper"
            />
            仅显示监控列表
          </label>
          {toast && <span className="text-xs text-green-600 ml-2">{toast}</span>}
          <div className="flex-1" />
          {/* 批次选择器 */}
          <select
            value={selectedRunId ?? ''}
            onChange={e => {
              const id = Number(e.target.value)
              const run = runs.find(r => r.id === id)
              if (run) handleSelectRun(run)
            }}
            className="px-2 py-1.5 text-xs border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
          >
            {runs.length === 0 && <option value="">暂无批次</option>}
            {runs.slice(0, 20).map(run => (
              <option key={run.id} value={run.id}>
                #{run.id} · 命中 {run.detected}/{run.total}
                {run.finished_at ? ` · ${new Date(run.finished_at).toLocaleDateString()}` : ''}
              </option>
            ))}
          </select>
        </div>
      </Card>

      {/* ── 状态摘要条（可点击过滤） ── */}
      {selectedRun && (
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <SummaryChip
            label="全部" count={results.length}
            active={statusFilter === null}
            onClick={() => setStatusFilter(null)}
            color="default"
          />
          <SummaryChip
            label="突破" count={summary.breakout}
            active={statusFilter === 'breakout'}
            onClick={() => setStatusFilter(statusFilter === 'breakout' ? null : 'breakout')}
            color="success"
          />
          <SummaryChip
            label="构筑中" count={summary.forming}
            active={statusFilter === 'forming'}
            onClick={() => setStatusFilter(statusFilter === 'forming' ? null : 'forming')}
            color="warning"
          />
          <SummaryChip
            label="已延伸" count={summary.extended}
            active={statusFilter === 'extended'}
            onClick={() => setStatusFilter(statusFilter === 'extended' ? null : 'extended')}
            color="copper"
          />
          <SummaryChip
            label="失败" count={summary.failed}
            active={statusFilter === 'failed'}
            onClick={() => setStatusFilter(statusFilter === 'failed' ? null : 'failed')}
            color="danger"
          />
          <div className="flex-1" />
          <span className="text-gray-400">
            批次 #{selectedRun.id} · {selectedRun.finished_at ? new Date(selectedRun.finished_at).toLocaleString() : '进行中'}
          </span>
        </div>
      )}

      {/* ── 主表 ── */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cream-200 text-xs text-gray-500">
                <th className="px-3 py-2 text-left">代码</th>
                <th className="px-3 py-2 text-left">板块</th>
                <th className="px-3 py-2 text-left">状态</th>
                <th className="px-3 py-2 text-right">评分</th>
                <th className="px-3 py-2 text-right">Pivot</th>
                <th className="px-3 py-2 text-right">距 Pivot</th>
                <th className="px-3 py-2 text-right">收缩链</th>
                <th className="px-3 py-2 text-right">RS</th>
                <th className="px-3 py-2 text-right">最后告警</th>
              </tr>
            </thead>
            <tbody>
              {filteredSorted.map(r => (
                <ResultRow
                  key={r.id}
                  r={r}
                  inWatchlist={watchlistSet.has(r.symbol)}
                  expanded={expandedSymbol === r.symbol}
                  onExpand={() => handleExpand(r)}
                  activeDetail={activeDetail}
                  loading={loading}
                />
              ))}
              {filteredSorted.length === 0 && !loading && (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-gray-400">
                    {results.length === 0 ? '该批次无 VCP 检测结果' : '当前过滤条件下无结果'}
                  </td>
                </tr>
              )}
              {loading && results.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-gray-400">加载中...</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

// ── 摘要 Chip ──
function SummaryChip({
  label, count, active, onClick, color,
}: {
  label: string
  count: number
  active: boolean
  onClick: () => void
  color: 'default' | 'success' | 'danger' | 'warning' | 'copper'
}) {
  const colorMap: Record<string, string> = {
    default: 'border-cream-300 text-gray-600',
    success: 'border-green-300 text-green-700',
    danger: 'border-red-300 text-red-600',
    warning: 'border-amber-300 text-amber-700',
    copper: 'border-copper/50 text-copper',
  }
  const activeMap: Record<string, string> = {
    default: 'bg-cream-200',
    success: 'bg-green-50',
    danger: 'bg-red-50',
    warning: 'bg-amber-50',
    copper: 'bg-orange-50',
  }
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full border transition-all flex items-center gap-1.5 ${colorMap[color]} ${active ? activeMap[color] : 'bg-white hover:bg-cream-50'}`}
    >
      <span>{label}</span>
      <span className="font-mono font-semibold">{count}</span>
    </button>
  )
}

// ── 主表行（含展开图表） ──
function ResultRow({
  r, inWatchlist, expanded, onExpand, activeDetail, loading,
}: {
  r: VcpScanResult
  inWatchlist: boolean
  expanded: boolean
  onExpand: () => void
  activeDetail: any
  loading: boolean
}) {
  // 距 Pivot 颜色：>0 红、<0 绿，绝对值越大颜色越饱和
  const distClass = (d: number | null): string => {
    if (d === null) return 'text-gray-400'
    if (d > 5) return 'text-red-600 font-semibold'
    if (d > 0) return 'text-red-500'
    if (d > -3) return 'text-gray-600'
    return 'text-green-600'
  }

  const scoreClass = (s: number): string => {
    if (s >= 80) return 'text-copper font-semibold'
    if (s >= 60) return 'text-gray-700'
    return 'text-gray-400'
  }

  return (
    <Fragment>
      <tr
        className={`border-b border-cream-100 cursor-pointer ${expanded ? 'bg-cream-50' : 'hover:bg-cream-50'}`}
        onClick={onExpand}
      >
        <td className="px-3 py-2">
          <div className="flex items-center gap-1.5">
            <span className="font-medium">{r.symbol}</span>
            {inWatchlist && <span className="text-[9px] text-copper" title="在监控列表中">●</span>}
          </div>
        </td>
        <td className="px-3 py-2 text-xs text-gray-500">{getCnSector(r.sector) || '-'}</td>
        <td className="px-3 py-2">
          <Badge variant={STATUS_BADGE[r.status] || 'default'}>
            {STATUS_LABEL[r.status] || r.status}
          </Badge>
        </td>
        <td className={`px-3 py-2 text-right font-mono ${scoreClass(r.score)}`}>{r.score}</td>
        <td className="px-3 py-2 text-right font-mono text-sm">
          {r.pivot_price ? `$${r.pivot_price.toFixed(2)}` : '-'}
        </td>
        <td className={`px-3 py-2 text-right font-mono text-sm ${distClass(r.distance_pct)}`}>
          {r.distance_pct !== null && r.distance_pct !== undefined
            ? `${r.distance_pct > 0 ? '+' : ''}${r.distance_pct.toFixed(2)}%`
            : '-'}
        </td>
        <td className="px-3 py-2 text-right text-xs text-gray-500 whitespace-nowrap">
          {r.contractions.map(c => `${c.depth_pct}%`).join(' → ') || '-'}
        </td>
        <td className="px-3 py-2 text-right font-mono text-sm">
          {r.rs_percentile !== null && r.rs_percentile !== undefined ? r.rs_percentile.toFixed(0) : '-'}
        </td>
        <td className="px-3 py-2 text-right text-xs text-gray-400 whitespace-nowrap">
          {r.last_alert_at ? new Date(r.last_alert_at).toLocaleDateString() : '-'}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={9} className="p-4 bg-cream-50 border-b border-cream-200">
            {loading ? (
              <div className="text-center py-8 text-gray-400 text-sm">加载图表中...</div>
            ) : activeDetail ? (
              <VcpChart detail={activeDetail} />
            ) : (
              <div className="text-center py-8 text-gray-400 text-sm">无数据</div>
            )}
          </td>
        </tr>
      )}
    </Fragment>
  )
}

// ═══════════════════════════════════════════════════════════════
// Watchlist Tab（精简：移除"立即扫描"，仅保留标的池管理）
// ═══════════════════════════════════════════════════════════════
function WatchlistTab() {
  const { watchlist, fetchWatchlist, addSymbol, removeSymbol, seedFromSepa } = useVcpStore()
  const [newSymbol, setNewSymbol] = useState('')
  const [toast, setToast] = useState('')

  useEffect(() => { fetchWatchlist() }, []) // eslint-disable-line

  const flash = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  const handleAdd = async () => {
    const s = newSymbol.trim().toUpperCase()
    if (!s) return
    try {
      await addSymbol(s)
      setNewSymbol('')
      flash(`${s} 已加入`)
    } catch (e: any) {
      flash(`添加失败：${e?.response?.data?.detail || e?.message || '未知错误'}`)
    }
  }

  const handleSeed = async () => {
    const added = await seedFromSepa()
    flash(`从 SEPA 导入 ${added} 只`)
  }

  const enabledItems = watchlist.filter(w => w.enabled)
  const disabledItems = watchlist.filter(w => !w.enabled)

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <input
            value={newSymbol}
            onChange={e => setNewSymbol(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            placeholder="输入股票代码 (如 NVDA)"
            className="px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper w-48"
          />
          <Button size="sm" onClick={handleAdd}>添加</Button>
          <Button size="sm" variant="secondary" onClick={handleSeed}>从 SEPA 种子</Button>
          {toast && <span className="text-xs text-green-600 ml-2">{toast}</span>}
          <div className="flex-1" />
          <span className="text-xs text-gray-500">
            启用 {enabledItems.length} · 已禁用 {disabledItems.length}
          </span>
        </div>
      </Card>

      <Card>
        <CardHeader title={`监控列表 (${enabledItems.length})`} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cream-200 text-xs text-gray-500">
                <th className="px-3 py-2 text-left">代码</th>
                <th className="px-3 py-2 text-left">来源</th>
                <th className="px-3 py-2 text-left">备注</th>
                <th className="px-3 py-2 text-left">添加时间</th>
                <th className="px-3 py-2 text-left">最后告警</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {enabledItems.map(item => (
                <tr key={item.id} className="border-b border-cream-100 hover:bg-cream-50">
                  <td className="px-3 py-2 font-medium">{item.symbol}</td>
                  <td className="px-3 py-2">
                    <Badge variant={item.source === 'auto' ? 'default' : 'copper'}>
                      {item.source === 'auto' ? '自动' : '手动'}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-gray-500 text-xs">{item.note || '-'}</td>
                  <td className="px-3 py-2 text-xs text-gray-400">
                    {item.created_at ? new Date(item.created_at).toLocaleDateString() : '-'}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-400">
                    {item.last_triggered_at ? new Date(item.last_triggered_at).toLocaleDateString() : '-'}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => removeSymbol(item.id)}
                      className="text-gray-400 hover:text-red-500 text-xs"
                    >
                      移除
                    </button>
                  </td>
                </tr>
              ))}
              {enabledItems.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-8 text-center text-gray-400 text-sm">
                    暂无监控标的，请添加或从 SEPA 导入
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// Alerts Tab（保留原样）
// ═══════════════════════════════════════════════════════════════
function AlertsTab() {
  const { alerts, fetchAlerts } = useVcpStore()

  useEffect(() => { fetchAlerts() }, []) // eslint-disable-line

  return (
    <Card>
      <CardHeader title="告警历史" />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-cream-200 text-xs text-gray-500">
              <th className="px-3 py-2 text-left">时间</th>
              <th className="px-3 py-2 text-left">代码</th>
              <th className="px-3 py-2 text-left">类型</th>
              <th className="px-3 py-2 text-right">Pivot</th>
              <th className="px-3 py-2 text-right">量比</th>
              <th className="px-3 py-2 text-center">飞书</th>
              <th className="px-3 py-2 text-center">备注</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map(a => (
              <tr key={a.id} className="border-b border-cream-100">
                <td className="px-3 py-2 text-xs text-gray-500">
                  {a.alerted_at ? new Date(a.alerted_at).toLocaleString() : '-'}
                </td>
                <td className="px-3 py-2 font-medium">{a.symbol}</td>
                <td className="px-3 py-2">
                  <Badge variant="default">突破</Badge>
                </td>
                <td className="px-3 py-2 text-right font-mono">
                  {a.pivot_price ? `$${a.pivot_price.toFixed(2)}` : '-'}
                </td>
                <td className="px-3 py-2 text-right font-mono">
                  {a.volume_ratio ? `${a.volume_ratio.toFixed(2)}x` : '-'}
                </td>
                <td className="px-3 py-2 text-center">
                  {a.sent_feishu ? '✓' : '✗'}
                </td>
                <td className="px-3 py-2 text-center text-xs text-gray-400">
                  {a.prior_failed ? '二次突破' : ''}
                </td>
              </tr>
            ))}
            {alerts.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-gray-400">暂无告警记录</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
