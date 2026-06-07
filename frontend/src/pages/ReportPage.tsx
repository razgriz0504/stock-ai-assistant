import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Card, CardHeader, Button, Badge } from '@/components/ui'

interface ReportVersion {
  id: number
  version: string
  report_date: string
  model_name: string
  trigger: string
}

interface ReportData {
  id: number
  version: string
  report_date: string
  model_name: string
  market: { indices: Array<{ name: string; symbol: string; price: number; weekly_change: number; weekly_change_pct: number }>; ai_market_summary: string }
  capital: { ai_capital_summary: string }
  geopolitics: { ai_geopolitics_summary: string }
  yield_curve: { yield_curve: Record<string, unknown>; ai_yield_curve_summary: string }
  sector: { sectors: Array<{ name: string; etf: string; weekly_return: number }>; ai_sector_summary: string }
  stocks: { watchlist_scores: Array<Record<string, unknown>>; hot_stock_scores: Array<Record<string, unknown>> }
  x_monitor: { x_tweets_data: Record<string, unknown>; ai_x_monitor_summary: string }
  sector_strength: { enhanced_sector_data: Record<string, unknown>; ai_sector_strength_summary: string }
}

const sections = [
  { id: 'market', num: '01', title: '大盘综述' },
  { id: 'capital', num: '02', title: '资金面' },
  { id: 'geopolitics', num: '03', title: '国际局势' },
  { id: 'yield_curve', num: '04', title: '收益率曲线' },
  { id: 'sector_strength', num: '05', title: '板块强度' },
  { id: 'sector', num: '06', title: '行业轮动' },
  { id: 'stocks', num: '07', title: '个股评分' },
  { id: 'x_monitor', num: '08', title: 'X 舆情' },
]

export default function ReportPage() {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [activeSection, setActiveSection] = useState('market')

  // Versions list
  const { data: versions } = useQuery<ReportVersion[]>({
    queryKey: ['report-versions'],
    queryFn: async () => (await api.get('/api/report/versions')).data,
  })

  // Report data
  const reportId = selectedId || (versions && versions.length > 0 ? versions[0]?.id : null)
  const { data: report, isLoading } = useQuery<ReportData>({
    queryKey: ['report', reportId],
    queryFn: async () => (await api.get(`/api/report/${reportId}`)).data,
    enabled: !!reportId,
  })

  return (
    <div>
      {/* Header */}
      <div className="flex items-end justify-between mb-8">
        <div>
          <span className="section-label flex items-center gap-2 mb-3">
            <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
            Weekly Report
          </span>
          <h1 className="page-title">投研<span className="text-copper">周报</span></h1>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={reportId || ''}
            onChange={e => setSelectedId(Number(e.target.value))}
            className="px-3 py-2 text-xs font-mono border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper min-w-[180px]"
          >
            {versions?.map(v => (
              <option key={v.id} value={v.id}>
                {v.version} — {v.report_date?.slice(0, 10)}
              </option>
            ))}
          </select>
          <Button size="sm" onClick={() => window.open('/report-admin', '_self')}>
            管理
          </Button>
        </div>
      </div>

      {isLoading || !report ? (
        <div className="flex justify-center py-20">
          <div className="w-6 h-6 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
        </div>
      ) : (
        <div className="flex gap-6">
          {/* Section nav */}
          <nav className="hidden lg:block w-[180px] shrink-0 sticky top-8 self-start">
            <div className="space-y-1">
              {sections.map(s => (
                <button
                  key={s.id}
                  onClick={() => setActiveSection(s.id)}
                  className={`w-full text-left px-3 py-2 rounded-md text-xs transition-all ${
                    activeSection === s.id
                      ? 'bg-orange-50 text-copper font-semibold border border-copper/20'
                      : 'text-gray-500 hover:text-gray-900 hover:bg-cream-200'
                  }`}
                >
                  <span className="font-mono text-[10px] mr-2">{s.num}</span>
                  {s.title}
                </button>
              ))}
            </div>
          </nav>

          {/* Content */}
          <div className="flex-1 min-w-0 space-y-8">
            {/* Market */}
            {(activeSection === 'market' || !activeSection) && (
              <ReportSection num="01" title="大盘综述">
                {report.market.indices && report.market.indices.length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                    {report.market.indices.map((idx) => (
                      <div key={idx.symbol} className="p-4 bg-cream-50 border border-cream-200 rounded-lg">
                        <div className="font-heading text-base font-bold">{idx.name}</div>
                        <div className="font-mono text-[10px] text-gray-400 mb-3">{idx.symbol}</div>
                        <div className="font-heading text-2xl font-bold tracking-tight mb-1">
                          {idx.price?.toLocaleString()}
                        </div>
                        <div className={`font-mono text-xs font-medium ${idx.weekly_change_pct >= 0 ? 'text-success' : 'text-danger'}`}>
                          {idx.weekly_change_pct >= 0 ? '+' : ''}{idx.weekly_change_pct?.toFixed(2)}%
                          <span className="text-gray-400 ml-2">
                            ({idx.weekly_change >= 0 ? '+' : ''}{idx.weekly_change?.toFixed(2)})
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <AiSummary text={report.market.ai_market_summary} />
              </ReportSection>
            )}

            {activeSection === 'capital' && (
              <ReportSection num="02" title="资金面分析">
                <AiSummary text={report.capital.ai_capital_summary} />
              </ReportSection>
            )}

            {activeSection === 'geopolitics' && (
              <ReportSection num="03" title="国际局势">
                <AiSummary text={report.geopolitics.ai_geopolitics_summary} />
              </ReportSection>
            )}

            {activeSection === 'yield_curve' && (
              <ReportSection num="04" title="收益率曲线">
                <AiSummary text={report.yield_curve.ai_yield_curve_summary} />
              </ReportSection>
            )}

            {activeSection === 'sector_strength' && (
              <ReportSection num="05" title="板块强度">
                <AiSummary text={report.sector_strength?.ai_sector_strength_summary} />
              </ReportSection>
            )}

            {activeSection === 'sector' && (
              <ReportSection num="06" title="行业轮动">
                {report.sector.sectors && report.sector.sectors.length > 0 && (
                  <div className="mb-6 overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-cream-300">
                          <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">板块</th>
                          <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">ETF</th>
                          <th className="text-right px-3 py-2 font-mono text-[10px] uppercase text-gray-500">周涨跌</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.sector.sectors.map((s, i) => (
                          <tr key={i} className="border-b border-cream-200">
                            <td className="px-3 py-2 font-heading font-semibold text-sm">{s.name}</td>
                            <td className="px-3 py-2 font-mono text-xs text-gray-400">{s.etf}</td>
                            <td className={`px-3 py-2 text-right font-mono text-xs font-medium ${s.weekly_return >= 0 ? 'text-success' : 'text-danger'}`}>
                              {s.weekly_return >= 0 ? '+' : ''}{s.weekly_return?.toFixed(2)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <AiSummary text={report.sector.ai_sector_summary} />
              </ReportSection>
            )}

            {activeSection === 'stocks' && (
              <ReportSection num="07" title="个股评分">
                <StockScores label="关注列表" scores={report.stocks.watchlist_scores} />
                <StockScores label="热门股票" scores={report.stocks.hot_stock_scores} />
              </ReportSection>
            )}

            {activeSection === 'x_monitor' && (
              <ReportSection num="08" title="X 舆情">
                <AiSummary text={report.x_monitor?.ai_x_monitor_summary} />
              </ReportSection>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function ReportSection({ num, title, children }: { num: string; title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-baseline gap-3 mb-6">
        <span className="font-mono text-xs text-copper tracking-wider">{num}</span>
        <h2 className="font-heading text-xl font-semibold">{title}</h2>
      </div>
      {children}
    </div>
  )
}

function AiSummary({ text }: { text?: string }) {
  if (!text) return <p className="text-sm text-gray-400">暂无 AI 分析</p>
  return (
    <div className="relative pl-7 py-5 px-5 bg-white border border-cream-300 rounded-lg">
      <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-copper rounded-l-lg" />
      <div className="font-mono text-[10px] tracking-[1.5px] uppercase text-copper mb-3">AI Analysis</div>
      <div className="text-sm leading-[1.8] text-gray-700 prose prose-sm max-w-none">
        {text.split('\n').map((line, i) => (
          <p key={i} className={line.trim() ? 'mb-2' : 'mb-0'}>{line || '\u00A0'}</p>
        ))}
      </div>
    </div>
  )
}

function StockScores({ label, scores }: { label: string; scores: Array<Record<string, unknown>> }) {
  if (!scores || scores.length === 0) return null
  return (
    <div className="mb-6">
      <h4 className="font-mono text-[10px] tracking-wider uppercase text-gray-500 mb-3">{label}</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-cream-300">
              <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">代码</th>
              <th className="text-right px-3 py-2 font-mono text-[10px] uppercase text-gray-500">评分</th>
              <th className="text-right px-3 py-2 font-mono text-[10px] uppercase text-gray-500">价格</th>
              <th className="text-right px-3 py-2 font-mono text-[10px] uppercase text-gray-500">周涨跌</th>
            </tr>
          </thead>
          <tbody>
            {scores.map((s, i) => (
              <tr key={i} className="border-b border-cream-200">
                <td className="px-3 py-2 font-mono font-semibold text-xs">{String(s.symbol || '')}</td>
                <td className="px-3 py-2 text-right">
                  <Badge variant={Number(s.score || 0) >= 70 ? 'success' : Number(s.score || 0) >= 40 ? 'warning' : 'danger'}>
                    {String(s.score || '-')}
                  </Badge>
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">${Number(s.price || 0).toFixed(2)}</td>
                <td className={`px-3 py-2 text-right font-mono text-xs font-medium ${Number(s.weekly_change_pct || 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                  {Number(s.weekly_change_pct || 0) >= 0 ? '+' : ''}{Number(s.weekly_change_pct || 0).toFixed(2)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
