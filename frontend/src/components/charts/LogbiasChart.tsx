import { useEffect, useRef } from 'react'

/**
 * LOGBIAS Chart - 对数均线偏离度曲线。
 *
 * 复刻通达信原图：偏离度折线 + 4 条阈值虚线（15 / 5 / 0 / -5）+ 零轴分区着色。
 */
interface Props {
  series: number[]
  dates: string[]
  value: number | null
}

// 阈值虚线定义（减法版）
const THRESHOLDS = [
  { y: 15, color: '#e53935', label: '过热 +15' },
  { y: 5, color: '#f59e0b', label: '适中 +5' },
  { y: 0, color: '#9ca3af', label: '均线 0' },
  { y: -5, color: '#e53935', label: '失速 -5' },
]

export default function LogbiasChart({ series, dates, value }: Props) {
  const chartRef = useRef<HTMLDivElement>(null)
  const echartsRef = useRef<unknown>(null)

  useEffect(() => {
    if (!chartRef.current || !series.length) return

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let chart: any = null

    const initChart = async () => {
      const echarts = await import('echarts')
      if (!chartRef.current) return
      chart = echarts.init(chartRef.current, undefined, { renderer: 'canvas' })
      echartsRef.current = chart

      const markLineData = THRESHOLDS.map(t => ({
        yAxis: t.y,
        label: { formatter: t.label, position: 'start' as const, fontSize: 10, color: t.color },
        lineStyle: { color: t.color, type: 'dashed' as const, width: 1, opacity: 0.7 },
      }))

      const option = {
        animation: false,
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'line' },
          formatter: (params: { dataIndex: number; value: number }[]) => {
            const p = params[0]
            if (!p) return ''
            return `${dates[p.dataIndex]}<br/>偏离度: <strong>${p.value?.toFixed(2)}%</strong>`
          },
        },
        grid: { left: 48, right: 20, top: 20, bottom: 30 },
        xAxis: {
          type: 'category',
          data: dates,
          axisLabel: { fontSize: 10, color: '#9ca3af' },
          axisLine: { lineStyle: { color: '#e5e7eb' } },
        },
        yAxis: {
          type: 'value',
          scale: true,
          axisLabel: { fontSize: 10, color: '#9ca3af', formatter: '{value}%' },
          splitLine: { lineStyle: { color: '#f3f4f6' } },
        },
        series: [
          {
            name: 'LOGBIAS',
            type: 'line',
            data: series,
            smooth: true,
            symbol: 'none',
            lineStyle: { width: 2, color: '#b87333' },
            areaStyle: {
              opacity: 0.12,
              color: '#b87333',
            },
            markLine: { data: markLineData, symbol: 'none', silent: true },
          },
        ],
      }

      chart.setOption(option)
    }

    initChart()

    const handleResize = () => {
      if (echartsRef.current && typeof (echartsRef.current as { resize?: () => void }).resize === 'function') {
        (echartsRef.current as { resize: () => void }).resize()
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      if (chart) chart.dispose()
    }
  }, [series, dates])

  if (!series.length) {
    return <div className="py-8 text-center text-xs text-gray-400">暂无偏离度数据</div>
  }

  return (
    <div>
      <div className="flex items-center gap-4 mb-1 text-xs text-gray-500">
        <span>当前偏离度: <strong className="text-copper">{value?.toFixed(2)}%</strong></span>
        <span className="text-gray-400">对数均线偏离度 · EMA20(ln Close)</span>
      </div>
      <div ref={chartRef} style={{ width: '100%', height: 220 }} />
    </div>
  )
}
