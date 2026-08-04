/**
 * 净 Gamma 敞口（Net GEX）API 客户端。
 * 后端见 [gex_api.py](file:///d:/Codes/stock-ai-assistant/app/api/gex_api.py)。
 * 数据源依赖富途 OpenD（只读），FUTU_ENABLED=false 时返回 503。
 */
import { api } from '@/api/client'

export interface GexStrike {
  strike: number
  call_gex_1pct: number
  put_gex_1pct: number
  net_gex_1pct: number
  call_oi: number
  put_oi: number
}

export interface GexExpiry {
  expire_date: string
  t_days: number
  call_gex_1pct: number
  put_gex_1pct: number
  net_gex_1pct: number
  contracts: number
  oi_total: number
}

export interface GexCurvePoint {
  spot: number
  net_gex_1pct: number
}

export interface GexAnalysis {
  code: string
  spot: number
  r: number
  net_gex_1pct: number
  zero_gamma: number | null
  call_gex_1pct: number
  put_gex_1pct: number
  contracts: number
  strikes: GexStrike[]
  expiries: GexExpiry[]
  curve: GexCurvePoint[]
  sign_convention: string
  warning?: string
  filters: {
    min_oi: number
    min_t_days: number
    max_t_days: number
    max_expiries: number
  }
}

export interface GexStatus {
  enabled: boolean
  connected: boolean
  reason?: string
  [k: string]: unknown
}

export async function fetchGexStatus(): Promise<GexStatus> {
  const r = await api.get<GexStatus>('/api/gex/status')
  return r.data
}

export async function fetchGexAnalysis(
  code: string,
  maxExpiries = 6,
  minOi = 500,
): Promise<GexAnalysis> {
  const r = await api.get<GexAnalysis>('/api/gex/analysis', {
    params: { code, max_expiries: maxExpiries, min_oi: minOi },
  })
  return r.data
}
