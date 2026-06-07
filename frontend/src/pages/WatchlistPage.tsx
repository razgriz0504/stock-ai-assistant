import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Card, CardHeader, Button, Input } from '@/components/ui'

export default function WatchlistPage() {
  const queryClient = useQueryClient()
  const [input, setInput] = useState('')
  const [status, setStatus] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['watchlist'],
    queryFn: async () => {
      const res = await api.get('/api/watchlist')
      return res.data.stocks as string[]
    },
  })

  const stocks = data || []

  const mutation = useMutation({
    mutationFn: async (newStocks: string[]) => {
      const res = await api.post('/api/watchlist', { stocks: newStocks })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] })
    },
  })

  const addStocks = () => {
    if (!input.trim()) return
    const newOnes = input.split(/[,，\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean)
    const added: string[] = []
    const combined = [...stocks]
    for (const s of newOnes) {
      if (!combined.includes(s)) {
        combined.push(s)
        added.push(s)
      }
    }
    setInput('')
    if (added.length > 0) {
      mutation.mutate(combined)
      showStatus(`已添加: ${added.join(', ')}`, 'ok')
    } else {
      showStatus('股票已在列表中', 'err')
    }
  }

  const removeStock = (symbol: string) => {
    const updated = stocks.filter(s => s !== symbol)
    mutation.mutate(updated)
    showStatus(`已移除: ${symbol}`, 'ok')
  }

  const showStatus = (msg: string, type: 'ok' | 'err') => {
    setStatus({ msg, type })
    setTimeout(() => setStatus(null), 3000)
  }

  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          Watchlist
        </span>
        <h1 className="page-title">关注<span className="text-copper">列表</span></h1>
        <p className="text-sm text-gray-500 mt-2">管理投研周报评分的股票池</p>
      </div>

      <Card>
        <CardHeader title="股票管理" label={stocks.length > 0 ? `${stocks.length} 只股票` : undefined} />

        {/* Input */}
        <div className="flex gap-3 mb-6">
          <div className="flex-1">
            <Input
              placeholder="输入股票代码，多个用逗号分隔（如 AAPL, TSLA, NVDA）"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addStocks()}
            />
          </div>
          <Button variant="primary" onClick={addStocks}>
            添加
          </Button>
        </div>

        {/* Status */}
        {status && (
          <p className={`text-xs mb-4 ${status.type === 'ok' ? 'text-success' : 'text-danger'}`}>
            {status.msg}
          </p>
        )}

        {/* List */}
        {isLoading ? (
          <div className="text-center py-8 text-cream-500 text-sm">加载中...</div>
        ) : stocks.length === 0 ? (
          <div className="text-center py-8 text-cream-500 text-sm">暂无关注股票，请在上方添加</div>
        ) : (
          <div className="space-y-2">
            {stocks.map((symbol) => (
              <div
                key={symbol}
                className="flex items-center justify-between px-4 py-3 bg-cream-100 border border-cream-300 rounded-md group"
              >
                <span className="font-mono font-semibold text-sm tracking-wide">{symbol}</span>
                <button
                  onClick={() => removeStock(symbol)}
                  className="text-danger opacity-0 group-hover:opacity-100 transition-opacity text-lg leading-none"
                  title="删除"
                >
                  &times;
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
