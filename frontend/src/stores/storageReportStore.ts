import { create } from 'zustand'
import { api } from '@/api/client'

// ── 元数据 ──

export interface MetricDef {
  key: string
  name: string
  unit: string
  definition: string
  source_hint: string
}

export interface StorageMeta {
  categories: Record<string, string>
  themes: Record<string, string>
  vendors: Record<string, string>
  metrics: MetricDef[]
}

// ── 完整报告版本 ──

export type GenStatus = 'idle' | 'pending' | 'running' | 'success' | 'failed'

export interface ReportVersion {
  id: number
  version: number
  status: string
  trigger: string
  model_name: string
  categories: string[]
  time_range: string
  report_date: string | null
  created_at: string | null
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyResult = any

interface StorageReportState {
  // 元数据
  meta: StorageMeta | null
  fetchMeta: () => Promise<void>

  // 即时分析（六大能力），按 key 存 loading / result
  loading: Record<string, boolean>
  results: Record<string, AnyResult>
  runMetricQuery: (metricKey: string, category: string) => Promise<void>
  runProsperity: (timeRange: string, categories: string[], themes: string[]) => Promise<void>
  runPriceTrend: (categories: string[], timeRange: string) => Promise<void>
  runSupplyDemand: (category: string, timeRange: string) => Promise<void>
  runVendorTracking: (vendors: string[]) => Promise<void>
  runAnomaly: (timeRange: string) => Promise<void>

  // 一键生成完整报告
  genStatus: GenStatus
  genReportId: number | null
  genError: string | null
  generate: (categories: string[] | null, timeRange: string) => Promise<void>
  pollStatus: () => Promise<boolean>

  // 报告版本管理
  reports: ReportVersion[]
  currentReport: AnyResult | null
  fetchReports: () => Promise<void>
  fetchReport: (id: number) => Promise<void>
  deleteReport: (id: number) => Promise<void>
}

async function runCapability(
  set: (partial: Partial<StorageReportState> | ((s: StorageReportState) => Partial<StorageReportState>)) => void,
  key: string,
  fn: () => Promise<AnyResult>,
) {
  set((s) => ({ loading: { ...s.loading, [key]: true } }))
  try {
    const data = await fn()
    set((s) => ({ results: { ...s.results, [key]: data } }))
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '请求失败'
    set((s) => ({ results: { ...s.results, [key]: { error: msg } } }))
  } finally {
    set((s) => ({ loading: { ...s.loading, [key]: false } }))
  }
}

export const useStorageReportStore = create<StorageReportState>((set, get) => ({
  meta: null,
  loading: {},
  results: {},
  genStatus: 'idle',
  genReportId: null,
  genError: null,
  reports: [],
  currentReport: null,

  fetchMeta: async () => {
    try {
      const res = await api.get('/api/storage-report/metrics')
      set({ meta: res.data })
    } catch { /* ignore */ }
  },

  runMetricQuery: (metricKey, category) =>
    runCapability(set, 'metric', async () =>
      (await api.post('/api/storage-report/metric-query', { metric_key: metricKey, category })).data,
    ),

  runProsperity: (timeRange, categories, themes) =>
    runCapability(set, 'prosperity', async () =>
      (await api.post('/api/storage-report/prosperity', { time_range: timeRange, categories, themes })).data,
    ),

  runPriceTrend: (categories, timeRange) =>
    runCapability(set, 'price_trend', async () =>
      (await api.post('/api/storage-report/price-trend', { categories, time_range: timeRange })).data,
    ),

  runSupplyDemand: (category, timeRange) =>
    runCapability(set, 'supply_demand', async () =>
      (await api.post('/api/storage-report/supply-demand', { category, time_range: timeRange })).data,
    ),

  runVendorTracking: (vendors) =>
    runCapability(set, 'vendor', async () =>
      (await api.post('/api/storage-report/vendor-tracking', { vendors })).data,
    ),

  runAnomaly: (timeRange) =>
    runCapability(set, 'anomaly', async () =>
      (await api.post('/api/storage-report/anomaly', { time_range: timeRange })).data,
    ),

  generate: async (categories, timeRange) => {
    set({ genStatus: 'pending', genError: null, genReportId: null })
    try {
      const res = await api.post('/api/storage-report/generate', {
        categories: categories,
        time_range: timeRange,
      })
      set({ genStatus: 'running', genReportId: res.data.report_id })
      await get().fetchReports()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '生成失败'
      set({ genStatus: 'failed', genError: msg })
    }
  },

  pollStatus: async () => {
    const { genReportId } = get()
    if (!genReportId) return false
    try {
      const res = await api.get(`/api/storage-report/status/${genReportId}`)
      const { status, error_message } = res.data
      if (status === 'completed') {
        set({ genStatus: 'success' })
        await get().fetchReports()
        return true
      } else if (status === 'failed') {
        set({ genStatus: 'failed', genError: error_message })
        return true
      }
      set({ genStatus: 'running' })
      return false
    } catch {
      return false
    }
  },

  fetchReports: async () => {
    try {
      const res = await api.get('/api/storage-report/reports')
      set({ reports: res.data })
    } catch { /* ignore */ }
  },

  fetchReport: async (id) => {
    try {
      const res = await api.get(`/api/storage-report/report/${id}`)
      set({ currentReport: res.data })
    } catch { /* ignore */ }
  },

  deleteReport: async (id) => {
    try {
      await api.delete(`/api/storage-report/report/${id}`)
      if (get().currentReport?.id === id) set({ currentReport: null })
      await get().fetchReports()
    } catch { /* ignore */ }
  },
}))
