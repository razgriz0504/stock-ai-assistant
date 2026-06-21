import { useState, useEffect } from 'react'
import { Card, CardHeader, Button, Badge } from '@/components/ui'
import { Tabs } from '@/components/ui'
import { useVcpStore } from '@/stores/vcpStore'
import type { VcpScanResult, VcpScanRun } from '@/stores/vcpStore'
import VcpChart from '@/components/charts/VcpChart'

export default function VcpMonitorPage() {
  const [activeTab, setActiveTab] = useState('watchlist')

  const tabs = [
    { id: 'watchlist', label: '监控列表' },
    { id: 'results', label: '扫描结果' },
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
        <p className="text-sm text-gray-500 mt-2">Volatility Contraction Pattern - 波动收缩形态入场监控</p>
      </div>

      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      <div className="mt-6">
        {activeTab === 'watchlist' && <WatchlistTab />}
        {activeTab === 'results' && <ResultsTab />}
        {activeTab === 'alerts' && <AlertsTab />}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// Watchlist Tab
// ═══════════════════════════════════════════════════════════════
function WatchlistTab() {
  const { watchlist, fetchWatchlist, addSymbol, removeSymbol, startScan, scanning, seedFromSepa } = useVcpStore()
  const [newSymbol, setNewSymbol] = useState('')
  const [seedMsg, setSeedMsg] = useState('')

  useEffect(() => { fetchWatchlist() }, []) // eslint-disable-line

  const handleAdd = async () => {
    if (!newSymbol.trim()) return
    await addSymbol(newSymbol.trim())
    setNewSymbol('')
  }

  const handleSeed = async () => {
    const added = await seedFromSepa()
    setSeedMsg(`已从 SEPA 结果导入 ${added} 只股票`)
    setTimeout(() => setSeedMsg(''), 3000)
  }

  const enabledItems = watchlist.filter(w => w.enabled)

  return (
    <div className="space-y-4">
      {/* Actions */}
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
          <Button size="sm" variant="secondary" onClick={startScan} disabled={scanning}>
            {scanning ? '扫描中...' : '立即扫描'}
          </Button>
          {seedMsg && <span className="text-xs text-green-600">{seedMsg}</span>}
        </div>
      </Card>

      {/* Watchlist Table */}
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
                <th className="px-3 py-2 text-left">最近信号</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {enabledItems.map(item => (
                <tr key={item.id} className="border-b border-cream-100 hover:bg-cream-50">
                  <td className="px-3 py-2 font-medium">{item.symbol}</td>
                  <td className="px-3 py-2">
                    <Badge variant={item.source === 'auto' ? 'default' : 'secondary'}>
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
                  <td className="px-3 py-2">
                    <button
                      onClick={() => removeSymbol(item.id)}
                      className="text-gray-400 hover:text-danger text-xs"
                    >移除</button>
                  </td>
                </tr>
              ))}
              {enabledItems.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-8 text-center text-gray-400 text-sm">暂无监控标的，请添加或从 SEPA 导入</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// Results Tab
// ═══════════════════════════════════════════════════════════════
function ResultsTab() {
  const { runs, results, fetchRuns, fetchResults, fetchDetail, activeDetail, loading } = useVcpStore()
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null)

  useEffect(() => { fetchRuns() }, []) // eslint-disable-line

  const handleSelectRun = (run: VcpScanRun) => {
    setSelectedRunId(run.id)
    fetchResults(run.id)
    setExpandedSymbol(null)
  }

  const handleExpand = (result: VcpScanResult) => {
    if (expandedSymbol === result.symbol) {
      setExpandedSymbol(null)
    } else {
      setExpandedSymbol(result.symbol)
      fetchDetail(result.symbol)
    }
  }

  const statusColor = (status: string): "default" | "secondary" | "destructive" => {
    if (status === 'breakout') return 'default'
    if (status === 'failed') return 'destructive'
    return 'secondary'
  }

  return (
    <div className="space-y-4">
      {/* Run selector */}
      <Card className="p-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium">选择扫描批次:</span>
          {runs.slice(0, 10).map(run => (
            <button
              key={run.id}
              onClick={() => handleSelectRun(run)}
              className={`px-3 py-1 text-xs rounded-md border transition-all ${
                selectedRunId === run.id
                  ? 'border-copper bg-orange-50 text-copper'
                  : 'border-cream-300 hover:border-copper/50'
              }`}
            >
              #{run.id} ({run.detected}/{run.total})
            </button>
          ))}
          {runs.length === 0 && <span className="text-xs text-gray-400">暂无扫描记录</span>}
        </div>
      </Card>

      {/* Results table */}
      {selectedRunId && (
        <Card>
          <CardHeader title={`扫描结果 (${results.length} 只检测到 VCP)`} />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-cream-200 text-xs text-gray-500">
                  <th className="px-3 py-2 text-left">代码</th>
                  <th className="px-3 py-2 text-left">状态</th>
                  <th className="px-3 py-2 text-right">评分</th>
                  <th className="px-3 py-2 text-right">Pivot</th>
                  <th className="px-3 py-2 text-right">收缩</th>
                  <th className="px-3 py-2 text-right">RS</th>
                </tr>
              </thead>
              <tbody>
                {results.map(r => (
                  <>
                    <tr
                      key={r.id}
                      className="border-b border-cream-100 hover:bg-cream-50 cursor-pointer"
                      onClick={() => handleExpand(r)}
                    >
                      <td className="px-3 py-2 font-medium">{r.symbol}</td>
                      <td className="px-3 py-2">
                        <Badge variant={statusColor(r.status)}>{r.status}</Badge>
                      </td>
                      <td className="px-3 py-2 text-right font-mono">{r.score}</td>
                      <td className="px-3 py-2 text-right font-mono">
                        {r.pivot_price ? `$${r.pivot_price.toFixed(2)}` : '-'}
                      </td>
                      <td className="px-3 py-2 text-right text-xs text-gray-500">
                        {r.contractions.map(c => `${c.depth_pct}%`).join(' → ')}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {r.rs_percentile ? r.rs_percentile.toFixed(0) : '-'}
                      </td>
                    </tr>
                    {expandedSymbol === r.symbol && (
                      <tr key={`${r.id}-chart`}>
                        <td colSpan={6} className="p-4 bg-cream-50">
                          {loading ? (
                            <div className="text-center py-8 text-gray-400">加载图表中...</div>
                          ) : activeDetail ? (
                            <VcpChart detail={activeDetail} />
                          ) : (
                            <div className="text-center py-8 text-gray-400">无数据</div>
                          )}
                        </td>
                      </tr>
                    )}
                  </>
                ))}
                {results.length === 0 && !loading && (
                  <tr><td colSpan={6} className="px-3 py-8 text-center text-gray-400">该批次无 VCP 检测结果</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// Alerts Tab
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
              <tr><td colSpan={7} className="px-3 py-8 text-center text-gray-400">暂无告警记录</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
