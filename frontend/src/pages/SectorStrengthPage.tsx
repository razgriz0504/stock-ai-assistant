import { Fragment, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Card, Button, Badge } from '@/components/ui'
import LogbiasChart from '@/components/charts/LogbiasChart'
import LogPriceChart from '@/components/charts/LogPriceChart'
import { exportNodeAsHtml } from '@/utils/exportReport'

// SPDR 板块 ETF → yfinance 中的 sector 名称
const SPDR_TO_SECTOR: Record<string, string> = {
  XLK: 'Technology',
  XLF: 'Financial Services',
  XLV: 'Healthcare',
  XLY: 'Consumer Cyclical',
  XLP: 'Consumer Defensive',
  XLC: 'Communication Services',
  XLI: 'Industrials',
  XLE: 'Energy',
  XLB: 'Basic Materials',
  XLRE: 'Real Estate',
  XLU: 'Utilities',
}

interface SectorItem {
  symbol: string
  name: string
  category: string
  current: number
  chg_5d: number | null
  chg_15d: number | null
  chg_30d: number | null
  chg_60d: number | null
  vol_ratio: number
  rs: { composite: number | null; rs_5d: number | null; rs_15d: number | null; rs_30d: number | null; rs_60d: number | null }
  flow: { direction: string; flow_5d: number | null; vol_surge: number | null; accumulation: number | null }
  logbias: { value: number | null; zone: string; series: number[]; dates: string[]; log_close: number[]; ema: number[] }
  rs_line: { value: number | null; series: number[]; dates: string[] }
}

// 取数组尾部 n 个元素（用于截取近 N 个交易日）
function sliceTail<T>(arr: T[], n: number): T[] {
  return arr.slice(Math.max(0, arr.length - n))
}

// 展开区三个时间窗口（交易日）：近6个月 / 近3个月 / 近1个月
const LOGBIAS_WINDOWS: [string, number][] = [
  ['近 6 个月', 126],
  ['近 3 个月', 63],
  ['近 1 个月', 21],
]

// RS 相对强弱线阈值（零轴：强于/弱于大盘分界）
const RS_THRESHOLDS = [
  { y: 0, color: '#9ca3af', label: '大盘线 0' },
]

// LOGBIAS 状态区间 → 展示样式
const ZONE_META: Record<string, { label: string; cls: string }> = {
  overheated: { label: '过热', cls: 'bg-red-100 text-red-700' },
  moderate: { label: '适中', cls: 'bg-amber-100 text-amber-700' },
  above: { label: '均线上方', cls: 'bg-green-100 text-green-700' },
  hold: { label: '刚跌破', cls: 'bg-gray-100 text-gray-600' },
  exit: { label: '失速', cls: 'bg-red-100 text-red-700' },
  unknown: { label: '-', cls: 'bg-gray-50 text-gray-400' },
}

type SortKey = 'rs_composite' | 'chg_5d' | 'chg_15d' | 'chg_30d' | 'vol_ratio' | 'logbias'
type Market = 'us' | 'cn'

export default function SectorStrengthPage() {
  const navigate = useNavigate()
  const reportRef = useRef<HTMLDivElement>(null)
  const [market, setMarket] = useState<Market>('us')
  const [sortBy, setSortBy] = useState<SortKey>('rs_composite')
  const [filterCat, setFilterCat] = useState<string>('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [showRsHelp, setShowRsHelp] = useState(false)
  const [exporting, setExporting] = useState(false)

  // 市场相关词汇/符号
  const benchmarkLabel = market === 'cn' ? '沪深300' : 'SPY'
  const currencySymbol = market === 'cn' ? '¥' : '$'

  // 切换市场时重置展开行与分类过滤（防止新市场不包含旧 symbol/分类导致 UI 错位）
  const switchMarket = (m: Market) => {
    if (m === market) return
    setMarket(m)
    setExpanded(new Set())
    setFilterCat('')
  }

  // 允许多行同时展开：切换某一行时不影响其它已展开行
  const toggleExpand = (symbol: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(symbol)) next.delete(symbol)
      else next.add(symbol)
      return next
    })
  }

  const handleExport = async () => {
    if (!reportRef.current) return
    setExporting(true)
    // 导出前记录当前展开状态，并临时展开所有行，使导出的报告包含全部展开图表
    const prevExpanded = expanded
    const allSymbols = filtered.map(s => s.symbol)
    setExpanded(new Set(allSymbols))
    try {
      // 等待 React 提交 DOM 且 ECharts 完成渲染（图表较多，留足渲染时间）
      await new Promise<void>(resolve =>
        requestAnimationFrame(() => setTimeout(resolve, 900))
      )
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
      await exportNodeAsHtml(reportRef.current, {
        title: '板块强度雷达',
        filename: `板块强度雷达_${stamp}.html`,
      })
    } finally {
      // 还原用户原本的展开状态
      setExpanded(prevExpanded)
      setExporting(false)
    }
  }

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['sector-strength', market],
    queryFn: async () => {
      const res = await api.get(`/api/sector-strength/data?market=${market}`)
      return res.data
    },
    staleTime: 60_000,
  })

  const sectors: SectorItem[] = data?.sectors || []
  const updatedAt = data?.generated_at || ''

  const getSortValue = (s: SectorItem, key: SortKey): number => {
    if (key === 'rs_composite') return s.rs?.composite ?? -999
    if (key === 'chg_5d') return s.chg_5d ?? -999
    if (key === 'chg_15d') return s.chg_15d ?? -999
    if (key === 'chg_30d') return s.chg_30d ?? -999
    if (key === 'vol_ratio') return s.vol_ratio ?? 0
    if (key === 'logbias') return s.logbias?.value ?? -999
    return 0
  }

  const filtered = sectors
    .filter(s => !filterCat || s.category === filterCat)
    .sort((a, b) => getSortValue(b, sortBy) - getSortValue(a, sortBy))

  const categories = [...new Set(sectors.map(s => s.category))].filter(Boolean)

  const fmtPct = (v: number | null) => {
    if (v == null) return '-'
    const sign = v >= 0 ? '+' : ''
    return `${sign}${v.toFixed(2)}%`
  }

  const pctColor = (v: number | null) => {
    if (v == null) return 'text-gray-500'
    return v > 0 ? 'text-success' : v < 0 ? 'text-danger' : 'text-gray-500'
  }

  return (
    <div ref={reportRef}>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <span className="section-label flex items-center gap-2 mb-3">
            <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
            Sector Radar
          </span>
          <h1 className="page-title">板块强度<span className="text-copper">雷达</span></h1>
        </div>
        <div className="flex items-center gap-3">
          {/* 市场 Tab 切换 */}
          <div className="inline-flex rounded-md border border-cream-300 overflow-hidden">
            <button
              onClick={() => switchMarket('us')}
              className={`px-3 py-1.5 text-xs font-mono transition-colors ${
                market === 'us'
                  ? 'bg-copper text-white'
                  : 'bg-white text-gray-600 hover:bg-cream-50'
              }`}
            >
              美股
            </button>
            <button
              onClick={() => switchMarket('cn')}
              className={`px-3 py-1.5 text-xs font-mono transition-colors border-l border-cream-300 ${
                market === 'cn'
                  ? 'bg-copper text-white'
                  : 'bg-white text-gray-600 hover:bg-cream-50'
              }`}
            >
              A 股
            </button>
          </div>
          {updatedAt && <span className="text-xs text-gray-500 font-mono">{updatedAt}</span>}
          <Button size="sm" variant="ghost" onClick={() => setShowRsHelp(v => !v)}>
            {showRsHelp ? '收起 RS 说明' : 'RS 说明'}
          </Button>
          <Button size="sm" variant="secondary" onClick={handleExport} disabled={exporting || isLoading}>
            {exporting ? '导出中...' : '导出'}
          </Button>
          <Button size="sm" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? '刷新中...' : '刷新'}
          </Button>
        </div>
      </div>

      {/* RS 说明 */}
      {showRsHelp && (
        <Card className="mb-4 p-4 bg-cream-50 border-cream-300">
          <div className="text-sm text-gray-700 space-y-2 leading-relaxed">
            <div className="font-semibold text-gray-900">RS 相对强弱（Relative Strength）</div>
            <p>
              RS 衡量一个板块相对于大盘（基准：{benchmarkLabel}）的表现强弱，而非绝对涨跌。
              即使板块下跌，只要跌得比大盘少，RS 依然可能为正（强于大盘）。
            </p>
            <ul className="list-disc pl-5 space-y-1 text-gray-600">
              <li><strong className="text-gray-800">RS 评分（composite）</strong>：综合 5/15/30/60 日多周期相对表现的加权评分，数值越高代表越强，用于默认排序。</li>
              <li><strong className="text-gray-800">RS 强弱线（vs {benchmarkLabel}）</strong>：展开行中的曲线，以零轴为界——在零轴上方表示近期跑赢大盘，下方表示跑输。</li>
              <li><strong className="text-gray-800">应用</strong>：优先关注 RS 持续走强、刚从零轴下方上穿的板块（轮动拐点），避开 RS 持续走弱的板块。</li>
            </ul>
          </div>
        </Card>
      )}

      {/* Filters */}
      <div className="flex gap-2 mb-4 flex-wrap">
        <button
          onClick={() => setFilterCat('')}
          className={`px-3 py-1.5 text-xs font-mono rounded-full border transition-all ${
            !filterCat ? 'border-copper text-copper bg-orange-50' : 'border-cream-300 text-gray-500 hover:text-gray-900'
          }`}
        >
          全部
        </button>
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => setFilterCat(cat)}
            className={`px-3 py-1.5 text-xs font-mono rounded-full border transition-all ${
              filterCat === cat ? 'border-copper text-copper bg-orange-50' : 'border-cream-300 text-gray-500 hover:text-gray-900'
            }`}
          >
            {cat}
          </button>
        ))}
        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value as SortKey)}
          className="ml-auto px-3 py-1.5 text-xs font-mono border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
        >
          <option value="rs_composite">RS 评分</option>
          <option value="chg_5d">5日涨跌</option>
          <option value="chg_15d">15日涨跌</option>
          <option value="chg_30d">30日涨跌</option>
          <option value="vol_ratio">量比</option>
          <option value="logbias">偏离度</option>
        </select>
      </div>

      {/* Table */}
      <Card className="p-0 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-6 h-6 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-cream-300 bg-cream-100">
                  <th className="text-left px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">#</th>
                  <th className="text-left px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">ETF</th>
                  <th className="text-left px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">分类</th>
                  <th className="text-right px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">价格</th>
                  <th className="text-right px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">5日</th>
                  <th className="text-right px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">15日</th>
                  <th className="text-right px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">30日</th>
                  <th className="text-right px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">RS</th>
                  <th
                    className="text-right px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500 cursor-help"
                    title="量比 = 近期成交量 / 过去一段时间的平均成交量。≥1 表示放量（资金活跃），<1 表示缩量。量比越大，说明当前成交越活跃，配合价格上涨更具意义。"
                  >
                    量比 <span className="text-gray-400">?</span>
                  </th>
                  <th className="text-center px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">偏离度</th>
                  <th className="text-center px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">资金流向</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s, i) => {
                  const sectorName = SPDR_TO_SECTOR[s.symbol]
                  // A 股无对应选股器行业映射，“→ 选股”按钮仅在美股后可用
                  const clickable = market === 'us' && !!sectorName
                  const isExpanded = expanded.has(s.symbol)
                  const zone = ZONE_META[s.logbias?.zone ?? 'unknown'] ?? ZONE_META.unknown ?? { label: '-', cls: 'bg-gray-50 text-gray-400' }
                  const goScreener = (e: MouseEvent) => {
                    e.stopPropagation()
                    if (!sectorName) return
                    navigate(`/screener?sector=${encodeURIComponent(sectorName)}&autorun=1`)
                  }
                  return (
                    <Fragment key={s.symbol}>
                    <tr
                      onClick={() => toggleExpand(s.symbol)}
                      className={`border-b border-cream-200 transition-colors cursor-pointer ${
                        isExpanded ? 'bg-orange-50' : 'hover:bg-cream-50'
                      }`}
                      title="点击展开对数均线偏离度曲线"
                    >
                      <td className="px-4 py-3 text-xs text-gray-400">{i + 1}</td>
                      <td className="px-4 py-3">
                        <span className="font-mono font-semibold text-xs">{s.symbol}</span>
                        <span className="text-xs text-gray-500 ml-2">{s.name}</span>
                        {clickable && (
                          <button
                            onClick={goScreener}
                            className="ml-2 text-[10px] text-copper hover:underline"
                            title={`锁定${s.name}板块运行选股`}
                          >
                            → 选股
                          </button>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Badge>{s.category}</Badge>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs">{currencySymbol}{s.current?.toFixed(2)}</td>
                      <td className={`px-4 py-3 text-right font-mono text-xs font-medium ${pctColor(s.chg_5d)}`}>
                        {fmtPct(s.chg_5d)}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono text-xs font-medium ${pctColor(s.chg_15d)}`}>
                        {fmtPct(s.chg_15d)}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono text-xs font-medium ${pctColor(s.chg_30d)}`}>
                        {fmtPct(s.chg_30d)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs font-bold">{s.rs?.composite?.toFixed(1) ?? '-'}</td>
                      <td className={`px-4 py-3 text-right font-mono text-xs ${s.vol_ratio >= 1 ? 'text-gray-900 font-medium' : 'text-gray-500'}`}>
                        {s.vol_ratio != null ? `${s.vol_ratio.toFixed(2)}x` : '-'}
                      </td>
                      <td className="px-4 py-3 text-center whitespace-nowrap">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono ${zone.cls}`}>
                          <span className="font-semibold">{s.logbias?.value != null ? `${s.logbias.value > 0 ? '+' : ''}${s.logbias.value.toFixed(1)}` : '-'}</span>
                          <span>{zone.label}</span>
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Badge variant={s.flow?.direction === 'inflow' ? 'success' : s.flow?.direction === 'outflow' ? 'danger' : 'default'}>
                          {s.flow?.direction === 'inflow' ? '流入' : s.flow?.direction === 'outflow' ? '流出' : '中性'}
                        </Badge>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="bg-cream-50 border-b border-cream-200">
                        <td colSpan={11} className="px-6 py-4">
                          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
                            <span className="font-medium text-gray-600">{s.symbol} {s.name}</span>
                            <span>对数值 ln(Close) + EMA20</span>
                            <span>
                              乖离率
                              {s.logbias?.value != null && (
                                <span className="ml-1"><strong className="text-copper">{s.logbias.value.toFixed(2)}%</strong></span>
                              )}
                            </span>
                            <span>
                              RS 相对强弱 (vs {benchmarkLabel})
                              {s.rs_line?.value != null && (
                                <span className="ml-1"><strong style={{ color: '#16a34a' }}>{s.rs_line.value.toFixed(2)}%</strong></span>
                              )}
                            </span>
                          </div>
                          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                            {LOGBIAS_WINDOWS.map(([label, n]) => (
                              <div key={label} className="space-y-3">
                                <LogPriceChart
                                  title={`对数值及EMA20 · ${label}`}
                                  logClose={sliceTail(s.logbias?.log_close || [], n)}
                                  ema={sliceTail(s.logbias?.ema || [], n)}
                                  dates={sliceTail(s.logbias?.dates || [], n)}
                                  height={180}
                                />
                                <LogbiasChart
                                  title={`乖离率 · ${label}`}
                                  series={sliceTail(s.logbias?.series || [], n)}
                                  dates={sliceTail(s.logbias?.dates || [], n)}
                                  height={160}
                                />
                                <LogbiasChart
                                  title={`RS 强弱 · ${label}`}
                                  series={sliceTail(s.rs_line?.series || [], n)}
                                  dates={sliceTail(s.rs_line?.dates || [], n)}
                                  height={160}
                                  color="#16a34a"
                                  thresholds={RS_THRESHOLDS}
                                />
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
