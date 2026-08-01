import { FormEvent, useCallback, useEffect, useState } from 'react'
import { api } from '@/api/client'
import { Card, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

// ─── 类型 ───

interface Settings {
  account_size: number
  risk_pct_green: number
  risk_pct_yellow: number
  risk_pct_red: number
  max_position_pct: number
  max_positions: number
}

interface Position {
  symbol: string
  qty: number
  avg_cost: number
  cost_value: number
  realized_pnl: number
  initial_stop: number | null
  first_buy_date: string | null
  current_price: number | null
  change_pct: number | null
  stop_price: number | null
  rs_percentile: number | null
  market_value: number | null
  unrealized_pnl: number | null
  unrealized_pct: number | null
  stop_distance_pct: number | null
  open_risk: number | null
  r_multiple: number | null
}

interface PositionSummary {
  position_count: number
  max_positions: number
  account_size: number
  total_market_value: number
  exposure_pct: number | null
  total_unrealized_pnl: number
  total_realized_pnl: number
  total_open_risk: number
  open_risk_pct: number | null
}

interface Trade {
  id: number
  symbol: string
  side: string
  qty: number
  price: number
  commission: number
  trade_date: string
  setup: string
  initial_stop: number | null
  note: string
}

interface SizeResult {
  shares: number
  position_value: number
  position_pct: number
  risk_amount: number
  risk_pct_used: number
  stop_distance_pct: number
  capped: boolean
  warnings: string[]
  risk_pct: number
  regime_state: string | null
}

const SETUP_OPTIONS = [
  { value: 'vcp_breakout', label: 'VCP 突破' },
  { value: 'pullback', label: '回踩买点' },
  { value: 'breakout', label: '其他突破' },
  { value: 'other', label: '其他' },
]

const fmtMoney = (v: number | null | undefined) =>
  v == null ? '--' : `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`

const pnlClass = (v: number | null | undefined) =>
  v == null ? 'text-gray-400' : v >= 0 ? 'text-emerald-600' : 'text-red-500'

// ─── 页面 ───

export default function PortfolioPage() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [summary, setSummary] = useState<PositionSummary | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)

  // 记一笔表单
  const [fSymbol, setFSymbol] = useState('')
  const [fSide, setFSide] = useState<'buy' | 'sell'>('buy')
  const [fQty, setFQty] = useState('')
  const [fPrice, setFPrice] = useState('')
  const [fCommission, setFCommission] = useState('0')
  const [fDate, setFDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [fSetup, setFSetup] = useState('vcp_breakout')
  const [fStop, setFStop] = useState('')
  const [fNote, setFNote] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // 仓位计算器
  const [cEntry, setCEntry] = useState('')
  const [cStop, setCStop] = useState('')
  const [cRisk, setCRisk] = useState('')       // 留空=按红绿灯自动
  const [sizeResult, setSizeResult] = useState<SizeResult | null>(null)
  const [sizing, setSizing] = useState(false)

  function flash(msg: string, type: 'ok' | 'err' = 'ok') {
    setStatus({ msg, type })
    setTimeout(() => setStatus(null), 4000)
  }

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [setRes, posRes, tradeRes] = await Promise.all([
        api.get('/api/portfolio/settings'),
        api.get('/api/portfolio/positions', { timeout: 120_000 }),
        api.get('/api/portfolio/trades', { params: { limit: 100 } }),
      ])
      setSettings(setRes.data.settings)
      setPositions(posRes.data.positions || [])
      setSummary(posRes.data.summary || null)
      setWarnings(posRes.data.warnings || [])
      setTrades(tradeRes.data.trades || [])
    } catch {
      flash('加载失败，请稍后重试', 'err')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  // ── 设置保存 ──
  async function saveSettings() {
    if (!settings) return
    try {
      await api.put('/api/portfolio/settings', settings)
      flash('风控设置已保存')
    } catch {
      flash('设置保存失败', 'err')
    }
  }

  // ── 记一笔 ──
  async function submitTrade(e: FormEvent) {
    e.preventDefault()
    const qty = parseFloat(fQty)
    const price = parseFloat(fPrice)
    if (!fSymbol.trim() || !qty || qty <= 0 || !price || price <= 0) {
      flash('请填写正确的代码 / 数量 / 价格', 'err')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/api/portfolio/trades', {
        symbol: fSymbol.trim().toUpperCase(),
        side: fSide,
        qty,
        price,
        commission: parseFloat(fCommission) || 0,
        trade_date: fDate,
        setup: fSide === 'buy' ? fSetup : '',
        initial_stop: fSide === 'buy' && fStop ? parseFloat(fStop) : null,
        note: fNote,
      })
      flash(`已记录 ${fSide === 'buy' ? '买入' : '卖出'} ${fSymbol.toUpperCase()} × ${qty}`)
      setFSymbol(''); setFQty(''); setFPrice(''); setFStop(''); setFNote('')
      fetchAll()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      flash(typeof detail === 'string' ? detail : '记录失败', 'err')
    } finally {
      setSubmitting(false)
    }
  }

  async function deleteTrade(id: number) {
    if (!window.confirm('确定删除这条交易记录？持仓将重新聚合。')) return
    try {
      await api.delete(`/api/portfolio/trades/${id}`)
      flash('已删除')
      fetchAll()
    } catch {
      flash('删除失败', 'err')
    }
  }

  async function updateStop(symbol: string, current: number | null) {
    const input = window.prompt(`更新 ${symbol} 的止损价`, current != null ? String(current) : '')
    if (input == null) return
    const stop = parseFloat(input)
    if (!stop || stop <= 0) {
      flash('止损价无效', 'err')
      return
    }
    try {
      await api.put(`/api/portfolio/positions/${symbol}/stop`, { stop_price: stop })
      flash(`${symbol} 止损已更新为 $${stop}`)
      fetchAll()
    } catch {
      flash('止损更新失败', 'err')
    }
  }

  // ── 仓位计算 ──
  async function calcSize() {
    const entry = parseFloat(cEntry)
    const stop = parseFloat(cStop)
    if (!entry || !stop || entry <= 0 || stop <= 0) {
      flash('请填写入场价与止损价', 'err')
      return
    }
    setSizing(true)
    try {
      const res = await api.post('/api/portfolio/position-size', {
        entry,
        stop,
        risk_pct: cRisk ? parseFloat(cRisk) : null,
      })
      setSizeResult(res.data)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      flash(typeof detail === 'string' ? detail : '计算失败', 'err')
      setSizeResult(null)
    } finally {
      setSizing(false)
    }
  }

  const regimeLight: Record<string, string> = { green: '🟢', yellow: '🟡', red: '🔴' }

  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          Portfolio & Journal
        </span>
        <h1 className="page-title">持仓<span className="text-copper">日志</span></h1>
        <p className="text-sm text-gray-500 mt-2">
          交易流水（平均成本法聚合）· 固定风险法仓位 · 止损与 R-multiple 跟踪
        </p>
      </div>

      {status && (
        <div className={`mb-6 px-4 py-3 rounded-md text-sm border ${
          status.type === 'ok'
            ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
            : 'bg-red-50 border-red-200 text-red-600'
        }`}>
          {status.msg}
        </div>
      )}

      {warnings.length > 0 && (
        <div className="mb-6 px-4 py-3 bg-amber-50 border border-amber-200 rounded-md text-xs text-amber-700 space-y-0.5">
          {warnings.map((w, i) => <p key={i}>⚠️ {w}</p>)}
        </div>
      )}

      {/* 组合概览 */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-6">
          {[
            { label: '账户资金', value: fmtMoney(summary.account_size), cls: '' },
            { label: '持仓市值', value: fmtMoney(summary.total_market_value), cls: '' },
            { label: '仓位敞口', value: summary.exposure_pct != null ? `${summary.exposure_pct}%` : '--', cls: '' },
            { label: '浮动盈亏', value: fmtMoney(summary.total_unrealized_pnl), cls: pnlClass(summary.total_unrealized_pnl) },
            { label: '已实现盈亏', value: fmtMoney(summary.total_realized_pnl), cls: pnlClass(summary.total_realized_pnl) },
            { label: '敞口风险', value: summary.open_risk_pct != null ? `${fmtMoney(summary.total_open_risk)} (${summary.open_risk_pct}%)` : '--', cls: 'text-amber-700' },
          ].map((it) => (
            <div key={it.label} className="bg-white border border-cream-300 rounded-lg px-4 py-3 shadow-card">
              <div className="text-[10px] text-gray-500 uppercase tracking-wide font-mono">{it.label}</div>
              <div className={`font-mono text-sm font-bold mt-1 ${it.cls}`}>{it.value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* 仓位计算器 */}
        <Card>
          <CardHeader
            title="仓位计算器"
            label="Position Sizing"
            description="固定风险法：股数 = 账户 × 风险% ÷ (入场价 − 止损价)"
          />
          <div className="grid grid-cols-3 gap-3">
            <Input label="入场价 $" type="number" step="0.01" value={cEntry}
                   onChange={(e) => setCEntry(e.target.value)} placeholder="100.00" />
            <Input label="止损价 $" type="number" step="0.01" value={cStop}
                   onChange={(e) => setCStop(e.target.value)} placeholder="93.00" />
            <Input label="风险 % (留空=红绿灯)" type="number" step="0.05" value={cRisk}
                   onChange={(e) => setCRisk(e.target.value)} placeholder="自动" />
          </div>
          <Button variant="primary" className="mt-4" onClick={calcSize} disabled={sizing}>
            {sizing ? '计算中...' : '计算建议仓位'}
          </Button>
          {sizeResult && (
            <div className="mt-4 bg-cream-100 border border-cream-300 rounded-md p-4 space-y-2">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-2xl font-bold text-copper">{sizeResult.shares} 股</span>
                <span className="font-mono text-sm text-gray-600">
                  ≈ {fmtMoney(sizeResult.position_value)}（{sizeResult.position_pct}% 仓位）
                </span>
              </div>
              <div className="text-xs text-gray-600 space-y-1">
                <p>
                  单笔风险 {fmtMoney(sizeResult.risk_amount)}（{sizeResult.risk_pct_used}% 账户）
                  · 止损距离 {sizeResult.stop_distance_pct}%
                </p>
                <p>
                  风险取值 {sizeResult.risk_pct}%
                  {sizeResult.regime_state && (
                    <> · 市场状态 {regimeLight[sizeResult.regime_state] ?? ''} {sizeResult.regime_state.toUpperCase()}</>
                  )}
                </p>
                {sizeResult.warnings.map((w, i) => (
                  <p key={i} className="text-amber-700">⚠️ {w}</p>
                ))}
              </div>
            </div>
          )}
        </Card>

        {/* 风控设置 */}
        <Card>
          <CardHeader
            title="风控设置"
            label="Risk Settings"
            description="单笔风险 % 按市场红绿灯自动切换"
            action={<Button size="sm" onClick={saveSettings}>保存</Button>}
          />
          {settings && (
            <div className="grid grid-cols-3 gap-3">
              <Input label="账户资金 $" type="number" value={settings.account_size}
                     onChange={(e) => setSettings({ ...settings, account_size: parseFloat(e.target.value) || 0 })} />
              <Input label="🟢 绿灯风险 %" type="number" step="0.05" value={settings.risk_pct_green}
                     onChange={(e) => setSettings({ ...settings, risk_pct_green: parseFloat(e.target.value) || 0 })} />
              <Input label="🟡 黄灯风险 %" type="number" step="0.05" value={settings.risk_pct_yellow}
                     onChange={(e) => setSettings({ ...settings, risk_pct_yellow: parseFloat(e.target.value) || 0 })} />
              <Input label="🔴 红灯风险 %" type="number" step="0.05" value={settings.risk_pct_red}
                     onChange={(e) => setSettings({ ...settings, risk_pct_red: parseFloat(e.target.value) || 0 })} />
              <Input label="单仓上限 %" type="number" value={settings.max_position_pct}
                     onChange={(e) => setSettings({ ...settings, max_position_pct: parseFloat(e.target.value) || 0 })} />
              <Input label="最大持仓数" type="number" value={settings.max_positions}
                     onChange={(e) => setSettings({ ...settings, max_positions: parseInt(e.target.value) || 0 })} />
            </div>
          )}
        </Card>
      </div>

      {/* 当前持仓 */}
      <Card className="mb-6">
        <CardHeader
          title="当前持仓"
          label="Open Positions"
          description={summary ? `${summary.position_count} / ${summary.max_positions} 个持仓` : undefined}
          action={<Button size="sm" onClick={fetchAll} disabled={loading}>{loading ? '刷新中...' : '刷新'}</Button>}
        />
        {positions.length === 0 ? (
          <p className="text-sm text-gray-500 py-4">暂无持仓，在下方记录第一笔买入后自动聚合。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b border-cream-300">
                  {['代码', '数量', '均价', '现价', '市值', '浮动盈亏', '止损价', '距止损', 'R', 'RS', ''].map((h) => (
                    <th key={h} className="font-mono text-[10px] uppercase tracking-wide text-gray-500 py-2 pr-3">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.symbol} className="border-b border-cream-200 hover:bg-cream-100">
                    <td className="py-2.5 pr-3 font-mono font-semibold">{p.symbol}</td>
                    <td className="py-2.5 pr-3 font-mono">{p.qty}</td>
                    <td className="py-2.5 pr-3 font-mono">${p.avg_cost.toFixed(2)}</td>
                    <td className="py-2.5 pr-3 font-mono">
                      {p.current_price != null ? `$${p.current_price.toFixed(2)}` : '--'}
                      {p.change_pct != null && (
                        <span className={`ml-1 text-xs ${pnlClass(p.change_pct)}`}>
                          {p.change_pct >= 0 ? '+' : ''}{p.change_pct}%
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 pr-3 font-mono">{fmtMoney(p.market_value)}</td>
                    <td className={`py-2.5 pr-3 font-mono ${pnlClass(p.unrealized_pnl)}`}>
                      {fmtMoney(p.unrealized_pnl)}
                      {p.unrealized_pct != null && ` (${p.unrealized_pct >= 0 ? '+' : ''}${p.unrealized_pct}%)`}
                    </td>
                    <td className="py-2.5 pr-3 font-mono">
                      {p.stop_price != null ? `$${p.stop_price.toFixed(2)}` : '--'}
                    </td>
                    <td className={`py-2.5 pr-3 font-mono ${
                      p.stop_distance_pct != null && p.stop_distance_pct < 3 ? 'text-red-500 font-bold' : ''
                    }`}>
                      {p.stop_distance_pct != null ? `${p.stop_distance_pct}%` : '--'}
                    </td>
                    <td className={`py-2.5 pr-3 font-mono ${pnlClass(p.r_multiple)}`}>
                      {p.r_multiple != null ? `${p.r_multiple}R` : '--'}
                    </td>
                    <td className={`py-2.5 pr-3 font-mono ${
                      p.rs_percentile != null && p.rs_percentile < 70 ? 'text-amber-600' : ''
                    }`}>
                      {p.rs_percentile != null ? Math.round(p.rs_percentile) : '--'}
                    </td>
                    <td className="py-2.5 text-right">
                      <Button size="sm" variant="ghost" onClick={() => updateStop(p.symbol, p.stop_price)}>
                        改止损
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* 记一笔 */}
      <Card className="mb-6">
        <CardHeader title="记一笔" label="New Trade" description="买入时填写初始止损价，将自动同步到持仓止损跟踪" />
        <form onSubmit={submitTrade}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Input label="代码" value={fSymbol} onChange={(e) => setFSymbol(e.target.value)} placeholder="NVDA" />
            <div className="space-y-1.5">
              <label className="block font-mono text-[10px] tracking-[1.5px] uppercase text-gray-500">方向</label>
              <div className="flex rounded-md border border-cream-300 overflow-hidden">
                {(['buy', 'sell'] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setFSide(s)}
                    className={`flex-1 py-2.5 text-sm font-mono transition-colors ${
                      fSide === s
                        ? s === 'buy' ? 'bg-emerald-600 text-white' : 'bg-red-500 text-white'
                        : 'bg-white text-gray-500 hover:bg-cream-100'
                    }`}
                  >
                    {s === 'buy' ? '买入' : '卖出'}
                  </button>
                ))}
              </div>
            </div>
            <Input label="数量" type="number" step="1" value={fQty} onChange={(e) => setFQty(e.target.value)} placeholder="100" />
            <Input label="成交价 $" type="number" step="0.01" value={fPrice} onChange={(e) => setFPrice(e.target.value)} placeholder="100.00" />
            <Input label="日期" type="date" value={fDate} onChange={(e) => setFDate(e.target.value)} />
            <Input label="佣金 $" type="number" step="0.01" value={fCommission} onChange={(e) => setFCommission(e.target.value)} />
            {fSide === 'buy' && (
              <>
                <div className="space-y-1.5">
                  <label className="block font-mono text-[10px] tracking-[1.5px] uppercase text-gray-500">入场形态</label>
                  <select
                    value={fSetup}
                    onChange={(e) => setFSetup(e.target.value)}
                    className="w-full px-3.5 py-2.5 text-sm bg-white border border-cream-300 rounded-md focus:outline-none focus:border-copper"
                  >
                    {SETUP_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <Input label="初始止损 $" type="number" step="0.01" value={fStop}
                       onChange={(e) => setFStop(e.target.value)} placeholder="93.00" />
              </>
            )}
          </div>
          <div className="mt-3">
            <Input label="备注 / 入场理由" value={fNote} onChange={(e) => setFNote(e.target.value)}
                   placeholder="如：第 3 次收缩后放量突破 Pivot，市场绿灯" />
          </div>
          <Button type="submit" variant="primary" className="mt-4" disabled={submitting}>
            {submitting ? '提交中...' : '记录交易'}
          </Button>
        </form>
      </Card>

      {/* 交易流水 */}
      <Card>
        <CardHeader title="交易流水" label="Trade Log" description="最近 100 条" />
        {trades.length === 0 ? (
          <p className="text-sm text-gray-500 py-4">暂无交易记录。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b border-cream-300">
                  {['日期', '代码', '方向', '数量', '价格', '佣金', '形态', '止损', '备注', ''].map((h) => (
                    <th key={h} className="font-mono text-[10px] uppercase tracking-wide text-gray-500 py-2 pr-3">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr key={t.id} className="border-b border-cream-200 hover:bg-cream-100">
                    <td className="py-2 pr-3 font-mono text-xs">{t.trade_date}</td>
                    <td className="py-2 pr-3 font-mono font-semibold">{t.symbol}</td>
                    <td className={`py-2 pr-3 font-mono text-xs ${t.side === 'buy' ? 'text-emerald-600' : 'text-red-500'}`}>
                      {t.side === 'buy' ? '买入' : '卖出'}
                    </td>
                    <td className="py-2 pr-3 font-mono">{t.qty}</td>
                    <td className="py-2 pr-3 font-mono">${t.price.toFixed(2)}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{t.commission ? `$${t.commission.toFixed(2)}` : '--'}</td>
                    <td className="py-2 pr-3 text-xs">
                      {SETUP_OPTIONS.find((o) => o.value === t.setup)?.label || (t.setup || '--')}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">
                      {t.initial_stop != null ? `$${t.initial_stop.toFixed(2)}` : '--'}
                    </td>
                    <td className="py-2 pr-3 text-xs text-gray-500 max-w-[200px] truncate" title={t.note}>
                      {t.note || '--'}
                    </td>
                    <td className="py-2 text-right">
                      <Button size="sm" variant="ghost" onClick={() => deleteTrade(t.id)}>删除</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
