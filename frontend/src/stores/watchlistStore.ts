import { create } from 'zustand'
import { api } from '@/api/client'

// ── 类型 ──

export interface WatchlistItem {
  symbol: string
  source: string        // manual | screener:<preset_name> | report | dashboard
  added_at: string      // ISO 时间
  note: string
}

export interface WatchlistQuote {
  price: number
  prev_close: number
  change_pct: number
}

interface WatchlistState {
  items: WatchlistItem[]
  loading: boolean
  error: string | null
  /** O(1) 查询某个 symbol 是否已关注 */
  symbolSet: Set<string>
  /** 行情快照 (symbol -> quote) */
  quotes: Record<string, WatchlistQuote>
  quotesLoading: boolean

  fetch: () => Promise<void>
  fetchQuotes: () => Promise<void>
  /** 加入单只股票,带来源标签;返回是否已存在 */
  add: (symbol: string, source?: string, note?: string) => Promise<{ alreadyExists: boolean }>
  remove: (symbol: string) => Promise<void>
  /** 整体替换(供 WatchlistPage 现有交互用) */
  replaceAll: (symbols: string[]) => Promise<void>
  isWatched: (symbol: string) => boolean
}

function buildSet(items: WatchlistItem[]): Set<string> {
  return new Set(items.map((i) => i.symbol))
}

export const useWatchlistStore = create<WatchlistState>((set, get) => ({
  items: [],
  loading: false,
  error: null,
  symbolSet: new Set(),
  quotes: {},
  quotesLoading: false,

  fetch: async () => {
    set({ loading: true, error: null })
    try {
      const res = await api.get<{ items: WatchlistItem[]; stocks: string[] }>('/api/watchlist')
      const items = res.data.items || []
      set({ items, symbolSet: buildSet(items), loading: false })
    } catch (e) {
      const msg = e instanceof Error ? e.message : '加载失败'
      set({ loading: false, error: msg })
    }
  },

  fetchQuotes: async () => {
    const symbols = get().items.map((i) => i.symbol)
    if (symbols.length === 0) {
      set({ quotes: {} })
      return
    }
    set({ quotesLoading: true })
    try {
      const res = await api.get<{ quotes: Record<string, WatchlistQuote> }>(
        `/api/watchlist/quotes?symbols=${encodeURIComponent(symbols.join(','))}`,
      )
      set({ quotes: res.data.quotes || {}, quotesLoading: false })
    } catch (e) {
      // 行情拉取失败不阻断主流程
      console.warn('[watchlist] fetchQuotes failed', e)
      set({ quotesLoading: false })
    }
  },

  add: async (symbol, source = 'manual', note = '') => {
    const sym = symbol.trim().toUpperCase()
    if (!sym) return { alreadyExists: false }
    try {
      const res = await api.post<{ items: WatchlistItem[]; already_exists: boolean }>(
        '/api/watchlist/add',
        { symbol: sym, source, note },
      )
      const items = res.data.items || []
      set({ items, symbolSet: buildSet(items) })
      return { alreadyExists: res.data.already_exists }
    } catch (e) {
      const msg = e instanceof Error ? e.message : '添加失败'
      set({ error: msg })
      throw e
    }
  },

  remove: async (symbol) => {
    const sym = symbol.trim().toUpperCase()
    if (!sym) return
    try {
      const res = await api.post<{ items: WatchlistItem[] }>('/api/watchlist/remove', {
        symbol: sym,
      })
      const items = res.data.items || []
      set({ items, symbolSet: buildSet(items) })
    } catch (e) {
      const msg = e instanceof Error ? e.message : '移除失败'
      set({ error: msg })
      throw e
    }
  },

  replaceAll: async (symbols) => {
    try {
      const res = await api.post<{ items: WatchlistItem[] }>('/api/watchlist', {
        stocks: symbols,
      })
      const items = res.data.items || []
      set({ items, symbolSet: buildSet(items) })
    } catch (e) {
      const msg = e instanceof Error ? e.message : '保存失败'
      set({ error: msg })
      throw e
    }
  },

  isWatched: (symbol) => get().symbolSet.has(symbol.trim().toUpperCase()),
}))

// ── 来源标签的展示工具 ──

export function describeSource(source: string): { label: string; group: string } {
  if (!source || source === 'manual') return { label: '手动添加', group: 'manual' }
  if (source.startsWith('screener:')) {
    const name = source.slice('screener:'.length) || '默认策略'
    return { label: `选股器 · ${name}`, group: 'screener' }
  }
  if (source === 'report') return { label: '周报推荐', group: 'report' }
  if (source === 'dashboard') return { label: '工作台', group: 'dashboard' }
  return { label: source, group: 'other' }
}
