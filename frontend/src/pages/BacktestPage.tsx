import { useState } from 'react'
import { api } from '@/api/client'
import { Card, CardHeader, Button, Input } from '@/components/ui'

const DEFAULT_STRATEGY = `def strategy(data):
    """均线交叉策略：MA5 上穿 MA20 买入，下穿卖出"""
    import pandas as pd
    ma5 = data['Close'].rolling(5).mean()
    ma20 = data['Close'].rolling(20).mean()
    signals = pd.Series(0, index=data.index)
    signals[(ma5 > ma20) & (ma5.shift(1) <= ma20.shift(1))] = 1
    signals[(ma5 < ma20) & (ma5.shift(1) >= ma20.shift(1))] = -1
    return signals`

interface BacktestResult {
  total_return: number
  annual_return: number
  max_drawdown: number
  sharpe_ratio: number
  win_rate: number
  total_trades: number
  profit_trades: number
  loss_trades: number
  equity_curve: number[]
  dates: string[]
  buy_signals: number[]
  sell_signals: number[]
}

export default function BacktestPage() {
  const [code, setCode] = useState(DEFAULT_STRATEGY)
  const [symbol, setSymbol] = useState('AAPL')
  const [period, setPeriod] = useState('1y')
  const [capital, setCapital] = useState('100000')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<BacktestResult | null>(null)

  const runBacktest = async () => {
    if (!symbol.trim()) { setError('请输入股票代码'); return }
    setLoading(true)
    setError('')
    setResult(null)

    try {
      const res = await api.post('/api/backtest/run', {
        code,
        symbol: symbol.trim().toUpperCase(),
        period,
        initial_capital: parseFloat(capital) || 100000,
        position_mode: 'full',
        position_pct: 100,
        fixed_amount: 10000,
      })
      if (res.data.success) {
        setResult(res.data.result)
      } else {
        setError(res.data.error || '回测失败')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '网络错误'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const fmtPct = (v: number) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`

  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          Strategy Backtest
        </span>
        <h1 className="page-title">策略<span className="text-copper">回测</span></h1>
        <p className="text-sm text-gray-500 mt-2">编写 Python 策略函数，在历史数据上回测验证</p>
      </div>

      {/* Parameters */}
      <Card className="mb-6">
        <CardHeader title="参数配置" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Input label="股票代码" value={symbol} onChange={e => setSymbol(e.target.value)} placeholder="AAPL" />
          <div className="space-y-1.5">
            <label className="block font-mono text-[10px] tracking-[1.5px] uppercase text-gray-500">时间周期</label>
            <select
              value={period}
              onChange={e => setPeriod(e.target.value)}
              className="w-full px-3.5 py-2.5 text-sm bg-white border border-cream-300 rounded-md focus:outline-none focus:border-copper"
            >
              <option value="6mo">6 个月</option>
              <option value="1y">1 年</option>
              <option value="2y">2 年</option>
              <option value="5y">5 年</option>
            </select>
          </div>
          <Input label="初始资金" type="number" value={capital} onChange={e => setCapital(e.target.value)} />
          <div className="flex items-end">
            <Button variant="primary" className="w-full" onClick={runBacktest} disabled={loading}>
              {loading ? '回测中...' : '▶ 执行回测'}
            </Button>
          </div>
        </div>
      </Card>

      {/* Code Editor */}
      <Card className="mb-6">
        <CardHeader title="策略代码" label="Python" />
        <textarea
          value={code}
          onChange={e => setCode(e.target.value)}
          className="w-full min-h-[300px] p-4 font-mono text-xs leading-relaxed bg-cream-50 border border-cream-300 rounded-lg resize-y focus:outline-none focus:border-copper"
          spellCheck={false}
        />
      </Card>

      {/* Error */}
      {error && (
        <Card className="mb-6 border-danger/30 bg-red-50/30">
          <p className="text-sm text-danger font-mono">{error}</p>
        </Card>
      )}

      {/* Results */}
      {result && (
        <>
          <Card className="mb-6">
            <CardHeader title="回测结果" label="Performance Metrics" />
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricCard label="总收益" value={fmtPct(result.total_return)} positive={result.total_return >= 0} />
              <MetricCard label="年化收益" value={fmtPct(result.annual_return)} positive={result.annual_return >= 0} />
              <MetricCard label="最大回撤" value={fmtPct(result.max_drawdown)} positive={false} />
              <MetricCard label="夏普比率" value={result.sharpe_ratio.toFixed(2)} positive={result.sharpe_ratio >= 1} />
              <MetricCard label="胜率" value={`${(result.win_rate * 100).toFixed(1)}%`} positive={result.win_rate >= 0.5} />
              <MetricCard label="总交易" value={String(result.total_trades)} />
              <MetricCard label="盈利交易" value={String(result.profit_trades)} positive />
              <MetricCard label="亏损交易" value={String(result.loss_trades)} positive={false} />
            </div>
          </Card>

          {result.equity_curve && result.equity_curve.length > 0 && (
            <Card>
              <CardHeader title="权益曲线" label="Equity Curve" />
              <div className="h-[300px] bg-cream-50 rounded-lg flex items-center justify-center text-sm text-gray-500">
                <p>ECharts 图表组件将在安装依赖后渲染</p>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

function MetricCard({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  const colorClass = positive === undefined ? 'text-gray-900' : positive ? 'text-success' : 'text-danger'
  return (
    <div className="p-4 bg-cream-50 rounded-lg border border-cream-200">
      <div className="font-mono text-[10px] tracking-wider uppercase text-gray-500 mb-1">{label}</div>
      <div className={`font-heading text-xl font-bold ${colorClass}`}>{value}</div>
    </div>
  )
}
