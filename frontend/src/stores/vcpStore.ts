import { create } from 'zustand'
import { api } from '@/api/client'

// ── Types ──

export interface VcpWatchlistItem {
  id: number
  symbol: string
  source: string
  auto_seeded: boolean
  enabled: boolean
  note: string
  created_at: string | null
  last_triggered_at: string | null
}

export interface VcpScanRun {
  id: number
  trigger: string
  status: string
  started_at: string | null
  finished_at: string | null
  total: number
  detected: number
}

export interface VcpContraction {
  name: string
  start_date: string
  end_date: string
  high: number
  low: number
  depth_pct: number
  avg_volume: number
}

export interface VcpScanResult {
  id: number
  symbol: string
  status: string
  score: number
  pivot_price: number | null
  last_close: number | null
  distance_pct: number | null
  contractions: VcpContraction[]
  volume_dry_ratio: number | null
  rs_percentile: number | null
  sector: string
  last_alert_at: string | null
  reject_reason: string | null
  created_at: string | null
}

export interface VcpAlert {
  id: number
  symbol: string
  alert_type: string
  pivot_price: number | null
  breakout_price: number | null
  volume_ratio: number | null
  prior_failed: boolean
  sent_feishu: boolean
  alerted_at: string | null
}

export interface VcpDetail {
  symbol: string
  ohlcv: Array<{ date: string; open: number; high: number; low: number; close: number; volume: number }>
  sma50: number[]
  sma150: number[]
  sma200: number[]
  pivot_price: number | null
  base_start_date: string | null
  status: string
  score: number
  contractions: VcpContraction[]
  volume_sma20: number
  rs_percentile: number
}

interface VcpState {
  watchlist: VcpWatchlistItem[]
  runs: VcpScanRun[]
  results: VcpScanResult[]
  alerts: VcpAlert[]
  activeDetail: VcpDetail | null
  scanning: boolean
  loading: boolean

  fetchWatchlist: () => Promise<void>
  addSymbol: (symbol: string, note?: string) => Promise<void>
  removeSymbol: (id: number) => Promise<void>
  startScan: (source?: string) => Promise<void>
  fetchRuns: () => Promise<void>
  fetchResults: (runId: number) => Promise<void>
  fetchDetail: (symbol: string) => Promise<void>
  fetchAlerts: () => Promise<void>
  seedFromSepa: () => Promise<number>
}

export const useVcpStore = create<VcpState>((set) => ({
  watchlist: [],
  runs: [],
  results: [],
  alerts: [],
  activeDetail: null,
  scanning: false,
  loading: false,

  fetchWatchlist: async () => {
    const { data } = await api.get('/api/vcp-monitor/watchlist')
    set({ watchlist: data })
  },

  addSymbol: async (symbol: string, note = '') => {
    await api.post('/api/vcp-monitor/watchlist', { symbol, note })
    const { data } = await api.get('/api/vcp-monitor/watchlist')
    set({ watchlist: data })
  },

  removeSymbol: async (id: number) => {
    await api.delete(`/api/vcp-monitor/watchlist/${id}`)
    const { data } = await api.get('/api/vcp-monitor/watchlist')
    set({ watchlist: data })
  },

  startScan: async (source: string = 'screener') => {
    set({ scanning: true })
    try {
      await api.post(`/api/vcp-monitor/scan?source=${source}`)
      const { data } = await api.get('/api/vcp-monitor/runs')
      set({ runs: data, scanning: false })
    } catch {
      set({ scanning: false })
    }
  },

  fetchRuns: async () => {
    const { data } = await api.get('/api/vcp-monitor/runs')
    set({ runs: data })
  },

  fetchResults: async (runId: number) => {
    set({ loading: true })
    const { data } = await api.get(`/api/vcp-monitor/results/${runId}`)
    set({ results: data, loading: false })
  },

  fetchDetail: async (symbol: string) => {
    set({ loading: true })
    const { data } = await api.get(`/api/vcp-monitor/detail/${symbol}`)
    set({ activeDetail: data, loading: false })
  },

  fetchAlerts: async () => {
    const { data } = await api.get('/api/vcp-monitor/alerts')
    set({ alerts: data })
  },

  seedFromSepa: async () => {
    const { data } = await api.post('/api/vcp-monitor/seed-from-sepa')
    // Refresh watchlist
    const wl = await api.get('/api/vcp-monitor/watchlist')
    set({ watchlist: wl.data })
    return data.added as number
  },
}))
