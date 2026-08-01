import { useCallback, useEffect, useState } from 'react'
import { api } from '@/api/client'
import { Card, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { useECharts } from '@/components/charts/useECharts'

// ─── 类型 ───

interface IndexTrend {
  close: number
  change_pct: number
  ema21: number
  ma50: number | null
  ma200: number | null
  above_ema21: boolean
  above_ma50: boolean
  above_ma200: boolean
  pct_vs_ma50: number | null
  pct_vs_ma200: number | null
}

interface FtdInfo {
  correction_low_date: string
  correction_pct: number
  in_correction: boolean
  days_since_low: number
  ftd: { date: string; day_of_attempt: number; gain_pct: number } | null
}

interface IndexStat {
  name: string
  dd_count: number
  dd_dates: string[]
  trend: IndexTrend
  ftd_info: FtdInfo
}

interface Breadth {
  universe_size?: number
  pct_above_ma50?: number | null
  pct_above_ma200?: number | null
  new_highs_52w?: number
  new_lows_52w?: number
  nh_nl_diff?: number
  rs_ge_80_count?: number | null
  stale?: boolean
}

interface Snapshot {
  snapshot_date: string
  state: 'green' | 'yellow' | 'red'
  prev_state: string
  reasons: string[]
  index_stats: Record<string, IndexStat>
  breadth: Breadth
  is_stale?: boolean
}

interface HistoryItem {
  date: string
  state: string
  dd_max: number
  pct_above_ma50: number | null
  pct_above_ma200: number | null
  nh_nl_diff: number | null
}

// ─── 样式映射 ───

const STATE_META: Record<string, { label: string; icon: string; bg: string; text: string; desc: string }> = {
  green: {
    label: '绿灯 · 顺风市场', icon: '🟢',
    bg: 'bg-emerald-50 border-emerald-300', text: 'text-emerald-700',
    desc: '趋势健康，可按标准风险执行买入信号',
  },
  yellow: {
    label: '黄灯 · 谨慎市场', icon: '🟡',
    bg: 'bg-amber-50 border-amber-300', text: 'text-amber-700',
    desc: '派发压力上升或趋势转弱，降低单笔风险、控制新开仓',
  },
  red: {
    label: '红灯 · 逆风市场', icon: '🔴',
    bg: 'bg-red-50 border-red-300', text: 'text-red-700',
    desc: '机构大举派发或趋势破坏，建议空仓或最低风险试探',
  },
}

const STATE_COLOR: Record<string, string> = {
  green: '#10b981',
  yellow: '#f59e0b',
  red: '#ef4444',
}

// ─── 宽度历史图 ───

function BreadthChart({ history }: { history: HistoryItem[] }) {
  const chartRef = useECharts(() => ({
    tooltip: { trigger: 'axis' },
    legend: { data: ['%>50MA', '%>200MA'], top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 40, right: 16, top: 28, bottom: 24 },
    xAxis: {
      type: 'category',
      data: history.map((h) => h.date.slice(5)),
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { fontSize: 10, formatter: '{value}%' } },
    series: [
      {
        name: '%>50MA', type: 'line', smooth: true, showSymbol: false,
        data: history.map((h) => h.pct_above_ma50),
        lineStyle: { width: 2, color: '#b87333' },
        itemStyle: { color: '#b87333' },
      },
      {
        name: '%>200MA', type: 'line', smooth: true, showSymbol: false,
        data: history.map((h) => h.pct_above_ma200),
        lineStyle: { width: 2, color: '#4b5563' },
        itemStyle: { color: '#4b5563' },
        markLine: {
          silent: true, symbol: 'none',
          data: [{ yAxis: 40 }],
          lineStyle: { type: 'dashed', color: '#ef4444', opacity: 0.5 },
          label: { formatter: '40% 警戒线', fontSize: 10 },
        },
      },
    ],
  }), [history])
  return <div ref={chartRef} className="w-full h-[260px]" />
}

// ─── 页面 ───

export default function MarketPage() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [snapRes, histRes] = await Promise.all([
        api.get('/api/market/regime'),
        api.get('/api/market/regime/history', { params: { days: 120 } }),
      ])
      setSnapshot(snapRes.data.snapshot)
      setHistory(histRes.data.history || [])
      setError('')
    } catch {
      setError('加载失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  async function handleRefresh() {
    setRefreshing(true)
    setError('')
    try {
      // 全量宽度计算耗时较长，单独放宽超时
      const res = await api.post('/api/market/regime/refresh', null, { timeout: 300_000 })
      setSnapshot(res.data.snapshot)
      const histRes = await api.get('/api/market/regime/history', { params: { days: 120 } })
      setHistory(histRes.data.history || [])
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || '刷新失败，请稍后重试')
    } finally {
      setRefreshing(false)
    }
  }

  const meta = snapshot ? STATE_META[snapshot.state] : null
  const breadth = snapshot?.breadth

  return (
    <div>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <span className="section-label flex items-center gap-2 mb-3">
            <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
            Market Regime
          </span>
          <h1 className="page-title">市场<span className="text-copper">红绿灯</span></h1>
          <p className="text-sm text-gray-500 mt-2">
            分布日计数 + FTD 确认 + 趋势位置 + 市场宽度（欧奈尔/Minervini 择时体系）
          </p>
        </div>
        <Button variant="primary" onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? '计算中（约 1-2 分钟）...' : '立即刷新'}
        </Button>
      </div>

      {error && (
        <div className="mb-6 px-4 py-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-600">
          {error}
        </div>
      )}

      {loading && !snapshot && (
        <div className="flex items-center justify-center py-20">
          <div className="w-6 h-6 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
        </div>
      )}

      {!loading && !snapshot && !error && (
        <Card>
          <p className="text-sm text-gray-500">
            暂无市场环境快照。点击右上角「立即刷新」生成首个快照（定时任务每个交易日 16:45 ET 自动更新）。
          </p>
        </Card>
      )}

      {snapshot && meta && (
        <div className="space-y-6">
          {/* 红绿灯主横幅 */}
          <div className={`border rounded-lg p-6 ${meta.bg}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <span className="text-4xl">{meta.icon}</span>
                <div>
                  <h2 className={`font-heading text-xl font-bold ${meta.text}`}>{meta.label}</h2>
                  <p className="text-sm text-gray-600 mt-1">{meta.desc}</p>
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono text-xs text-gray-500">
                  快照日期 {snapshot.snapshot_date}
                  {snapshot.is_stale && <span className="text-amber-600 ml-1">(非今日)</span>}
                </div>
                {snapshot.prev_state && snapshot.prev_state !== snapshot.state && (
                  <div className="font-mono text-xs text-gray-500 mt-1">
                    前一状态: {snapshot.prev_state.toUpperCase()}
                  </div>
                )}
              </div>
            </div>
            <ul className="mt-4 space-y-1">
              {snapshot.reasons.map((r, i) => (
                <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                  <span className="text-gray-400 mt-0.5">·</span>{r}
                </li>
              ))}
            </ul>
          </div>

          {/* 指数卡片 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {Object.entries(snapshot.index_stats).map(([sym, st]) => (
              <Card key={sym}>
                <CardHeader
                  title={st.name}
                  label={sym}
                  action={
                    <span className={`font-mono text-sm font-semibold ${st.trend.change_pct >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                      {st.trend.close?.toLocaleString()} ({st.trend.change_pct >= 0 ? '+' : ''}{st.trend.change_pct}%)
                    </span>
                  }
                />
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div className="bg-cream-100 rounded-md py-3">
                    <div className={`font-mono text-lg font-bold ${st.dd_count >= 6 ? 'text-red-500' : st.dd_count >= 4 ? 'text-amber-600' : 'text-gray-900'}`}>
                      {st.dd_count}
                    </div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide mt-1">分布日 (25日)</div>
                  </div>
                  <div className="bg-cream-100 rounded-md py-3">
                    <div className={`font-mono text-lg font-bold ${st.trend.above_ma50 ? 'text-emerald-600' : 'text-red-500'}`}>
                      {st.trend.pct_vs_ma50 != null ? `${st.trend.pct_vs_ma50 >= 0 ? '+' : ''}${st.trend.pct_vs_ma50}%` : '--'}
                    </div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide mt-1">vs 50MA</div>
                  </div>
                  <div className="bg-cream-100 rounded-md py-3">
                    <div className={`font-mono text-lg font-bold ${st.trend.above_ma200 ? 'text-emerald-600' : 'text-red-500'}`}>
                      {st.trend.pct_vs_ma200 != null ? `${st.trend.pct_vs_ma200 >= 0 ? '+' : ''}${st.trend.pct_vs_ma200}%` : '--'}
                    </div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide mt-1">vs 200MA</div>
                  </div>
                </div>
                <div className="mt-3 text-xs text-gray-500 space-y-1">
                  {st.ftd_info.in_correction ? (
                    st.ftd_info.ftd ? (
                      <p>
                        ✅ FTD 已确认：{st.ftd_info.ftd.date}（反弹第 {st.ftd_info.ftd.day_of_attempt} 天，+{st.ftd_info.ftd.gain_pct}%）
                      </p>
                    ) : (
                      <p>
                        ⏳ 修正中（{st.ftd_info.correction_pct}%），低点 {st.ftd_info.correction_low_date}，反弹第 {st.ftd_info.days_since_low + 1} 天，等待 FTD
                      </p>
                    )
                  ) : (
                    <p>趋势内运行，60 日内无 ≥5% 修正</p>
                  )}
                  {st.dd_dates.length > 0 && (
                    <p className="font-mono text-[10px]">分布日: {st.dd_dates.join(', ')}</p>
                  )}
                </div>
              </Card>
            ))}
          </div>

          {/* 市场宽度 */}
          <Card>
            <CardHeader
              title="市场宽度"
              label="Breadth"
              description={breadth?.stale ? '沿用最近一次全量计算结果' : `样本 ${breadth?.universe_size ?? '--'} 只（S&P500 + NDX100）`}
            />
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-center mb-4">
              {[
                { label: '%>50MA', value: breadth?.pct_above_ma50 != null ? `${breadth.pct_above_ma50}%` : '--' },
                { label: '%>200MA', value: breadth?.pct_above_ma200 != null ? `${breadth.pct_above_ma200}%` : '--' },
                { label: '52周新高', value: breadth?.new_highs_52w ?? '--' },
                { label: '52周新低', value: breadth?.new_lows_52w ?? '--' },
                { label: 'RS≥80 数量', value: breadth?.rs_ge_80_count ?? '--' },
              ].map((it) => (
                <div key={it.label} className="bg-cream-100 rounded-md py-3">
                  <div className="font-mono text-lg font-bold">{it.value}</div>
                  <div className="text-[10px] text-gray-500 uppercase tracking-wide mt-1">{it.label}</div>
                </div>
              ))}
            </div>
            {history.length > 1 && <BreadthChart history={history} />}
          </Card>

          {/* 红绿灯历史条 */}
          {history.length > 0 && (
            <Card>
              <CardHeader title="状态历史" label="History" description="最近 120 个快照日" />
              <div className="flex gap-[2px] items-end">
                {history.map((h) => (
                  <div
                    key={h.date}
                    title={`${h.date}: ${h.state.toUpperCase()} (分布日 ${h.dd_max})`}
                    className="flex-1 h-8 rounded-sm min-w-[3px]"
                    style={{ backgroundColor: STATE_COLOR[h.state] || '#d1d5db' }}
                  />
                ))}
              </div>
              <div className="flex justify-between mt-2 font-mono text-[10px] text-gray-400">
                <span>{history[0]?.date}</span>
                <span>{history[history.length - 1]?.date}</span>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
