import { useState, useEffect, useMemo } from 'react'
import { Card, CardHeader, Button, Input } from '@/components/ui'
import { useWatchlistStore, describeSource, type WatchlistItem } from '@/stores/watchlistStore'
import { getCnName } from '@/data/cnNames'

function formatAddedAt(iso: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return '-'
    const now = Date.now()
    const diffMs = now - d.getTime()
    const day = 24 * 3600 * 1000
    if (diffMs < 60 * 1000) return '刚刚'
    if (diffMs < 3600 * 1000) return `${Math.floor(diffMs / 60000)} 分钟前`
    if (diffMs < day) return `${Math.floor(diffMs / 3600000)} 小时前`
    if (diffMs < 7 * day) return `${Math.floor(diffMs / day)} 天前`
    return d.toLocaleDateString('zh-CN')
  } catch {
    return '-'
  }
}

export default function WatchlistPage() {
  const {
    items, loading, error,
    fetch: fetchList, add, remove,
    quotes, quotesLoading, fetchQuotes,
    sentiment, sentimentLoading, fetchSentiment,
  } = useWatchlistStore()
  const [input, setInput] = useState('')
  const [status, setStatus] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)

  useEffect(() => { fetchList() }, [fetchList])
  // 列表变化后拉取行情快照 + X 舆情聚合
  useEffect(() => {
    if (items.length > 0) {
      fetchQuotes()
      fetchSentiment(7)
    }
  }, [items, fetchQuotes, fetchSentiment])

  const showStatus = (msg: string, type: 'ok' | 'err') => {
    setStatus({ msg, type })
    setTimeout(() => setStatus(null), 3000)
  }

  const handleAdd = async () => {
    if (!input.trim()) return
    const newOnes = input.split(/[,，\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean)
    if (newOnes.length === 0) return
    let added = 0
    let skipped = 0
    for (const sym of newOnes) {
      try {
        const { alreadyExists } = await add(sym, 'manual')
        if (alreadyExists) skipped++
        else added++
      } catch {
        skipped++
      }
    }
    setInput('')
    if (added > 0) showStatus(`已添加 ${added} 只${skipped > 0 ? `,${skipped} 只已存在` : ''}`, 'ok')
    else showStatus('股票已在列表中', 'err')
  }

  const handleRemove = async (symbol: string) => {
    try {
      await remove(symbol)
      showStatus(`已移除: ${symbol}`, 'ok')
    } catch {
      showStatus('移除失败', 'err')
    }
  }

  // 按来源分组
  const groups = useMemo(() => {
    const map = new Map<string, { label: string; group: string; items: WatchlistItem[] }>()
    for (const it of items) {
      const desc = describeSource(it.source)
      const key = it.source || 'manual'
      if (!map.has(key)) map.set(key, { label: desc.label, group: desc.group, items: [] })
      map.get(key)!.items.push(it)
    }
    // 排序: 手动添加 → 选股器(按 label) → 周报 → 其他
    const order: Record<string, number> = { manual: 0, screener: 1, report: 2, dashboard: 3, other: 4 }
    return Array.from(map.entries())
      .map(([key, val]) => ({ key, ...val }))
      .sort((a, b) => {
        const oa = order[a.group] ?? 99
        const ob = order[b.group] ?? 99
        if (oa !== ob) return oa - ob
        return a.label.localeCompare(b.label)
      })
  }, [items])

  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          Watchlist
        </span>
        <h1 className="page-title">关注<span className="text-copper">列表</span></h1>
        <p className="text-sm text-gray-500 mt-2">按来源分组管理关注股票（手动 / 选股器 / 周报推荐）</p>
      </div>

      <Card className="mb-6">
        <CardHeader title="添加股票" label={items.length > 0 ? `共 ${items.length} 只` : undefined} />

        <div className="flex gap-3 mb-4">
          <div className="flex-1">
            <Input
              placeholder="输入股票代码，多个用逗号分隔（如 AAPL, TSLA, NVDA）"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAdd()}
            />
          </div>
          <Button variant="primary" onClick={handleAdd}>添加</Button>
        </div>

        {status && (
          <p className={`text-xs ${status.type === 'ok' ? 'text-success' : 'text-danger'}`}>
            {status.msg}
          </p>
        )}
        {error && (
          <p className="text-xs text-danger">{error}</p>
        )}
      </Card>

      {loading ? (
        <Card><div className="text-center py-8 text-cream-500 text-sm">加载中...</div></Card>
      ) : items.length === 0 ? (
        <Card><div className="text-center py-8 text-cream-500 text-sm">暂无关注股票，请在上方添加，或在选股器中点击 ☆ 加入</div></Card>
      ) : (
        <div className="space-y-4">
          {groups.map((g) => (
            <Card key={g.key}>
              <div className="flex items-center justify-between mb-3">
                <CardHeader title={g.label} label={`${g.items.length} 只`} />
                <span className="text-[11px] text-cream-500 font-mono">
                  {quotesLoading && '行情拉取中... '}
                  {sentimentLoading && '舆情聚合中...'}
                </span>
              </div>
              <div className="space-y-2">
                {g.items.map((it) => {
                  const q = quotes[it.symbol]
                  const chg = q?.change_pct
                  const chgColor =
                    chg == null ? 'text-gray-400' : chg > 0 ? 'text-success' : chg < 0 ? 'text-danger' : 'text-gray-500'
                  const chgText =
                    chg == null ? '-' : `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`
                  const sent = sentiment[it.symbol]
                  const hasSent = sent && sent.total > 0
                  // 徽章颜色: 看涨占多 -> 绿; 看跌占多 -> 红; 中性主 -> 灰
                  const sentTone = !hasSent
                    ? 'border-cream-300 text-gray-400 bg-cream-50'
                    : sent.bullish > sent.bearish
                      ? 'border-success/30 text-success bg-success/5'
                      : sent.bearish > sent.bullish
                        ? 'border-danger/30 text-danger bg-danger/5'
                        : 'border-cream-300 text-gray-500 bg-cream-100'
                  const sentTitle = hasSent
                    ? `近 7 天 X 舆情: 看涨 ${sent.bullish} / 看跌 ${sent.bearish} / 中性 ${sent.neutral}${sent.latest ? '\n最新: @' + sent.latest.username + ' - ' + sent.latest.text_zh : ''}`
                    : '近 7 天无 X 推文提及'
                  return (
                    <div
                      key={it.symbol}
                      className="flex items-center justify-between px-4 py-3 bg-cream-100 border border-cream-300 rounded-md group hover:border-copper/40 transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <span className="font-mono font-semibold text-sm tracking-wide w-16">{it.symbol}</span>
                        <span className="text-xs text-gray-500 truncate flex-1">{getCnName(it.symbol, '')}</span>
                      </div>
                      <div className="flex items-center gap-4">
                        <span
                          className={`font-mono text-[10px] px-2 py-0.5 rounded border tabular-nums whitespace-nowrap ${sentTone}`}
                          title={sentTitle}
                        >
                          {hasSent
                            ? `↑${sent.bullish} ↓${sent.bearish}`
                            : '—'}
                        </span>
                        <span className="font-mono text-sm tabular-nums w-20 text-right">
                          {q?.price != null ? `$${q.price.toFixed(2)}` : '-'}
                        </span>
                        <span className={`font-mono text-xs tabular-nums w-16 text-right font-medium ${chgColor}`}>
                          {chgText}
                        </span>
                        <span className="text-[11px] text-cream-500 font-mono w-20 text-right">{formatAddedAt(it.added_at)}</span>
                        <button
                          onClick={() => handleRemove(it.symbol)}
                          className="text-danger opacity-0 group-hover:opacity-100 transition-opacity text-lg leading-none w-4"
                          title="删除"
                        >
                          &times;
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
