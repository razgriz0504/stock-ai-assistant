import { useEffect, useRef } from 'react'
import type { VcpDetail } from '@/stores/vcpStore'

/**
 * VCP Chart Component - ECharts K-line with VCP annotations.
 *
 * Renders:
 * - Main chart: Candlestick + SMA50/150/200 + Pivot markLine + Contraction markAreas
 * - Sub chart: Volume bars + 20-day volume SMA baseline
 */
interface Props {
  detail: VcpDetail
}

export default function VcpChart({ detail }: Props) {
  const chartRef = useRef<HTMLDivElement>(null)
  const echartsRef = useRef<unknown>(null)

  useEffect(() => {
    if (!chartRef.current || !detail.ohlcv.length) return

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let chart: any = null

    const initChart = async () => {
      const echarts = await import('echarts')

      if (!chartRef.current) return
      chart = echarts.init(chartRef.current, undefined, { renderer: 'canvas' })
      echartsRef.current = chart

      const dates = detail.ohlcv.map(d => d.date)
      const ohlcData = detail.ohlcv.map(d => [d.open, d.close, d.low, d.high])
      const volumes = detail.ohlcv.map(d => d.volume)

      // Volume SMA 20
      const volSma20: (number | null)[] = []
      for (let i = 0; i < volumes.length; i++) {
        if (i < 19) { volSma20.push(null); continue }
        const sum = volumes.slice(i - 19, i + 1).reduce((a, b) => a + b, 0)
        volSma20.push(Math.round(sum / 20))
      }

      // Mark areas for contractions
      const markAreaData = detail.contractions.map((c, idx) => {
        const opacity = Math.max(0.05, 0.2 - idx * 0.04)
        return [{
          xAxis: c.start_date,
          itemStyle: { color: `rgba(255, 152, 0, ${opacity})` },
        }, {
          xAxis: c.end_date,
        }]
      })

      // Pivot mark line
      const markLineData = detail.pivot_price ? [{
        yAxis: detail.pivot_price,
        label: { formatter: `Pivot $${detail.pivot_price.toFixed(2)}`, position: 'end' as const },
        lineStyle: { color: '#e53935', type: 'dashed' as const, width: 2 },
      }] : []

      const option = {
        animation: false,
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'cross' },
        },
        legend: {
          data: ['K线', 'SMA50', 'SMA150', 'SMA200'],
          top: 10,
          textStyle: { fontSize: 11 },
        },
        grid: [
          { left: 60, right: 40, top: 60, height: '55%' },
          { left: 60, right: 40, top: '75%', height: '18%' },
        ],
        xAxis: [
          { type: 'category', data: dates, gridIndex: 0, axisLabel: { fontSize: 10 } },
          { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } },
        ],
        yAxis: [
          { type: 'value', gridIndex: 0, scale: true, axisLabel: { fontSize: 10 } },
          { type: 'value', gridIndex: 1, scale: true, axisLabel: { fontSize: 10, formatter: (v: number) => (v / 1e6).toFixed(0) + 'M' } },
        ],
        dataZoom: [{
          type: 'inside', xAxisIndex: [0, 1], start: 50, end: 100,
        }],
        series: [
          {
            name: 'K线',
            type: 'candlestick',
            data: ohlcData,
            xAxisIndex: 0,
            yAxisIndex: 0,
            itemStyle: {
              color: '#26a69a',
              color0: '#ef5350',
              borderColor: '#26a69a',
              borderColor0: '#ef5350',
            },
            markLine: { data: markLineData, symbol: 'none' },
            markArea: { data: markAreaData },
          },
          {
            name: 'SMA50', type: 'line', data: detail.sma50,
            xAxisIndex: 0, yAxisIndex: 0,
            lineStyle: { width: 1, color: '#42a5f5' },
            symbol: 'none', smooth: true,
          },
          {
            name: 'SMA150', type: 'line', data: detail.sma150,
            xAxisIndex: 0, yAxisIndex: 0,
            lineStyle: { width: 1, color: '#ab47bc' },
            symbol: 'none', smooth: true,
          },
          {
            name: 'SMA200', type: 'line', data: detail.sma200,
            xAxisIndex: 0, yAxisIndex: 0,
            lineStyle: { width: 1.5, color: '#ff7043' },
            symbol: 'none', smooth: true,
          },
          {
            name: '成交量', type: 'bar', data: volumes,
            xAxisIndex: 1, yAxisIndex: 1,
            itemStyle: {
              color: (params: { dataIndex: number }) => {
                const d = detail.ohlcv[params.dataIndex]
                if (!d) return '#78909c'
                return d.close >= d.open ? '#26a69a' : '#ef5350'
              },
            },
          },
          {
            name: 'Vol MA20', type: 'line', data: volSma20,
            xAxisIndex: 1, yAxisIndex: 1,
            lineStyle: { width: 1, color: '#78909c' },
            symbol: 'none',
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
  }, [detail])

  return (
    <div>
      <div className="flex items-center gap-4 mb-2 text-xs text-gray-500">
        <span className="font-medium text-sm text-gray-700">{detail.symbol}</span>
        <span>状态: <strong className={detail.status === 'breakout' ? 'text-green-600' : detail.status === 'failed' ? 'text-red-500' : 'text-amber-600'}>{detail.status}</strong></span>
        <span>评分: <strong>{detail.score}</strong>/100</span>
        <span>RS: <strong>{detail.rs_percentile.toFixed(0)}</strong></span>
        {detail.pivot_price && <span>Pivot: <strong className="text-red-600">${detail.pivot_price.toFixed(2)}</strong></span>}
      </div>
      <div ref={chartRef} style={{ width: '100%', height: 450 }} />
      {detail.contractions.length > 0 && (
        <div className="mt-2 flex gap-3 text-xs text-gray-500">
          <span>收缩序列:</span>
          {detail.contractions.map(c => (
            <span key={c.name} className="bg-orange-50 px-2 py-0.5 rounded">
              {c.name}: {c.depth_pct}%
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
