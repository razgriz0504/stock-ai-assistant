/**
 * 富途 OpenD 只读 API 客户端。
 * 后端见 [futu_api.py](file:///d:/Codes/stock-ai-assistant/app/api/futu_api.py)。
 * 所有接口均为查询类，不含下单/撤单。FUTU_ENABLED=false 时返回 503。
 */
import { api } from '@/api/client'

export interface FutuStatus {
  enabled: boolean
  host: string
  port: number
  trd_env: string
  trd_market: string
  detail: {
    connected: boolean
    reason?: string
    server_ver?: string
    trd_logined?: boolean
    qot_logined?: boolean
    [k: string]: unknown
  }
}

export type FutuRecord = Record<string, unknown>

export interface FutuListResp {
  records: FutuRecord[]
}

export async function fetchStatus(): Promise<FutuStatus> {
  const r = await api.get<FutuStatus>('/api/futu/status')
  return r.data
}

export async function fetchSnapshot(codes: string[]): Promise<{ codes: string[]; records: FutuRecord[] }> {
  const r = await api.get('/api/futu/snapshot', { params: { codes: codes.join(',') } })
  return r.data
}

export async function fetchOrderBook(code: string, num = 10): Promise<{ code: string; data: Record<string, unknown> }> {
  const r = await api.get('/api/futu/orderbook', { params: { code, num } })
  return r.data
}

export async function fetchTicker(code: string, num = 100): Promise<{ code: string; records: FutuRecord[] }> {
  const r = await api.get('/api/futu/ticker', { params: { code, num } })
  return r.data
}

export async function fetchKline(
  code: string,
  ktype = 'K_DAY',
  start = '',
  end = '',
  max_count = 500,
): Promise<{ code: string; ktype: string; records: FutuRecord[] }> {
  const r = await api.get('/api/futu/kline', { params: { code, ktype, start, end, max_count } })
  return r.data
}

export async function fetchTimeshare(code: string): Promise<{ code: string; records: FutuRecord[] }> {
  const r = await api.get('/api/futu/timeshare', { params: { code } })
  return r.data
}

export async function fetchPlateList(
  market = 'US',
  plate_class = 'INDUSTRY',
): Promise<{ market: string; plate_class: string; records: FutuRecord[] }> {
  const r = await api.get('/api/futu/plate/list', { params: { market, plate_class } })
  return r.data
}

export async function fetchPlateStocks(plate_code: string): Promise<{ plate_code: string; records: FutuRecord[] }> {
  const r = await api.get('/api/futu/plate/stocks', { params: { plate_code } })
  return r.data
}

export async function fetchCapitalFlow(code: string): Promise<{ code: string; records: FutuRecord[] }> {
  const r = await api.get('/api/futu/capital/flow', { params: { code } })
  return r.data
}

export async function fetchCapitalDistribution(code: string): Promise<{ code: string; data: Record<string, unknown> }> {
  const r = await api.get('/api/futu/capital/distribution', { params: { code } })
  return r.data
}

export async function fetchPositions(): Promise<{ trd_env: string; trd_market: string; records: FutuRecord[] }> {
  const r = await api.get('/api/futu/positions')
  return r.data
}

export async function fetchAccount(): Promise<{ trd_env: string; trd_market: string; data: Record<string, unknown> }> {
  const r = await api.get('/api/futu/account')
  return r.data
}
