import { useState, useEffect, useRef, useCallback } from 'react'
import { Card, CardHeader, Button, Badge, Input } from '@/components/ui'
import { Tabs } from '@/components/ui'
import { useScreenerStore, type ScreenerPreset } from '@/stores/screenerStore'

export default function ScreenerPage() {
  const [activeTab, setActiveTab] = useState('run')
  const store = useScreenerStore()

  // Load presets and runs on mount
  useEffect(() => {
    store.fetchPresets()
    store.fetchRuns()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const tabs = [
    { id: 'run', label: '运行选股' },
    { id: 'results', label: `结果 (${store.totalPassed})` },
    { id: 'history', label: '历史记录' },
    { id: 'schedule', label: '定时任务' },
  ]

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          Stock Screener
        </span>
        <h1 className="page-title">选<span className="text-copper">股器</span></h1>
      </div>

      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      <div className="mt-6">
        {activeTab === 'run' && <RunTab />}
        {activeTab === 'results' && <ResultsTab />}
        {activeTab === 'history' && <HistoryTab />}
        {activeTab === 'schedule' && <ScheduleTab />}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// Run Tab - Filter Panel + Code + Execute
// ═══════════════════════════════════════════════════════════════
function RunTab() {
  const {
    status, progress, errorMessage, filtersJson, customCode,
    presets, activePresetId,
    setFilters, setCustomCode, loadPreset, startRun, reset,
  } = useScreenerStore()

  const [presetName, setPresetName] = useState('')
  const { savePreset, deletePreset } = useScreenerStore()

  // Polling
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const { pollStatus, fetchResults } = useScreenerStore()

  const startPolling = useCallback(() => {
    if (pollingRef.current) return
    pollingRef.current = setInterval(async () => {
      const done = await pollStatus()
      if (done) {
        if (pollingRef.current) clearInterval(pollingRef.current)
        pollingRef.current = null
        await fetchResults()
      }
    }, 2000)
  }, [pollStatus, fetchResults])

  useEffect(() => {
    if (status === 'running') startPolling()
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [status, startPolling])

  const handleRun = async () => {
    await startRun()
    startPolling()
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Left: Presets */}
      <div className="lg:col-span-1">
        <Card>
          <CardHeader title="预设方案" description="保存和加载筛选配置" />
          <div className="mt-4 space-y-2 max-h-[300px] overflow-y-auto">
            {presets.map((p: ScreenerPreset) => (
              <div
                key={p.id}
                className={`flex items-center justify-between px-3 py-2 rounded-md cursor-pointer transition-all ${
                  activePresetId === p.id
                    ? 'bg-orange-50 border border-copper/20'
                    : 'hover:bg-cream-100'
                }`}
                onClick={() => loadPreset(p)}
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{p.name}</span>
                  {p.is_default && <Badge variant="copper">默认</Badge>}
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); deletePreset(p.id) }}
                  className="text-gray-400 hover:text-danger text-xs"
                >
                  ✕
                </button>
              </div>
            ))}
            {presets.length === 0 && (
              <p className="text-xs text-gray-400 py-4 text-center">暂无预设</p>
            )}
          </div>
          <div className="mt-4 pt-4 border-t border-cream-200 flex gap-2">
            <Input
              value={presetName}
              onChange={(e) => setPresetName(e.target.value)}
              placeholder="预设名称"
            />
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                if (presetName.trim()) {
                  savePreset(presetName.trim())
                  setPresetName('')
                }
              }}
            >
              保存
            </Button>
          </div>
        </Card>
      </div>

      {/* Right: Editor + Controls */}
      <div className="lg:col-span-2 space-y-6">
        {/* Status bar */}
        {status !== 'idle' && (
          <div className={`px-4 py-3 rounded-lg flex items-center gap-3 ${
            status === 'running' || status === 'pending'
              ? 'bg-orange-50 border border-copper/20'
              : status === 'success'
                ? 'bg-green-50 border border-green-200'
                : 'bg-red-50 border border-red-200'
          }`}>
            {(status === 'running' || status === 'pending') && (
              <div className="w-4 h-4 border-2 border-copper border-t-transparent rounded-full animate-spin" />
            )}
            <span className="text-sm font-medium">
              {status === 'pending' && '提交中...'}
              {status === 'running' && `正在执行 (${progress}%)`}
              {status === 'success' && '选股完成'}
              {status === 'failed' && `失败: ${errorMessage || '未知错误'}`}
            </span>
            {(status === 'success' || status === 'failed') && (
              <Button size="sm" variant="ghost" onClick={reset}>重置</Button>
            )}
          </div>
        )}

        {/* Filters JSON */}
        <Card>
          <CardHeader title="筛选条件" description="JSON 格式的过滤器配置" />
          <textarea
            value={filtersJson}
            onChange={(e) => setFilters(e.target.value)}
            rows={6}
            className="mt-3 w-full px-3 py-2 text-xs font-mono border border-cream-300 rounded-md bg-cream-50 focus:outline-none focus:border-copper resize-y"
            placeholder='{"min_market_cap": 1000000000, "min_pe": 5, "max_pe": 30}'
          />
        </Card>

        {/* Custom Code */}
        <Card>
          <CardHeader title="自定义代码" description="Python 代码用于高级筛选逻辑（可选）" />
          <textarea
            value={customCode}
            onChange={(e) => setCustomCode(e.target.value)}
            rows={10}
            className="mt-3 w-full px-3 py-2 text-xs font-mono border border-cream-300 rounded-md bg-cream-50 focus:outline-none focus:border-copper resize-y"
            placeholder={`# 自定义筛选逻辑\ndef custom_filter(stock):\n    # stock 包含: price, market_cap, pe_ratio, volume 等\n    return stock['pe_ratio'] < 20`}
          />
        </Card>

        {/* Run button */}
        <Button
          onClick={handleRun}
          disabled={status === 'running' || status === 'pending'}
          className="w-full"
        >
          {status === 'running' ? `执行中 (${progress}%)` : '开始选股'}
        </Button>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// Results Tab
// ═══════════════════════════════════════════════════════════════
function ResultsTab() {
  const { results, totalPassed, runId } = useScreenerStore()
  const [sortBy, setSortBy] = useState<string>('score')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  const sorted = [...results].sort((a, b) => {
    const aVal = (a as Record<string, unknown>)[sortBy] as number || 0
    const bVal = (b as Record<string, unknown>)[sortBy] as number || 0
    return sortOrder === 'desc' ? bVal - aVal : aVal - bVal
  })

  const toggleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')
    } else {
      setSortBy(field)
      setSortOrder('desc')
    }
  }

  const SortHeader = ({ field, label }: { field: string; label: string }) => (
    <th
      className="text-right px-3 py-2 font-mono text-[10px] uppercase text-gray-500 cursor-pointer hover:text-copper transition-colors"
      onClick={() => toggleSort(field)}
    >
      {label} {sortBy === field && (sortOrder === 'desc' ? '↓' : '↑')}
    </th>
  )

  if (!runId) {
    return (
      <Card>
        <p className="text-sm text-gray-400 text-center py-10">
          尚未执行选股。请在「运行选股」标签页启动。
        </p>
      </Card>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-500">
          共筛出 <span className="font-mono font-bold text-copper">{totalPassed}</span> 只股票
        </p>
      </div>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cream-300">
                <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">代码</th>
                <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">名称</th>
                <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">行业</th>
                <SortHeader field="score" label="评分" />
                <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">等级</th>
                <SortHeader field="price" label="价格" />
                <SortHeader field="change_pct" label="涨跌%" />
                <SortHeader field="pe_ratio" label="PE" />
                <SortHeader field="roe" label="ROE" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.symbol} className="border-b border-cream-200 hover:bg-cream-100 transition-colors">
                  <td className="px-3 py-2 font-mono font-semibold text-xs">{r.symbol}</td>
                  <td className="px-3 py-2 text-xs">{r.name}</td>
                  <td className="px-3 py-2 text-xs text-gray-500">{r.sector}</td>
                  <td className="px-3 py-2 text-right">
                    <Badge variant={r.score >= 70 ? 'success' : r.score >= 40 ? 'warning' : 'danger'}>
                      {r.score}
                    </Badge>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="copper">{r.rating || '-'}</Badge>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">${r.price?.toFixed(2)}</td>
                  <td className={`px-3 py-2 text-right font-mono text-xs font-medium ${r.change_pct >= 0 ? 'text-success' : 'text-danger'}`}>
                    {r.change_pct >= 0 ? '+' : ''}{r.change_pct?.toFixed(2)}%
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{r.pe_ratio?.toFixed(1)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{r.roe?.toFixed(1)}%</td>
                </tr>
              ))}
              {results.length === 0 && (
                <tr>
                  <td colSpan={9} className="text-center py-8 text-sm text-gray-400">暂无结果</td>
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
// History Tab
// ═══════════════════════════════════════════════════════════════
function HistoryTab() {
  const { runs, fetchRuns } = useScreenerStore()

  useEffect(() => { fetchRuns() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const statusColor = (s: string) => {
    if (s === 'completed') return 'success'
    if (s === 'failed') return 'danger'
    if (s === 'running') return 'warning'
    return 'default'
  }

  return (
    <Card>
      <CardHeader title="执行历史" description="最近 20 次选股记录" />
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-cream-300">
              <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">版本</th>
              <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">状态</th>
              <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">触发</th>
              <th className="text-right px-3 py-2 font-mono text-[10px] uppercase text-gray-500">总数</th>
              <th className="text-right px-3 py-2 font-mono text-[10px] uppercase text-gray-500">通过</th>
              <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">时间</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className="border-b border-cream-200">
                <td className="px-3 py-2 font-mono font-semibold text-xs">{r.version}</td>
                <td className="px-3 py-2">
                  <Badge variant={statusColor(r.status)}>{r.status}</Badge>
                </td>
                <td className="px-3 py-2 text-xs text-gray-500">{r.trigger}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{r.total_stocks || '-'}</td>
                <td className="px-3 py-2 text-right font-mono text-xs font-medium text-copper">{r.passed_stocks || '-'}</td>
                <td className="px-3 py-2 font-mono text-[10px] text-gray-400">
                  {r.started_at?.replace('T', ' ').slice(0, 16) || '-'}
                </td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr>
                <td colSpan={6} className="text-center py-8 text-sm text-gray-400">暂无记录</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

// ═══════════════════════════════════════════════════════════════
// Schedule Tab
// ═══════════════════════════════════════════════════════════════
function ScheduleTab() {
  const [form, setForm] = useState({
    schedule_enabled: false,
    schedule_frequency: 'daily',
    schedule_day_of_week: 'mon-fri',
    schedule_hour: 16,
    schedule_minute: 30,
    schedule_preset_id: null as number | null,
  })
  const [saving, setSaving] = useState(false)
  const { presets } = useScreenerStore()

  useEffect(() => {
    const load = async () => {
      try {
        const { api: apiClient } = await import('@/api/client')
        const res = await apiClient.get('/api/screener/schedule')
        setForm(res.data)
      } catch { /* ignore */ }
    }
    load()
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const { api: apiClient } = await import('@/api/client')
      await apiClient.post('/api/screener/schedule', form)
    } catch { /* ignore */ }
    setSaving(false)
  }

  return (
    <Card>
      <CardHeader title="定时选股" description="配置自动选股任务" />
      <div className="mt-4 space-y-5">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={form.schedule_enabled}
            onChange={(e) => setForm({ ...form, schedule_enabled: e.target.checked })}
            className="w-4 h-4 rounded border-cream-300 accent-copper"
          />
          <span className="text-sm font-medium">启用定时任务</span>
        </label>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-mono uppercase text-gray-500 mb-1">频率</label>
            <select
              value={form.schedule_frequency}
              onChange={(e) => setForm({ ...form, schedule_frequency: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
            >
              <option value="daily">每日</option>
              <option value="weekly">每周</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-mono uppercase text-gray-500 mb-1">星期</label>
            <input
              value={form.schedule_day_of_week}
              onChange={(e) => setForm({ ...form, schedule_day_of_week: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
              placeholder="mon-fri"
            />
          </div>
        </div>

        <div className="flex gap-4">
          <div>
            <label className="block text-xs font-mono uppercase text-gray-500 mb-1">小时</label>
            <input
              type="number"
              min={0} max={23}
              value={form.schedule_hour}
              onChange={(e) => setForm({ ...form, schedule_hour: Number(e.target.value) })}
              className="w-20 px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
            />
          </div>
          <div>
            <label className="block text-xs font-mono uppercase text-gray-500 mb-1">分钟</label>
            <input
              type="number"
              min={0} max={59}
              value={form.schedule_minute}
              onChange={(e) => setForm({ ...form, schedule_minute: Number(e.target.value) })}
              className="w-20 px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-mono uppercase text-gray-500 mb-1">使用预设</label>
          <select
            value={form.schedule_preset_id || ''}
            onChange={(e) => setForm({ ...form, schedule_preset_id: e.target.value ? Number(e.target.value) : null })}
            className="w-full px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
          >
            <option value="">不使用预设</option>
            {presets.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>

        <Button onClick={handleSave} disabled={saving}>
          {saving ? '保存中...' : '保存配置'}
        </Button>
      </div>
    </Card>
  )
}
