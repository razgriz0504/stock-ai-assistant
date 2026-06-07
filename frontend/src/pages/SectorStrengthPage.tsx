import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Card, Button, Badge } from '@/components/ui'

interface SectorItem {
  symbol: string
  name: string
  category: string
  price: number
  change_1d: number
  change_1w: number
  change_1m: number
  rs_score: number
  flow_signal: string
  volume_ratio: number
}

type SortKey = 'rs_score' | 'change_1d' | 'change_1w' | 'change_1m' | 'volume_ratio'

export default function SectorStrengthPage() {
  const [sortBy, setSortBy] = useState<SortKey>('rs_score')
  const [filterCat, setFilterCat] = useState<string>('')

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['sector-strength'],
    queryFn: async () => {
      const res = await api.get('/api/sector-strength/data')
      return res.data
    },
    staleTime: 60_000,
  })

  const sectors: SectorItem[] = data?.sectors || []
  const updatedAt = data?.updated_at || ''

  const filtered = sectors
    .filter(s => !filterCat || s.category === filterCat)
    .sort((a, b) => (b[sortBy] ?? 0) - (a[sortBy] ?? 0))

  const categories = [...new Set(sectors.map(s => s.category))].filter(Boolean)

  const fmtPct = (v: number | null) => {
    if (v == null) return '-'
    const sign = v >= 0 ? '+' : ''
    return `${sign}${v.toFixed(2)}%`
  }

  const pctColor = (v: number | null) => {
    if (v == null) return 'text-gray-500'
    return v > 0 ? 'text-success' : v < 0 ? 'text-danger' : 'text-gray-500'
  }

  return (
    <div>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <span className="section-label flex items-center gap-2 mb-3">
            <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
            Sector Radar
          </span>
          <h1 className="page-title">板块强度<span className="text-copper">雷达</span></h1>
        </div>
        <div className="flex items-center gap-3">
          {updatedAt && <span className="text-xs text-gray-500 font-mono">{updatedAt}</span>}
          <Button size="sm" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? '刷新中...' : '刷新'}
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-4 flex-wrap">
        <button
          onClick={() => setFilterCat('')}
          className={`px-3 py-1.5 text-xs font-mono rounded-full border transition-all ${
            !filterCat ? 'border-copper text-copper bg-orange-50' : 'border-cream-300 text-gray-500 hover:text-gray-900'
          }`}
        >
          全部
        </button>
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => setFilterCat(cat)}
            className={`px-3 py-1.5 text-xs font-mono rounded-full border transition-all ${
              filterCat === cat ? 'border-copper text-copper bg-orange-50' : 'border-cream-300 text-gray-500 hover:text-gray-900'
            }`}
          >
            {cat}
          </button>
        ))}
        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value as SortKey)}
          className="ml-auto px-3 py-1.5 text-xs font-mono border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
        >
          <option value="rs_score">RS 评分</option>
          <option value="change_1d">日涨跌</option>
          <option value="change_1w">周涨跌</option>
          <option value="change_1m">月涨跌</option>
          <option value="volume_ratio">量比</option>
        </select>
      </div>

      {/* Table */}
      <Card className="p-0 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-6 h-6 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-cream-300 bg-cream-100">
                  <th className="text-left px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">#</th>
                  <th className="text-left px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">ETF</th>
                  <th className="text-left px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">分类</th>
                  <th className="text-right px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">价格</th>
                  <th className="text-right px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">日涨跌</th>
                  <th className="text-right px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">周涨跌</th>
                  <th className="text-right px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">月涨跌</th>
                  <th className="text-right px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">RS</th>
                  <th className="text-center px-4 py-3 font-mono text-[10px] tracking-wider uppercase text-gray-500">资金流向</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s, i) => (
                  <tr key={s.symbol} className="border-b border-cream-200 hover:bg-cream-50 transition-colors">
                    <td className="px-4 py-3 text-xs text-gray-400">{i + 1}</td>
                    <td className="px-4 py-3">
                      <span className="font-mono font-semibold text-xs">{s.symbol}</span>
                      <span className="text-xs text-gray-500 ml-2">{s.name}</span>
                    </td>
                    <td className="px-4 py-3">
                      <Badge>{s.category}</Badge>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">${s.price?.toFixed(2)}</td>
                    <td className={`px-4 py-3 text-right font-mono text-xs font-medium ${pctColor(s.change_1d)}`}>
                      {fmtPct(s.change_1d)}
                    </td>
                    <td className={`px-4 py-3 text-right font-mono text-xs font-medium ${pctColor(s.change_1w)}`}>
                      {fmtPct(s.change_1w)}
                    </td>
                    <td className={`px-4 py-3 text-right font-mono text-xs font-medium ${pctColor(s.change_1m)}`}>
                      {fmtPct(s.change_1m)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs font-bold">{s.rs_score?.toFixed(1)}</td>
                    <td className="px-4 py-3 text-center">
                      <Badge variant={s.flow_signal === 'inflow' ? 'success' : s.flow_signal === 'outflow' ? 'danger' : 'default'}>
                        {s.flow_signal === 'inflow' ? '流入' : s.flow_signal === 'outflow' ? '流出' : '中性'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
