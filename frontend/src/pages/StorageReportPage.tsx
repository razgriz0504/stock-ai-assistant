import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Button, Card, Badge } from '@/components/ui'
import { useStorageReportStore } from '@/stores/storageReportStore'

const TIME_RANGES = ['近1个月', '近3个月', '近6个月', '近1年']

const TABS = [
  { id: 'prosperity', label: '景气度' },
  { id: 'price_trend', label: '价格趋势' },
  { id: 'supply_demand', label: '供需归因' },
  { id: 'vendor', label: '厂商动态' },
  { id: 'metric', label: '指标查询' },
  { id: 'anomaly', label: '异动识别' },
  { id: 'reports', label: '完整报告' },
]

function Markdown({ text }: { text?: string }) {
  if (!text) return <p className="text-sm text-gray-400">暂无内容</p>
  return (
    <div className="report-markdown text-sm leading-[1.8] text-gray-700">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  )
}

function Spinner() {
  return (
    <div className="flex justify-center py-10">
      <div className="w-5 h-5 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
    </div>
  )
}

function ResultCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative pl-5 py-5 px-5 bg-white border border-cream-300 rounded-lg">
      <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-copper rounded-l-lg" />
      {children}
    </div>
  )
}

// 多选标签组
function MultiChips({
  options,
  selected,
  onToggle,
}: {
  options: Record<string, string>
  selected: string[]
  onToggle: (key: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(options).map(([key, label]) => {
        const active = selected.includes(key)
        return (
          <button
            key={key}
            onClick={() => onToggle(key)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-all ${
              active
                ? 'bg-orange-50 text-copper border-copper/40'
                : 'bg-white text-gray-500 border-cream-300 hover:border-gray-400'
            }`}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}

export default function StorageReportPage() {
  const {
    meta, fetchMeta,
    loading, results,
    runMetricQuery, runProsperity, runPriceTrend, runSupplyDemand, runVendorTracking, runAnomaly,
    genStatus, generate, pollStatus,
    reports, currentReport, fetchReports, fetchReport, deleteReport,
  } = useStorageReportStore()

  const [activeTab, setActiveTab] = useState('prosperity')
  const [timeRange, setTimeRange] = useState('近3个月')
  const [categories, setCategories] = useState<string[]>(['DRAM', 'NAND', 'HBM'])
  const [themes, setThemes] = useState<string[]>([])
  const [supplyCategory, setSupplyCategory] = useState('DRAM')
  const [vendors, setVendors] = useState<string[]>([])
  const [metricKey, setMetricKey] = useState('')
  const [metricCategory, setMetricCategory] = useState('')

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    fetchMeta()
    fetchReports()
  }, [fetchMeta, fetchReports])

  // 初始化默认勾选
  useEffect(() => {
    if (meta) {
      if (themes.length === 0) setThemes(Object.keys(meta.themes))
      if (vendors.length === 0) setVendors(Object.keys(meta.vendors))
      const firstMetric = meta.metrics[0]
      if (!metricKey && firstMetric) setMetricKey(firstMetric.key)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta])

  // 轮询完整报告状态
  useEffect(() => {
    if (genStatus === 'running') {
      pollRef.current = setInterval(async () => {
        const done = await pollStatus()
        if (done && pollRef.current) clearInterval(pollRef.current)
      }, 4000)
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [genStatus, pollStatus])

  const toggle = (arr: string[], setArr: (v: string[]) => void, key: string) => {
    setArr(arr.includes(key) ? arr.filter((k) => k !== key) : [...arr, key])
  }

  const selectedMetric = useMemo(
    () => meta?.metrics.find((m) => m.key === metricKey),
    [meta, metricKey],
  )

  if (!meta) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-6 h-6 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-end justify-between mb-8">
        <div>
          <span className="section-label flex items-center gap-2 mb-3">
            <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
            Storage Industry Research
          </span>
          <h1 className="page-title">
            存储<span className="text-copper">行业研究</span>
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            onClick={() => generate(categories, timeRange)}
            disabled={genStatus === 'pending' || genStatus === 'running'}
          >
            {genStatus === 'running' || genStatus === 'pending' ? '生成中…' : '一键生成完整报告'}
          </Button>
        </div>
      </div>

      {/* 全局控制条：时间范围 + 品类 */}
      <Card className="mb-6">
        <div className="p-5 space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="font-mono text-[10px] uppercase text-gray-500 w-16">时间范围</span>
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="px-3 py-2 text-xs font-mono border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
            >
              {TIME_RANGES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div className="flex items-start gap-3 flex-wrap">
            <span className="font-mono text-[10px] uppercase text-gray-500 w-16 pt-1.5">品类</span>
            <MultiChips
              options={meta.categories}
              selected={categories}
              onToggle={(k) => toggle(categories, setCategories, k)}
            />
          </div>
        </div>
      </Card>

      {/* Tabs */}
      <div className="flex gap-0 border-b-2 border-cream-300 mb-8 overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`font-mono text-xs tracking-[1px] uppercase px-5 py-3 cursor-pointer border-b-2 -mb-[2px] whitespace-nowrap transition-all ${
              activeTab === tab.id
                ? 'text-copper border-copper'
                : 'text-gray-500 border-transparent hover:text-gray-900'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── 景气度 ── */}
      {activeTab === 'prosperity' && (
        <div className="space-y-5">
          <div className="flex items-start gap-3 flex-wrap">
            <span className="font-mono text-[10px] uppercase text-gray-500 w-16 pt-1.5">主题</span>
            <MultiChips options={meta.themes} selected={themes} onToggle={(k) => toggle(themes, setThemes, k)} />
          </div>
          <Button size="sm" onClick={() => runProsperity(timeRange, categories, themes)} disabled={loading.prosperity}>
            {loading.prosperity ? '分析中…' : '生成景气度研判'}
          </Button>
          {loading.prosperity ? <Spinner /> : <ProsperityResult data={results.prosperity} />}
        </div>
      )}

      {/* ── 价格趋势 ── */}
      {activeTab === 'price_trend' && (
        <div className="space-y-5">
          <Button size="sm" onClick={() => runPriceTrend(categories, timeRange)} disabled={loading.price_trend}>
            {loading.price_trend ? '分析中…' : '生成价格趋势分析'}
          </Button>
          {loading.price_trend ? <Spinner /> : <PriceTrendResult data={results.price_trend} />}
        </div>
      )}

      {/* ── 供需归因 ── */}
      {activeTab === 'supply_demand' && (
        <div className="space-y-5">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="font-mono text-[10px] uppercase text-gray-500 w-16">品类</span>
            <select
              value={supplyCategory}
              onChange={(e) => setSupplyCategory(e.target.value)}
              className="px-3 py-2 text-xs font-mono border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
            >
              {Object.entries(meta.categories).map(([k, label]) => (
                <option key={k} value={k}>{label}</option>
              ))}
            </select>
          </div>
          <Button size="sm" onClick={() => runSupplyDemand(supplyCategory, timeRange)} disabled={loading.supply_demand}>
            {loading.supply_demand ? '分析中…' : '生成供需归因'}
          </Button>
          {loading.supply_demand ? <Spinner /> : results.supply_demand && (
            <ResultCard><Markdown text={results.supply_demand.content} /></ResultCard>
          )}
        </div>
      )}

      {/* ── 厂商动态 ── */}
      {activeTab === 'vendor' && (
        <div className="space-y-5">
          <div className="flex items-start gap-3 flex-wrap">
            <span className="font-mono text-[10px] uppercase text-gray-500 w-16 pt-1.5">厂商</span>
            <MultiChips options={meta.vendors} selected={vendors} onToggle={(k) => toggle(vendors, setVendors, k)} />
          </div>
          <Button size="sm" onClick={() => runVendorTracking(vendors)} disabled={loading.vendor}>
            {loading.vendor ? '追踪中…' : '生成厂商动态'}
          </Button>
          {loading.vendor ? <Spinner /> : results.vendor && (
            <ResultCard><Markdown text={results.vendor.content} /></ResultCard>
          )}
        </div>
      )}

      {/* ── 指标查询 ── */}
      {activeTab === 'metric' && (
        <div className="space-y-5">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="font-mono text-[10px] uppercase text-gray-500 w-16">指标</span>
            <select
              value={metricKey}
              onChange={(e) => setMetricKey(e.target.value)}
              className="px-3 py-2 text-xs font-mono border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper min-w-[200px]"
            >
              {meta.metrics.map((m) => (
                <option key={m.key} value={m.key}>{m.name}</option>
              ))}
            </select>
            <select
              value={metricCategory}
              onChange={(e) => setMetricCategory(e.target.value)}
              className="px-3 py-2 text-xs font-mono border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
            >
              <option value="">通用</option>
              {Object.entries(meta.categories).map(([k, label]) => (
                <option key={k} value={k}>{label}</option>
              ))}
            </select>
          </div>
          {selectedMetric && (
            <div className="text-xs text-gray-500 bg-cream-50 border border-cream-200 rounded-md p-3">
              <span className="font-semibold text-gray-700">{selectedMetric.name}</span>
              （{selectedMetric.unit}）— {selectedMetric.definition}
              <div className="mt-1 text-gray-400">来源：{selectedMetric.source_hint}</div>
            </div>
          )}
          <Button size="sm" onClick={() => runMetricQuery(metricKey, metricCategory)} disabled={loading.metric || !metricKey}>
            {loading.metric ? '查询中…' : '查询指标'}
          </Button>
          {loading.metric ? <Spinner /> : results.metric && (
            <ResultCard><Markdown text={results.metric.content} /></ResultCard>
          )}
        </div>
      )}

      {/* ── 异动识别 ── */}
      {activeTab === 'anomaly' && (
        <div className="space-y-5">
          <Button size="sm" onClick={() => runAnomaly(timeRange)} disabled={loading.anomaly}>
            {loading.anomaly ? '识别中…' : '识别景气度异动'}
          </Button>
          {loading.anomaly ? <Spinner /> : <AnomalyResult data={results.anomaly} />}
        </div>
      )}

      {/* ── 完整报告 ── */}
      {activeTab === 'reports' && (
        <ReportsPanel
          reports={reports}
          currentReport={currentReport}
          genStatus={genStatus}
          onSelect={fetchReport}
          onDelete={deleteReport}
        />
      )}
    </div>
  )
}

// ── 结构化结果渲染 ──

function ProsperityResult({ data }: { data?: Record<string, unknown> }) {
  if (!data) return null
  if (data.error) return <p className="text-sm text-danger">{String(data.error)}</p>
  if (!('prosperity_score' in data) && data.raw) {
    return <ResultCard><Markdown text={String(data.raw)} /></ResultCard>
  }
  const score = Number(data.prosperity_score ?? 0)
  const trend = String(data.trend ?? '')
  const trendLabel = trend === 'warming' ? '升温' : trend === 'cooling' ? '降温' : '平稳'
  const themes = (data.themes as Array<Record<string, string>>) || []
  const risks = (data.key_risks as string[]) || []
  return (
    <ResultCard>
      <div className="flex items-center gap-4 mb-4">
        <div className="text-center">
          <div className="font-heading text-4xl font-bold text-copper">{score}</div>
          <div className="font-mono text-[10px] uppercase text-gray-400">景气度评分</div>
        </div>
        <Badge variant={trend === 'warming' ? 'success' : trend === 'cooling' ? 'danger' : 'warning'}>
          {trendLabel}
        </Badge>
      </div>
      {data.summary && <p className="text-sm text-gray-700 mb-4">{String(data.summary)}</p>}
      {themes.length > 0 && (
        <div className="space-y-2 mb-4">
          {themes.map((t, i) => (
            <div key={i} className="text-sm">
              <span className="font-semibold text-gray-800">{t.label || t.theme}：</span>
              <span className="text-gray-600">{t.assessment}</span>
            </div>
          ))}
        </div>
      )}
      {risks.length > 0 && (
        <div>
          <div className="font-mono text-[10px] uppercase text-gray-400 mb-1">关键风险</div>
          <ul className="list-disc pl-5 text-sm text-gray-600 space-y-1">
            {risks.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}
    </ResultCard>
  )
}

function PriceTrendResult({ data }: { data?: Record<string, unknown> }) {
  if (!data) return null
  if (data.error) return <p className="text-sm text-danger">{String(data.error)}</p>
  const cats = (data.categories as Array<Record<string, unknown>>) || []
  if (cats.length === 0 && data.raw) {
    return <ResultCard><Markdown text={String(data.raw)} /></ResultCard>
  }
  return (
    <div className="space-y-4">
      {cats.map((c, i) => {
        const anomalies = (c.anomalies as Array<Record<string, string>>) || []
        const trend = String(c.trend ?? '')
        return (
          <ResultCard key={i}>
            <div className="flex items-center gap-3 mb-2">
              <span className="font-heading text-lg font-bold">{String(c.category)}</span>
              <Badge variant={trend === 'up' ? 'success' : trend === 'down' ? 'danger' : 'warning'}>
                {trend === 'up' ? '上行' : trend === 'down' ? '下行' : '震荡'}
              </Badge>
              <span className="font-mono text-sm text-gray-700">{String(c.change_pct ?? '')}</span>
            </div>
            <p className="text-sm text-gray-600 mb-3">{String(c.narrative ?? '')}</p>
            {anomalies.length > 0 && (
              <div className="border-t border-cream-200 pt-3">
                <div className="font-mono text-[10px] uppercase text-gray-400 mb-2">异常波动</div>
                <div className="space-y-2">
                  {anomalies.map((a, j) => (
                    <div key={j} className="text-xs text-gray-600">
                      <span className="font-semibold">{a.period}</span> · {a.magnitude} — {a.scenario}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </ResultCard>
        )
      })}
    </div>
  )
}

function AnomalyResult({ data }: { data?: Record<string, unknown> }) {
  if (!data) return null
  if (data.error) return <p className="text-sm text-danger">{String(data.error)}</p>
  const anomalies = (data.anomalies as Array<Record<string, unknown>>) || []
  if (anomalies.length === 0 && data.raw) {
    return <ResultCard><Markdown text={String(data.raw)} /></ResultCard>
  }
  return (
    <ResultCard>
      {data.summary && <p className="text-sm text-gray-700 mb-4">{String(data.summary)}</p>}
      {anomalies.length === 0 ? (
        <p className="text-sm text-gray-400">未识别到明显异动</p>
      ) : (
        <div className="space-y-3">
          {anomalies.map((a, i) => {
            const sev = String(a.severity ?? 'low')
            const tickers = (a.impacted_tickers as string[]) || []
            return (
              <div key={i} className="border-b border-cream-200 pb-3 last:border-0">
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant={sev === 'high' ? 'danger' : sev === 'medium' ? 'warning' : 'success'}>{sev}</Badge>
                  <span className="font-mono text-xs text-gray-500">{String(a.date ?? '')}</span>
                  <span className="text-xs text-gray-400">{String(a.category ?? '')} · {String(a.type ?? '')}</span>
                </div>
                <p className="text-sm text-gray-700">{String(a.description ?? '')}</p>
                <p className="text-xs text-gray-500 mt-1">场景：{String(a.scenario ?? '')}</p>
                {tickers.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {tickers.map((t, j) => (
                      <span key={j} className="font-mono text-[10px] px-1.5 py-0.5 bg-cream-100 rounded text-gray-600">{t}</span>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </ResultCard>
  )
}

// ── 完整报告面板 ──

interface ReportVersionLite {
  id: number
  version: number
  status: string
  time_range: string
  report_date: string | null
  categories: string[]
}

function ReportsPanel({
  reports,
  currentReport,
  genStatus,
  onSelect,
  onDelete,
}: {
  reports: ReportVersionLite[]
  currentReport: Record<string, unknown> | null
  genStatus: string
  onSelect: (id: number) => void
  onDelete: (id: number) => void
}) {
  return (
    <div className="flex gap-6">
      {/* 版本列表 */}
      <div className="w-[240px] shrink-0 space-y-2">
        {genStatus === 'running' && (
          <div className="text-xs text-copper font-mono px-3 py-2">报告生成中…</div>
        )}
        {reports.length === 0 && <p className="text-sm text-gray-400 px-3">暂无报告</p>}
        {reports.map((r) => (
          <div
            key={r.id}
            className={`px-3 py-2.5 rounded-md border cursor-pointer transition-all ${
              currentReport?.id === r.id
                ? 'bg-orange-50 border-copper/40'
                : 'bg-white border-cream-300 hover:border-gray-400'
            }`}
            onClick={() => onSelect(r.id)}
          >
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-semibold">v{r.version}</span>
              <Badge variant={r.status === 'completed' ? 'success' : r.status === 'failed' ? 'danger' : 'warning'}>
                {r.status}
              </Badge>
            </div>
            <div className="text-[10px] text-gray-400 mt-1">
              {r.report_date?.slice(0, 10)} · {r.time_range}
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(r.id) }}
              className="text-[10px] text-gray-400 hover:text-danger mt-1"
            >
              删除
            </button>
          </div>
        ))}
      </div>

      {/* 报告详情 */}
      <div className="flex-1 min-w-0">
        {!currentReport ? (
          <p className="text-sm text-gray-400">选择左侧版本查看完整报告</p>
        ) : (
          <div className="space-y-8">
            <FullReportSection num="01" title="行业景气度">
              <ProsperityResult data={currentReport.prosperity as Record<string, unknown>} />
            </FullReportSection>
            <FullReportSection num="02" title="价格趋势">
              <PriceTrendResult data={currentReport.price_trend as Record<string, unknown>} />
            </FullReportSection>
            <FullReportSection num="03" title="供需归因">
              <ResultCard><Markdown text={String(currentReport.supply_demand ?? '')} /></ResultCard>
            </FullReportSection>
            <FullReportSection num="04" title="厂商动态">
              <ResultCard><Markdown text={String(currentReport.vendor ?? '')} /></ResultCard>
            </FullReportSection>
            <FullReportSection num="05" title="景气度异动">
              <AnomalyResult data={currentReport.anomaly as Record<string, unknown>} />
            </FullReportSection>
          </div>
        )}
      </div>
    </div>
  )
}

function FullReportSection({ num, title, children }: { num: string; title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-baseline gap-3 mb-4">
        <span className="font-mono text-xs text-copper tracking-wider">{num}</span>
        <h2 className="font-heading text-xl font-semibold">{title}</h2>
      </div>
      {children}
    </div>
  )
}
