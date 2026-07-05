import { useEffect, useRef } from 'react'
import type { EChartsCoreOption, EChartsType } from 'echarts'

/**
 * ECharts 生命周期通用 Hook。
 *
 * 封装 React 中使用 ECharts 的全部「脏活」：异步动态加载(懒分包)、实例
 * 初始化/销毁、resize 监听、以及 isMounted 异步竞态防护。组件只需提供
 * option 构建函数与数据依赖数组，无需再关心底层 DOM 生命周期。
 *
 * 设计要点：
 * - 生命周期 Effect 依赖为空，仅初始化/销毁一次，切断与数据更新的耦合
 * - 数据 Effect 监听 deps 变化，走 setOption 增量更新（notMerge 全量替换避免残留）
 * - isMounted 锁确保异步 import 完成时若组件已卸载则不再 init，杜绝内存泄漏
 *
 * @param getOption 返回 ECharts option 的纯函数（闭包捕获组件最新 props）
 * @param deps      数据依赖数组，变化时触发增量 setOption
 * @returns         挂载到容器 div 的 ref
 */
export function useECharts(getOption: () => EChartsCoreOption, deps: unknown[]) {
  const chartRef = useRef<HTMLDivElement>(null)
  const instanceRef = useRef<EChartsType | null>(null)

  // 1. 实例生命周期：仅初始化/销毁一次，isMounted 杜绝异步竞态
  useEffect(() => {
    if (!chartRef.current) return

    let isMounted = true

    const initChart = async () => {
      const echarts = await import('echarts')
      if (!chartRef.current || !isMounted) return
      const instance = echarts.init(chartRef.current, undefined, { renderer: 'canvas' })
      instanceRef.current = instance
      instance.setOption(getOption(), true)
    }

    initChart()

    const handleResize = () => instanceRef.current?.resize()
    window.addEventListener('resize', handleResize)

    return () => {
      isMounted = false
      window.removeEventListener('resize', handleResize)
      instanceRef.current?.dispose()
      instanceRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 2. 数据变化：增量更新(notMerge 全量替换)，不重建实例
  useEffect(() => {
    instanceRef.current?.setOption(getOption(), true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return chartRef
}
