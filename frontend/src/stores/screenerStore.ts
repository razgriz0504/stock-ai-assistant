import { create } from 'zustand'
import { api } from '@/api/client'

// ── State Machine: IDLE → PENDING → RUNNING → SUCCESS / FAILED ──

export type ScreenerStatus = 'idle' | 'pending' | 'running' | 'success' | 'failed'

export interface ScreenerResult {
  symbol: string
  name: string
  sector: string
  industry: string
  score: number
  rating: string
  price: number
  change_pct: number
  market_cap: number
  pe_ratio: number
  revenue_growth: number
  roe: number
  dividend_yield: number
  filter_details: Record<string, unknown>
  indicators: Record<string, unknown>
}

export interface ScreenerRun {
  id: number
  version: string
  trigger: string
  status: string
  total_stocks: number
  passed_stocks: number
  started_at: string | null
  filters_json: string
}

export interface ScreenerPreset {
  id: number
  name: string
  filters_json: string
  custom_code: string | null
  is_default: boolean
}

interface ScreenerState {
  // State machine
  status: ScreenerStatus
  runId: number | null
  progress: number
  errorMessage: string | null

  // Results
  results: ScreenerResult[]
  totalPassed: number
  currentRunFilters: string  // filters_json of currently viewed run
  currentRunVersion: number | null  // version of currently viewed run

  // Runs history
  runs: ScreenerRun[]

  // Presets
  presets: ScreenerPreset[]
  activePresetId: number | null

  // Filters & code
  filtersJson: string
  customCode: string

  // Actions
  setFilters: (json: string) => void
  setCustomCode: (code: string) => void
  setActivePreset: (id: number | null) => void
  loadPreset: (preset: ScreenerPreset) => void

  // Async actions
  startRun: () => Promise<void>
  pollStatus: () => Promise<boolean>
  fetchResults: () => Promise<void>
  loadRunResults: (runId: number) => Promise<void>
  fetchRuns: () => Promise<void>
  fetchPresets: () => Promise<void>
  savePreset: (name: string, isDefault?: boolean) => Promise<void>
  deletePreset: (id: number) => Promise<void>
  reset: () => void
}

export const useScreenerStore = create<ScreenerState>((set, get) => ({
  status: 'idle',
  runId: null,
  progress: 0,
  errorMessage: null,
  results: [],
  totalPassed: 0,
  currentRunFilters: '{}',
  currentRunVersion: null,
  runs: [],
  presets: [],
  activePresetId: null,
  filtersJson: '{}',
  customCode: '',

  setFilters: (json) => set({ filtersJson: json }),
  setCustomCode: (code) => set({ customCode: code }),
  setActivePreset: (id) => set({ activePresetId: id }),

  loadPreset: (preset) => set({
    activePresetId: preset.id,
    filtersJson: preset.filters_json || '{}',
    customCode: preset.custom_code || '',
  }),

  startRun: async () => {
    const { filtersJson, customCode, activePresetId } = get()
    set({ status: 'pending', errorMessage: null, results: [], progress: 0 })

    try {
      let filters = {}
      try { filters = JSON.parse(filtersJson) } catch { /* use empty */ }

      const res = await api.post('/api/screener/run', {
        filters,
        custom_code: customCode || '',
        preset_id: activePresetId || null,
      })
      set({ status: 'running', runId: res.data.run_id })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start'
      set({ status: 'failed', errorMessage: msg })
    }
  },

  pollStatus: async () => {
    const { runId } = get()
    if (!runId) return false

    try {
      const res = await api.get(`/api/screener/status/${runId}`)
      const { status, progress_pct, error_message } = res.data

      if (status === 'completed') {
        set({ status: 'success', progress: 100 })
        return true // done
      } else if (status === 'failed') {
        set({ status: 'failed', errorMessage: error_message, progress: 0 })
        return true // done
      } else {
        set({ status: 'running', progress: progress_pct || 0 })
        return false // still running
      }
    } catch {
      return false
    }
  },

  fetchResults: async () => {
    const { runId } = get()
    if (!runId) return
    try {
      const res = await api.get(`/api/screener/results/${runId}`)
      set({
        results: res.data.results,
        totalPassed: res.data.total_passed,
        currentRunFilters: res.data.filters_json || '{}',
        currentRunVersion: res.data.version ?? null,
      })
    } catch { /* ignore */ }
  },

  loadRunResults: async (id: number) => {
    set({ runId: id, status: 'success', results: [], totalPassed: 0 })
    try {
      const res = await api.get(`/api/screener/results/${id}`)
      set({
        results: res.data.results,
        totalPassed: res.data.total_passed,
        currentRunFilters: res.data.filters_json || '{}',
        currentRunVersion: res.data.version ?? null,
      })
    } catch { /* ignore */ }
  },

  fetchRuns: async () => {
    try {
      const res = await api.get('/api/screener/runs')
      set({ runs: res.data })
    } catch { /* ignore */ }
  },

  fetchPresets: async () => {
    try {
      const res = await api.get('/api/screener/presets')
      set({ presets: res.data })
    } catch { /* ignore */ }
  },

  savePreset: async (name, isDefault = false) => {
    const { filtersJson, customCode, activePresetId } = get()
    try {
      await api.post('/api/screener/presets', {
        id: activePresetId,
        name,
        filters_json: filtersJson,
        custom_code: customCode || '',
        is_default: isDefault,
      })
      await get().fetchPresets()
    } catch { /* ignore */ }
  },

  deletePreset: async (id) => {
    try {
      await api.delete(`/api/screener/presets/${id}`)
      if (get().activePresetId === id) {
        set({ activePresetId: null })
      }
      await get().fetchPresets()
    } catch { /* ignore */ }
  },

  reset: () => set({
    status: 'idle',
    runId: null,
    progress: 0,
    errorMessage: null,
    results: [],
    totalPassed: 0,
    currentRunFilters: '{}',
    currentRunVersion: null,
  }),
}))
