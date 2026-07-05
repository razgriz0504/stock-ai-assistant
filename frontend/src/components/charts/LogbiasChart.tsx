import type { EChartsCoreOption } from 'echarts'
import { useECharts } from './useECharts'

/**
 * 趋势曲线图（偏离度 / RS 相对强弱通用）。
 *
 * - 主折线 + 阈值虚线 + 零轴分区着色
 * - 可选叠加对主序列做 EMA20 平滑的趋势线（overlayEma）
 */
interface Threshold {
  y: number
  color: string
  label: string
}

interface Props {
  series: number[]
  dates: string[]
  value?: number | null
  title?: string
  height?: number
  color?: string
  thresholds?: Threshold[]
  overlayEma?: boolean
}

interface TooltipParam {
  dataIndex: number
  value: number
  seriesName: string
}

// 乖离度默认阈值虚线（减法版）
const DEFAULT_THRESHOLDS: Threshold[] = [
  { y: 15, color: '#e53935', label: '过热 +15' },
  { y: 5, color: '#f59e0b', label: '适中 +5' },
  { y: 0, color: '#9ca3af', label: '均线 0' },
  { y: -5, color: '#e53935', label: '失速 -5' },
]

// 对序列做 EMA 平滑（前端计算，用作趋势参考线）
function computeEma(data: number[], span: number): number[] {
  const k = 2 / (span + 1)
  const out: number[] = []
  let prev: number | null = null
  for (const v of data) {
    prev = prev === null ? v : v * k + prev * (1 - k)
    out.push(Math.round(prev * 100) / 100)
  }
  return out
}

export default function LogbiasChart({
  series,
  dates,
  value,
  title,
  height = 220,
  color = '#b87333',
  thresholds = DEFAULT_THRESHOLDS,
  overlayEma = false,
}: Props) {
  const getOption = (): EChartsCoreOption => {
    const markLineData = thresholds.map(t => ({
      yAxis: t.y,
      label: {
        formatter: t.label,
        position: 'insideEndTop' as const,
        fontSize: 10,
        color: t.color,
        padding: [0, 4, 2, 0],
      },
      lineStyle: { color: t.color, type: 'dashed' as const, width: 1, opacity: 0.7 },
    }))

    const emaData = overlayEma ? computeEma(series, 20) : null

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const seriesOption: any[] = [
      {
        name: '数值',
        type: 'line',
        data: series,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color },
        areaStyle: { opacity: 0.1, color },
        markLine: { data: markLineData, symbol: 'none', silent: true },
        z: 2,
      },
    ]

    if (emaData) {
      seriesOption.push({
        name: 'EMA20',
        type: 'line',
        data: emaData,
        smooth: false,
        symbol: 'none',
        lineStyle: { width: 1.5, color: '#2563eb', type: 'dashed' },
        z: 3,
      })
    }

    return {
      animation: false,
      legend: overlayEma
        ? { data: ['数值', 'EMA20'], top: 0, right: 4, itemWidth: 16, itemHeight: 8, textStyle: { fontSize: 10, color: '#9ca3af' } }
        : undefined,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'line' },
        formatter: (params: TooltipParam[]) => {
          if (!params.length) return ''
          const idx = params[0].dataIndex
          let html = `${dates[idx]}<br/>`
          for (const p of params) {
            html += `${p.seriesName}: <strong>${Number(p.value).toFixed(2)}%</strong><br/>`
          }
          return html
        },
      },
      grid: { left: 44, right: 20, top: overlayEma ? 24 : 20, bottom: 30 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { fontSize: 10, color: '#9ca3af' },
        axisLine: { lineStyle: { color: '#e5e7eb' } },
      },
      yAxis: {
        type: 'value',
        scale: true,
        splitNumber: 4,
        axisLabel: { fontSize: 10, color: '#9ca3af', formatter: (v: number) => `${Math.round(v)}%` },
        splitLine: { lineStyle: { color: '#f3f4f6' } },
      },
      series: seriesOption,
    }
  }

  const chartRef = useECharts(getOption, [series, dates, color, thresholds, overlayEma])

  if (!series.length) {
    return (
      <div>
        {title && <div className="mb-1 text-xs font-medium text-gray-600">{title}</div>}
        <div
          className="flex items-center justify-center text-xs text-gray-400"
          style={{ height }}
        >
          数据不足
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-1 text-xs">
        {title && <span className="font-medium text-gray-600">{title}</span>}
        {value != null && (
          <span className="text-gray-500">当前 <strong style={{ color }}>{value.toFixed(2)}%</strong></span>
        )}
      </div>
      <div ref={chartRef} style={{ width: '100%', height }} />
    </div>
  )
}
