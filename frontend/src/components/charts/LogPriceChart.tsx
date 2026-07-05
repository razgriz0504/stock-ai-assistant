import type { EChartsCoreOption } from 'echarts'
import { useECharts } from './useECharts'

/**
 * 对数值 + EMA20 走势图。
 *
 * 复刻 EarlETF 原图上半部分：ln(Close) 蓝线 + EMA20(ln Close) 红线。
 * 纵轴为对数值绝对量（非百分比），双线无阈值。
 */
interface Props {
  logClose: number[]
  ema: number[]
  dates: string[]
  title?: string
  height?: number
}

interface TooltipParam {
  dataIndex: number
  value: number
  seriesName: string
}

export default function LogPriceChart({ logClose, ema, dates, title, height = 180 }: Props) {
  const getOption = (): EChartsCoreOption => ({
    animation: false,
    legend: {
      data: ['对数值', 'EMA20'],
      top: 0,
      right: 4,
      itemWidth: 16,
      itemHeight: 8,
      textStyle: { fontSize: 10, color: '#9ca3af' },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line' },
      formatter: (params: TooltipParam[]) => {
        if (!params.length) return ''
        const idx = params[0].dataIndex
        let html = `${dates[idx]}<br/>`
        for (const p of params) {
          html += `${p.seriesName}: <strong>${Number(p.value).toFixed(3)}</strong><br/>`
        }
        return html
      },
    },
    grid: { left: 44, right: 20, top: 24, bottom: 30 },
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
      axisLabel: { fontSize: 10, color: '#9ca3af', formatter: (v: number) => v.toFixed(2) },
      splitLine: { lineStyle: { color: '#f3f4f6' } },
    },
    series: [
      {
        name: '对数值',
        type: 'line',
        data: logClose,
        smooth: false,
        symbol: 'none',
        lineStyle: { width: 1.5, color: '#2563eb' },
        z: 2,
      },
      {
        // EMA 本身已是平滑均线，关闭贝塞尔平滑以精准反映数学落点
        name: 'EMA20',
        type: 'line',
        data: ema,
        smooth: false,
        symbol: 'none',
        lineStyle: { width: 1.5, color: '#e53935' },
        z: 3,
      },
    ],
  })

  const chartRef = useECharts(getOption, [logClose, ema, dates])

  if (!logClose.length) {
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
      {title && <div className="mb-1 text-xs font-medium text-gray-600">{title}</div>}
      <div ref={chartRef} style={{ width: '100%', height }} />
    </div>
  )
}
