import { create } from 'zustand'
import { api } from '@/api/client'

// ── 类型定义,与后端 dashboard_api.py 返回结构对齐 ──

export interface DashSectorItem {
  symbol: string
  name: string
  current: number | null
  chg_5d: number | null
  chg_30d: number | null
  rs_composite: number | null
  flow_direction: string | null
}

export interface DashTopStock {
  symbol: string
  name: string
  sector: string
  score: number | null
  rating: string
  price: number | null
  change_pct: number | null
}

export interface DashLatestRun {
  id: number
  status: string
  trigger: string
  passed_stocks: number
  total_stocks: number
  started_at: string | null
}

export interface DashLatestReport {
  id: number
  version: number
  report_date: string | null
  model_name: string
  trigger: string
}

export interface DashLatestTweet {
  username: string
  text_zh: string
  text: string
  sentiment: string
  created_at: string
}

export interface DashAlert {
  type: 'report' | 'screener' | 'x_monitor' | 'sector'
  level: 'info' | 'success' | 'warn' | 'danger'
  title: string
  desc: string
  link: string
}

export interface DashboardSummary {
  generated_at: string
  watchlist: { count: number; stocks: string[] }
  screener: {
    recent_24h_runs: number
    latest: DashLatestRun | null
    latest_completed_id: number | null
    top_stocks: DashTopStock[]
  }
  report: {
    latest: DashLatestReport | null
    is_running: boolean
  }
  x_monitor: {
    total_24h: number
    sentiment_distribution: { bullish: number; bearish: number; neutral: number }
    top_assets: { ticker: string; count: number }[]
    latest_tweet: DashLatestTweet | null
  }
  sector: {
    generated_at: string | null
    benchmark: unknown
    top_gainers: DashSectorItem[]
    top_losers: DashSectorItem[]
    inflow: DashSectorItem[]
    outflow: DashSectorItem[]
  }
  alerts: DashAlert[]
}

interface DashboardState {
  data: DashboardSummary | null
  loading: boolean
  error: string | null
  lastFetch: number | null
  fetchSummary: (opts?: { silent?: boolean }) => Promise<void>
}

export const useDashboardStore = create<DashboardState>((set) => ({
  data: null,
  loading: false,
  error: null,
  lastFetch: null,

  fetchSummary: async ({ silent } = {}) => {
    if (!silent) set({ loading: true, error: null })
    try {
      const res = await api.get<DashboardSummary>('/api/dashboard/summary')
      set({ data: res.data, loading: false, error: null, lastFetch: Date.now() })
    } catch (e) {
      const msg = e instanceof Error ? e.message : '加载失败'
      set({ loading: false, error: msg })
    }
  },
}))
