/**
 * 净 Gamma 敞口（Net GEX）看板。
 * 后端接口见 [gex_api.py](file:///d:/Codes/stock-ai-assistant/app/api/gex_api.py)。
 * 数据源依赖富途 OpenD（只读）：期权链静态信息 + 快照行情。
 *
 * 口径说明：Call GEX 记正 / Put GEX 记负（公共数据标准约定，dealer 持仓方向
 * 为模型假设）。Net GEX > 0 对应 dealer 净长 gamma（对冲盘逆势、平抑波动），
 * < 0 对应净短 gamma（顺势、放大波动）。Zero Gamma 为净敞口过零位。
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { EChartsCoreOption } from 'echarts'
import { Card, CardHeader, Button, Input, Badge } from '@/components/ui'
import { useECharts } from '@/components/charts/useECharts'
import {
  fetchGexStatus,
  fetchGexAnalysis,
  type GexAnalysis,
  type GexStrike,
  type GexExpiry,
} from '@/api/gex'

// ─── 工具 ───
function fmtMoney(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : v > 0 ? '+' : ''
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(digits)}B`
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(digits)}M`
  return `${sign}$${abs.toFixed(0)}`
}

function gexColor(v: number): string {
  // 美股惯例：正=红、负=绿
  if (v > 0) return 'text-red-600'
  if (v < 0) return 'text-green-600'
  return 'text-gray-700'
}

function fmtInt(v: number | undefined): string {
  return v === undefined ? '-' : v.toLocaleString('en-US')
}

// ─── 图 1：按行权价 GEX 分布（Call / Put 柱状 + Zero Gamma 线） ───
function GexStrikeChart({ strikes, zeroGamma }: { strikes: GexStrike[]; zeroGamma: number | null }) {
  const option = (): EChartsCoreOption => ({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (v: unknown) => fmtMoney(Number(v)),
    },
    legend: { data: ['Call GEX', 'Put GEX'], top: 0 },
    grid: { left: 70, right: 16, top: 32, bottom: 28 },
    xAxis: {
      type: 'category',
      data: strikes.map((s) => s.strike),
      axisLabel: { rotate: 45, fontSize: 10 },
      name: '行权价',
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: (v: number) => fmtMoney(v, 0) },
      name: 'GEX / 1%',
    },
    series: [
      {
        name: 'Call GEX',
        type: 'bar',
        data: strikes.map((s) => s.call_gex_1pct),
        itemStyle: { color: '#e53935' },
      },
      {
        name: 'Put GEX',
        type: 'bar',
        data: strikes.map((s) => s.put_gex_1pct),
        itemStyle: { color: '#1e88e5' },
      },
      ...(zeroGamma === null
        ? []
        : [
            {
              name: 'Zero Gamma',
              type: 'line',
              markLine: {
                symbol: 'none',
                silent: true,
                lineStyle: { color: '#b87333', type: 'dashed', width: 1.5 },
                label: { formatter: `Zero Gamma ${zeroGamma}`, fontSize: 10 },
                data: [{ xAxis: String(zeroGamma) }],
              },
            },
          ]),
    ],
  })

  const chartRef = useECharts(option, [strikes, zeroGamma])
  return <div ref={chartRef} className="h-[320px] w-full" />
}

// ─── 图 2：Net GEX 扫描曲线（vs 假想 spot） ───
function GexCurveChart({ analysis }: { analysis: GexAnalysis }) {
  const { curve, spot, zero_gamma } = analysis
  const option = (): EChartsCoreOption => {
    // markLine 数据直接内联构造，避免中间数组类型推断问题（严格 TS 模式）
    const markLineData = [
      { yAxis: 0, label: { formatter: '零轴' }, lineStyle: { color: '#9ca3af' } },
      {
        xAxis: spot,
        label: { formatter: `现货 ${spot}` },
        lineStyle: { color: '#1e88e5', type: 'dashed' },
      },
      ...(zero_gamma === null
        ? []
        : [
            {
              xAxis: zero_gamma,
              label: { formatter: `Zero Gamma ${zero_gamma}` },
              lineStyle: { color: '#b87333', type: 'dashed' },
            },
          ]),
    ]
    return {
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v: unknown) => fmtMoney(Number(v)),
      },
      grid: { left: 70, right: 16, top: 16, bottom: 28 },
      xAxis: {
        type: 'value',
        name: '假想现货价',
        scale: true,
        axisLabel: { fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        name: 'Net GEX / 1%',
        axisLabel: { formatter: (v: number) => fmtMoney(v, 0) },
      },
      series: [
        {
          name: 'Net GEX',
          type: 'line',
          data: curve.map((p) => [p.spot, p.net_gex_1pct]),
          showSymbol: false,
          lineStyle: { color: '#b87333', width: 2 },
          areaStyle: { color: 'rgba(184, 115, 51, 0.12)' },
          markLine: { symbol: 'none', silent: true, data: markLineData },
        },
      ],
    }
  }

  const chartRef = useECharts(option, [analysis])
  return <div ref={chartRef} className="h-[300px] w-full" />
}

// ─── 统计卡片 ───
function StatCard({ label, value, sub, valueClass }: {
  label: string
  value: string
  sub?: string
  valueClass?: string
}) {
  return (
    <Card>
      <div className="p-4">
        <div className="text-xs text-gray-500">{label}</div>
        <div className={`font-heading text-xl font-bold mt-1 ${valueClass ?? ''}`}>{value}</div>
        {sub ? <div className="text-xs text-gray-400 mt-0.5">{sub}</div> : null}
      </div>
    </Card>
  )
}

// ─── 行权价聚合表 ───
function StrikeTable({ strikes, zeroGamma }: { strikes: GexStrike[]; zeroGamma: number | null }) {
  return (
    <Card>
      <CardHeader title={`按行权价聚合（${strikes.length} 档）`} />
      <div className="overflow-y-auto max-h-[420px]">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-[#faf7f2]">
            <tr className="text-left text-xs text-gray-500">
              <th className="px-4 py-2">行权价</th>
              <th className="px-4 py-2 text-right">Call GEX</th>
              <th className="px-4 py-2 text-right">Put GEX</th>
              <th className="px-4 py-2 text-right">Net GEX</th>
              <th className="px-4 py-2 text-right">Call OI</th>
              <th className="px-4 py-2 text-right">Put OI</th>
            </tr>
          </thead>
          <tbody>
            {strikes.map((s) => {
              const isZero = zeroGamma !== null && Math.abs(s.strike - zeroGamma) < 0.01
              return (
                <tr key={s.strike} className={`border-t border-gray-100 ${isZero ? 'bg-amber-50' : ''}`}>
                  <td className="px-4 py-1.5 font-medium">{s.strike}</td>
                  <td className={`px-4 py-1.5 text-right ${gexColor(s.call_gex_1pct)}`}>{fmtMoney(s.call_gex_1pct)}</td>
                  <td className={`px-4 py-1.5 text-right ${gexColor(s.put_gex_1pct)}`}>{fmtMoney(s.put_gex_1pct)}</td>
                  <td className={`px-4 py-1.5 text-right font-medium ${gexColor(s.net_gex_1pct)}`}>{fmtMoney(s.net_gex_1pct)}</td>
                  <td className="px-4 py-1.5 text-right">{fmtInt(s.call_oi)}</td>
                  <td className="px-4 py-1.5 text-right">{fmtInt(s.put_oi)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

// ─── 到期日聚合表 ───
function ExpiryTable({ expiries }: { expiries: GexExpiry[] }) {
  return (
    <Card>
      <CardHeader title={`按到期日聚合（${expiries.length} 个）`} />
      <div className="overflow-y-auto max-h-[420px]">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-[#faf7f2]">
            <tr className="text-left text-xs text-gray-500">
              <th className="px-4 py-2">到期日</th>
              <th className="px-4 py-2 text-right">剩余天数</th>
              <th className="px-4 py-2 text-right">Call GEX</th>
              <th className="px-4 py-2 text-right">Put GEX</th>
              <th className="px-4 py-2 text-right">Net GEX</th>
              <th className="px-4 py-2 text-right">合约数</th>
              <th className="px-4 py-2 text-right">总 OI</th>
            </tr>
          </thead>
          <tbody>
            {expiries.map((e) => (
              <tr key={e.expire_date} className="border-t border-gray-100">
                <td className="px-4 py-1.5 font-medium">{e.expire_date}</td>
                <td className="px-4 py-1.5 text-right">{e.t_days}</td>
                <td className={`px-4 py-1.5 text-right ${gexColor(e.call_gex_1pct)}`}>{fmtMoney(e.call_gex_1pct)}</td>
                <td className={`px-4 py-1.5 text-right ${gexColor(e.put_gex_1pct)}`}>{fmtMoney(e.put_gex_1pct)}</td>
                <td className={`px-4 py-1.5 text-right font-medium ${gexColor(e.net_gex_1pct)}`}>{fmtMoney(e.net_gex_1pct)}</td>
                <td className="px-4 py-1.5 text-right">{fmtInt(e.contracts)}</td>
                <td className="px-4 py-1.5 text-right">{fmtInt(e.oi_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

// ─── 页面 ───
export default function GexPage() {
  const [code, setCode] = useState('US.AAPL')
  const [maxExpiries, setMaxExpiries] = useState(6)
  const [minOi, setMinOi] = useState(500)

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['gex-status'],
    queryFn: fetchGexStatus,
    refetchInterval: 60_000,
  })

  const disabled = !status?.enabled
  const connected = !!status?.connected

  const { data: analysis, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['gex-analysis', code, maxExpiries, minOi],
    queryFn: () => fetchGexAnalysis(code, maxExpiries, minOi),
    enabled: !disabled && connected && code.trim().length > 0,
    retry: 1,
  })

  const errDetail =
    isError && error !== null
      ? typeof (error as { response?: { data?: { detail?: string } } }).response?.data?.detail === 'string'
        ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : String((error as Error).message ?? '未知错误')
      : null

  const regime = analysis ? (analysis.net_gex_1pct > 0 ? '正 Gamma（对冲盘逆势，波动倾向平抑）' : '负 Gamma（对冲盘顺势，波动倾向放大）') : null

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold">GEX 敞口</h1>
          <p className="text-sm text-gray-500 mt-1">净 Gamma 敞口 / Zero Gamma / 按行权价分布（富途只读数据源）</p>
        </div>
        <Badge variant={disabled ? 'warning' : connected ? 'success' : 'danger'}>
          {statusLoading ? '检测中…' : disabled ? 'Futu 未启用' : connected ? 'OpenD 已连接' : 'OpenD 未连接'}
        </Badge>
      </div>

      {disabled && (
        <Card>
          <div className="p-4 text-sm text-gray-600">
            富途集成尚未启用（<code>FUTU_ENABLED=false</code>）。请在服务器 <code>.env</code> 中开启并重启后端。
            {status?.reason ? <div className="mt-2 text-gray-400">detail: {String(status.reason)}</div> : null}
          </div>
        </Card>
      )}

      {!disabled && (
        <>
          {/* 查询参数 */}
          <Card>
            <div className="p-4 flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500">标的代码</label>
                <Input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="US.AAPL / US.SPY"
                  className="w-52"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500">到期日个数</label>
                <Input
                  type="number"
                  min={1}
                  max={12}
                  value={maxExpiries}
                  onChange={(e) => setMaxExpiries(Number(e.target.value) || 6)}
                  className="w-24"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500">Min OI</label>
                <Input
                  type="number"
                  min={0}
                  value={minOi}
                  onChange={(e) => setMinOi(Number(e.target.value) || 0)}
                  className="w-24"
                />
              </div>
              <Button variant="primary" onClick={() => refetch()} disabled={isLoading}>
                {isLoading ? '计算中…' : '重新计算'}
              </Button>
            </div>
          </Card>

          {isError && (
            <Card>
              <div className="p-4 text-sm text-red-600">{errDetail ?? '计算失败'}</div>
            </Card>
          )}

          {isLoading && !analysis && (
            <Card>
              <div className="p-4 text-sm text-gray-500">正在获取期权链并计算 GEX…（需拉取 {maxExpiries} 个到期日 × Call/Put 静态链 + 行情快照）</div>
            </Card>
          )}

          {analysis && (
            <>
              {analysis.warning ? (
                <Card>
                  <div className="p-4 text-sm text-amber-600">{analysis.warning}</div>
                </Card>
              ) : null}

              {/* 统计卡片 */}
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                <StatCard label="现货价" value={String(analysis.spot)} sub={`r=${analysis.r}`} />
                <StatCard
                  label="Net GEX / 1%"
                  value={fmtMoney(analysis.net_gex_1pct, 2)}
                  sub={regime ?? ''}
                  valueClass={gexColor(analysis.net_gex_1pct)}
                />
                <StatCard
                  label="Zero Gamma"
                  value={analysis.zero_gamma === null ? '网格内无翻转位' : String(analysis.zero_gamma)}
                  sub={analysis.zero_gamma === null ? 'Net GEX 恒正/恒负' : '对冲流翻转位'}
                />
                <StatCard label="Call GEX" value={fmtMoney(analysis.call_gex_1pct, 2)} valueClass="text-red-600" />
                <StatCard label="Put GEX" value={fmtMoney(analysis.put_gex_1pct, 2)} valueClass="text-green-600" />
                <StatCard label="合约数" value={fmtInt(analysis.contracts)} sub={`OI≥${analysis.filters.min_oi}`} />
              </div>

              {/* 图表 */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Card>
                  <CardHeader title="按行权价 GEX 分布（每 1% 波动）" />
                  <div className="p-2">
                    <GexStrikeChart strikes={analysis.strikes} zeroGamma={analysis.zero_gamma} />
                  </div>
                </Card>
                <Card>
                  <CardHeader title="Net GEX 曲线（Sticky Strike 扫描）" />
                  <div className="p-2">
                    <GexCurveChart analysis={analysis} />
                  </div>
                </Card>
              </div>

              {/* 数据表 */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <StrikeTable strikes={analysis.strikes} zeroGamma={analysis.zero_gamma} />
                <ExpiryTable expiries={analysis.expiries} />
              </div>

              {/* 口径说明 */}
              <Card>
                <div className="p-4 text-xs text-gray-500 space-y-1">
                  <div>
                    口径：<code>{analysis.sign_convention}</code>（公共数据标准约定，dealer 持仓方向为模型假设，非真实账簿观察）。
                    覆盖到期日 {analysis.filters.min_t_days}~{analysis.filters.max_t_days} 天、OI≥{analysis.filters.min_oi}。
                    单位：每 1% 标的波动的对冲盘美元敞口。
                  </div>
                  <div>
                    GEX 用于波动率情境参考（正=平抑/磁吸，负=放大），不构成方向预测；OI 为前夜快照，盘中新开仓不反映。
                  </div>
                </div>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  )
}
