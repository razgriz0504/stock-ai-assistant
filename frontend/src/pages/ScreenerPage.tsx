import { useState, useEffect, useRef, useCallback } from 'react'
import { Card, CardHeader, Button, Badge, Input } from '@/components/ui'
import { Tabs } from '@/components/ui'
import { api } from '@/api/client'
import { useScreenerStore, type ScreenerPreset } from '@/stores/screenerStore'

// ── Filter definitions ──
interface FilterDef {
  key: string
  label: string
  category: 'trend_continuation' | 'trend_initiation' | 'auxiliary' | 'fundamental'
  params?: ParamDef[]
}

interface ParamDef {
  id: string
  label: string
  type: 'number' | 'select'
  default: string | number
  options?: { value: string; label: string }[]
  min?: number
  max?: number
  step?: number
  width?: string
}

const FILTERS: FilterDef[] = [
  // 趋势延续
  {
    key: 'ma_arrangement', label: 'EMA Arrangement', category: 'trend_continuation',
    params: [
      { id: 'direction', label: '方向', type: 'select', default: 'bullish', options: [{ value: 'bullish', label: 'Bullish ↑' }, { value: 'bearish', label: 'Bearish ↓' }] },
    ],
  },
  // 趋势启动
  {
    key: 'trend_initiation', label: 'Trend Initiation', category: 'trend_initiation',
    params: [
      { id: 'lookback', label: '回溯', type: 'number', default: 5, min: 2, max: 15 },
      { id: 'vol_multiplier', label: '量比', type: 'number', default: 1.5, min: 1, step: 0.1 },
    ],
  },
  // 辅助指标
  {
    key: 'macd_golden_cross', label: 'MACD Golden Cross', category: 'auxiliary',
    params: [{ id: 'lookback', label: '回溯', type: 'number', default: 3, min: 1, max: 10 }],
  },
  {
    key: 'kdj_oversold_bounce', label: 'KDJ Oversold Bounce', category: 'auxiliary',
    params: [{ id: 'lookback', label: '回溯', type: 'number', default: 3, min: 1, max: 10 }],
  },
  {
    key: 'volume_breakout', label: 'Volume Breakout', category: 'auxiliary',
    params: [{ id: 'multiplier', label: '倍数', type: 'number', default: 2.0, min: 1, step: 0.5 }],
  },
  {
    key: 'rsi_zone', label: 'RSI Zone', category: 'auxiliary',
    params: [
      { id: 'min', label: 'Min', type: 'number', default: 30, min: 0, max: 100 },
      { id: 'max', label: 'Max', type: 'number', default: 70, min: 0, max: 100 },
    ],
  },
  {
    key: 'bb_squeeze', label: 'Bollinger Band', category: 'auxiliary',
    params: [
      { id: 'mode', label: '模式', type: 'select', default: 'squeeze', options: [{ value: 'squeeze', label: 'Squeeze' }, { value: 'breakout', label: 'Breakout ↑' }] },
      { id: 'width_threshold', label: '宽度', type: 'number', default: 0.15, step: 0.01, min: 0.01, max: 0.5 },
    ],
  },
  {
    key: 'atr_filter', label: 'ATR Volatility', category: 'auxiliary',
    params: [
      { id: 'min_pct', label: 'Min%', type: 'number', default: 1, step: 0.5, min: 0 },
      { id: 'max_pct', label: 'Max%', type: 'number', default: 5, step: 0.5, min: 0 },
    ],
  },
  // 基本面
  {
    key: 'pe_range', label: '市盈率 PE', category: 'fundamental',
    params: [
      { id: 'min', label: 'Min', type: 'number', default: 5, min: 0 },
      { id: 'max', label: 'Max', type: 'number', default: 30, min: 0 },
    ],
  },
  {
    key: 'market_cap', label: '市值规模', category: 'fundamental',
    params: [
      { id: 'tier', label: '档位', type: 'select', default: 'large', options: [{ value: 'large', label: '大盘 (>2000亿)' }, { value: 'mid', label: '中盘 (100-2000亿)' }, { value: 'small', label: '小盘 (<100亿)' }] },
    ],
  },
  {
    key: 'revenue_growth', label: '营收增长', category: 'fundamental',
    params: [{ id: 'min_pct', label: '最低%', type: 'number', default: 10, min: 0 }],
  },
  {
    key: 'roe_filter', label: 'ROE', category: 'fundamental',
    params: [{ id: 'min_pct', label: '最低%', type: 'number', default: 15, min: 0 }],
  },
  {
    key: 'dividend_yield', label: '股息率', category: 'fundamental',
    params: [{ id: 'min_pct', label: '最低%', type: 'number', default: 1, step: 0.5, min: 0 }],
  },
]

const CATEGORY_LABELS = {
  trend_continuation: { icon: '📈', title: '趋势延续', desc: '已确立上升趋势' },
  trend_initiation: { icon: '🚀', title: '趋势启动', desc: '刚开始上涨' },
  auxiliary: { icon: '🔧', title: '辅助指标', desc: '' },
  fundamental: { icon: '📊', title: '基本面筛选', desc: '' },
}

export default function ScreenerPage() {
  const [activeTab, setActiveTab] = useState('run')
  const store = useScreenerStore()

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
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          Stock Screener
        </span>
        <h1 className="page-title">选<span className="text-copper">股器</span></h1>
        <p className="text-sm text-gray-500 mt-2">标普500 + 纳斯达克100 智能筛选</p>
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
// Run Tab - Interactive Filter Panel + Presets
// ═══════════════════════════════════════════════════════════════
function RunTab() {
  const {
    status, progress, errorMessage,
    presets, activePresetId, customCode,
    setCustomCode, loadPreset, startRun, reset, setFilters,
  } = useScreenerStore()
  const { savePreset, deletePreset, fetchResults, pollStatus } = useScreenerStore()

  // Filter state: { [filterKey]: { enabled: boolean, ...params } }
  const [filterState, setFilterState] = useState<Record<string, Record<string, unknown>>>({})
  const [presetName, setPresetName] = useState('')

  // Toggle a filter on/off
  const toggleFilter = (key: string) => {
    setFilterState(prev => {
      const existing = prev[key]
      if (existing?.enabled) {
        return { ...prev, [key]: { ...existing, enabled: false } }
      }
      // Enable with defaults
      const def = FILTERS.find(f => f.key === key)
      const params: Record<string, unknown> = { enabled: true }
      def?.params?.forEach(p => { params[p.id] = p.default })
      return { ...prev, [key]: params }
    })
  }

  // Update a filter param
  const setParam = (filterKey: string, paramId: string, value: unknown) => {
    setFilterState(prev => ({
      ...prev,
      [filterKey]: { ...prev[filterKey], [paramId]: value },
    }))
  }

  // Build filters JSON from state
  const buildFiltersJson = useCallback(() => {
    const technical: Record<string, unknown> = {}
    const fundamental: Record<string, unknown> = {}
    for (const [key, val] of Object.entries(filterState)) {
      if (!val?.enabled) continue
      const def = FILTERS.find(f => f.key === key)
      if (!def) continue
      if (def.category === 'fundamental') {
        fundamental[key] = val
      } else {
        technical[key] = val
      }
    }
    return JSON.stringify({ technical, fundamental })
  }, [filterState])

  // Sync filter state to store
  useEffect(() => {
    setFilters(buildFiltersJson())
  }, [filterState, buildFiltersJson, setFilters])

  // Apply preset to filter state
  const handleLoadPreset = (preset: ScreenerPreset) => {
    loadPreset(preset)
    try {
      const cfg = JSON.parse(preset.filters_json || '{}')
      const newState: Record<string, Record<string, unknown>> = {}
      const tech = cfg.technical || {}
      const fund = cfg.fundamental || {}
      for (const [key, val] of Object.entries(tech)) {
        newState[key] = val as Record<string, unknown>
      }
      for (const [key, val] of Object.entries(fund)) {
        newState[key] = val as Record<string, unknown>
      }
      setFilterState(newState)
    } catch { /* ignore */ }
  }

  // Polling
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

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
    return () => { if (pollingRef.current) clearInterval(pollingRef.current) }
  }, [status, startPolling])

  const handleRun = async () => {
    await startRun()
    startPolling()
  }

  // Group filters by category
  const categories = ['trend_continuation', 'trend_initiation', 'auxiliary', 'fundamental'] as const

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6">
      {/* Left: Filter Panel */}
      <div className="space-y-4">
        {/* Presets */}
        <Card>
          <CardHeader title="预设策略" />
          <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
            {presets.map((p: ScreenerPreset) => (
              <div
                key={p.id}
                className={`flex items-center justify-between px-3 py-2 rounded-md cursor-pointer transition-all text-sm ${
                  activePresetId === p.id
                    ? 'bg-orange-50 border border-copper/20'
                    : 'hover:bg-cream-100'
                }`}
                onClick={() => handleLoadPreset(p)}
              >
                <span className="font-medium">{p.name}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); deletePreset(p.id) }}
                  className="text-gray-400 hover:text-danger text-xs"
                >✕</button>
              </div>
            ))}
            {presets.length === 0 && (
              <p className="text-xs text-gray-400 py-3 text-center">暂无预设</p>
            )}
          </div>
          <div className="mt-3 pt-3 border-t border-cream-200 flex gap-2">
            <input
              value={presetName}
              onChange={(e) => setPresetName(e.target.value)}
              placeholder="预设名称"
              className="flex-1 px-2.5 py-1.5 text-xs border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
            />
            <Button size="sm" variant="secondary" onClick={() => {
              if (presetName.trim()) { savePreset(presetName.trim()); setPresetName('') }
            }}>保存</Button>
          </div>
        </Card>

        {/* Filter checkboxes */}
        {categories.map(cat => {
          const catFilters = FILTERS.filter(f => f.category === cat)
          const catInfo = CATEGORY_LABELS[cat]
          return (
            <Card key={cat} className="p-4">
              <div className="flex items-center gap-2 mb-3">
                <span>{catInfo.icon}</span>
                <span className="font-heading font-semibold text-sm">{catInfo.title}</span>
                {catInfo.desc && <span className="text-[10px] text-gray-400">({catInfo.desc})</span>}
              </div>
              <div className="space-y-2">
                {catFilters.map(f => {
                  const isEnabled = !!filterState[f.key]?.enabled
                  return (
                    <div key={f.key}>
                      <label className="flex items-center gap-2.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={isEnabled}
                          onChange={() => toggleFilter(f.key)}
                          className="w-3.5 h-3.5 rounded border-cream-300 accent-copper"
                        />
                        <span className="text-xs font-medium">{f.label}</span>
                      </label>
                      {isEnabled && f.params && (
                        <div className="ml-6 mt-1.5 flex flex-wrap gap-2 items-center">
                          {f.params.map(p => (
                            <div key={p.id} className="flex items-center gap-1">
                              <span className="text-[10px] text-gray-500">{p.label}:</span>
                              {p.type === 'select' ? (
                                <select
                                  value={String(filterState[f.key]?.[p.id] ?? p.default)}
                                  onChange={e => setParam(f.key, p.id, e.target.value)}
                                  className="px-1.5 py-0.5 text-[11px] border border-cream-300 rounded bg-white focus:outline-none focus:border-copper"
                                >
                                  {p.options?.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                                </select>
                              ) : (
                                <input
                                  type="number"
                                  value={String(filterState[f.key]?.[p.id] ?? p.default)}
                                  onChange={e => setParam(f.key, p.id, parseFloat(e.target.value) || 0)}
                                  min={p.min}
                                  max={p.max}
                                  step={p.step}
                                  className="w-14 px-1.5 py-0.5 text-[11px] border border-cream-300 rounded bg-white focus:outline-none focus:border-copper"
                                />
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </Card>
          )
        })}

        {/* Custom code */}
        <Card className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <span>💻</span>
            <span className="font-heading font-semibold text-sm">自定义代码</span>
          </div>
          <textarea
            value={customCode}
            onChange={(e) => setCustomCode(e.target.value)}
            rows={5}
            className="w-full px-2.5 py-2 text-[11px] font-mono border border-cream-300 rounded-md bg-cream-50 focus:outline-none focus:border-copper resize-y"
            placeholder={`def filter(data, info):\n    # data: DataFrame with indicators\n    # info: dict with fundamentals\n    return data['RSI_14'].iloc[-1] < 40`}
          />
        </Card>
      </div>

      {/* Right: Status + Run */}
      <div className="space-y-4">
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
            <div className="flex-1">
              <span className="text-sm font-medium">
                {status === 'pending' && '提交中...'}
                {status === 'running' && `正在扫描 (${progress}%)`}
                {status === 'success' && '选股完成 ✓'}
                {status === 'failed' && `失败: ${errorMessage || '未知错误'}`}
              </span>
              {status === 'running' && (
                <div className="mt-2 h-2 bg-cream-200 rounded-full overflow-hidden">
                  <div className="h-full bg-copper rounded-full transition-all" style={{ width: `${progress}%` }} />
                </div>
              )}
            </div>
            {(status === 'success' || status === 'failed') && (
              <Button size="sm" variant="ghost" onClick={reset}>重置</Button>
            )}
          </div>
        )}

        {/* Active filters summary */}
        <Card>
          <CardHeader title="当前筛选条件" description="已勾选的策略将以 AND 逻辑组合" />
          <div className="flex flex-wrap gap-2">
            {Object.entries(filterState).filter(([, v]) => v?.enabled).map(([key]) => {
              const def = FILTERS.find(f => f.key === key)
              return (
                <Badge key={key} variant="copper">{def?.label || key}</Badge>
              )
            })}
            {Object.entries(filterState).filter(([, v]) => v?.enabled).length === 0 && (
              <p className="text-xs text-gray-400">未选择任何筛选条件，请在左侧勾选</p>
            )}
          </div>
        </Card>

        {/* Run button */}
        <Button
          onClick={handleRun}
          disabled={status === 'running' || status === 'pending'}
          className="w-full"
        >
          {status === 'running' ? `⏳ 扫描中 (${progress}%)` : '▶ 开始选股'}
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
    const aVal = (a as unknown as Record<string, unknown>)[sortBy] as number || 0
    const bVal = (b as unknown as Record<string, unknown>)[sortBy] as number || 0
    return sortOrder === 'desc' ? bVal - aVal : aVal - bVal
  })

  const toggleSort = (field: string) => {
    if (sortBy === field) { setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc') }
    else { setSortBy(field); setSortOrder('desc') }
  }

  const SortHeader = ({ field, label, align = 'right' }: { field: string; label: string; align?: string }) => (
    <th
      className={`text-${align} px-3 py-2 font-mono text-[10px] uppercase text-gray-500 cursor-pointer hover:text-copper transition-colors`}
      onClick={() => toggleSort(field)}
    >
      {label} {sortBy === field && (sortOrder === 'desc' ? '↓' : '↑')}
    </th>
  )

  const fmtCap = (v: number) => {
    if (!v) return '-'
    if (v >= 1e12) return (v / 1e12).toFixed(1) + 'T'
    if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B'
    if (v >= 1e6) return (v / 1e6).toFixed(0) + 'M'
    return String(v)
  }

  if (!runId) {
    return (
      <Card>
        <p className="text-sm text-gray-400 text-center py-10">
          尚未执行选股。请在「运行选股」标签页配置条件并启动。
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
      <Card className="p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cream-300 bg-cream-100">
                <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">代码</th>
                <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">名称</th>
                <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">板块</th>
                <SortHeader field="score" label="评分" />
                <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">等级</th>
                <SortHeader field="price" label="价格" />
                <SortHeader field="change_pct" label="涨跌%" />
                <SortHeader field="pe_ratio" label="PE" />
                <SortHeader field="market_cap" label="市值" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.symbol} className="border-b border-cream-200 hover:bg-cream-50 transition-colors">
                  <td className="px-3 py-2 font-mono font-semibold text-xs">{r.symbol}</td>
                  <td className="px-3 py-2 text-xs text-gray-600">{r.name}</td>
                  <td className="px-3 py-2 text-xs text-gray-500">{r.sector}</td>
                  <td className="px-3 py-2 text-right">
                    <Badge variant={r.score >= 70 ? 'success' : r.score >= 40 ? 'warning' : 'danger'}>
                      {r.score?.toFixed(1)}
                    </Badge>
                  </td>
                  <td className="px-3 py-2"><Badge variant="copper">{r.rating || '-'}</Badge></td>
                  <td className="px-3 py-2 text-right font-mono text-xs">${r.price?.toFixed(2)}</td>
                  <td className={`px-3 py-2 text-right font-mono text-xs font-medium ${r.change_pct >= 0 ? 'text-success' : 'text-danger'}`}>
                    {r.change_pct >= 0 ? '+' : ''}{r.change_pct?.toFixed(2)}%
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{r.pe_ratio?.toFixed(1) || '-'}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{fmtCap(r.market_cap)}</td>
                </tr>
              ))}
              {results.length === 0 && (
                <tr><td colSpan={9} className="text-center py-8 text-sm text-gray-400">暂无结果</td></tr>
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
                <td className="px-3 py-2 font-mono font-semibold text-xs">v{r.version}</td>
                <td className="px-3 py-2"><Badge variant={statusColor(r.status)}>{r.status}</Badge></td>
                <td className="px-3 py-2 text-xs text-gray-500">{r.trigger === 'manual' ? '手动' : '定时'}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{r.total_stocks || '-'}</td>
                <td className="px-3 py-2 text-right font-mono text-xs font-medium text-copper">{r.passed_stocks || '-'}</td>
                <td className="px-3 py-2 font-mono text-[10px] text-gray-400">
                  {r.started_at ? new Date(r.started_at).toLocaleString('zh-CN') : '-'}
                </td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr><td colSpan={6} className="text-center py-8 text-sm text-gray-400">暂无记录</td></tr>
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
        const res = await api.get('/api/screener/schedule')
        setForm(res.data)
      } catch { /* ignore */ }
    }
    load()
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.post('/api/screener/schedule', form)
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
              <option value="daily">每天</option>
              <option value="weekly">每周</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-mono uppercase text-gray-500 mb-1">日期</label>
            <select
              value={form.schedule_day_of_week}
              onChange={(e) => setForm({ ...form, schedule_day_of_week: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
            >
              <option value="mon-fri">周一至周五</option>
              <option value="mon,wed,fri">周一/三/五</option>
              <option value="fri">周五</option>
            </select>
          </div>
        </div>

        <div className="flex gap-4">
          <div>
            <label className="block text-xs font-mono uppercase text-gray-500 mb-1">小时 (ET)</label>
            <input type="number" min={0} max={23} value={form.schedule_hour}
              onChange={(e) => setForm({ ...form, schedule_hour: Number(e.target.value) })}
              className="w-20 px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper" />
          </div>
          <div>
            <label className="block text-xs font-mono uppercase text-gray-500 mb-1">分钟</label>
            <input type="number" min={0} max={59} value={form.schedule_minute}
              onChange={(e) => setForm({ ...form, schedule_minute: Number(e.target.value) })}
              className="w-20 px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper" />
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
            {presets.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>

        <Button onClick={handleSave} disabled={saving}>
          {saving ? '保存中...' : '保存配置'}
        </Button>
      </div>
    </Card>
  )
}
