/**
 * 富途看板 — 只读页面（持仓 / 个股 / 板块）。
 * 后端接口见 [futu_api.py](file:///d:/Codes/stock-ai-assistant/app/api/futu_api.py)。
 * 本页面**仅展示**，不含任何下单/撤单入口。
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardHeader, Button, Input, Badge, Tabs } from '@/components/ui'
import {
  fetchStatus,
  fetchSnapshot,
  fetchOrderBook,
  fetchKline,
  fetchPlateList,
  fetchPlateStocks,
  fetchCapitalDistribution,
  fetchPositions,
  fetchAccount,
  type FutuRecord,
} from '@/api/futu'

// ─── 工具 ───
function pick<T = unknown>(row: FutuRecord | undefined, key: string): T | undefined {
  if (!row) return undefined
  const v = row[key]
  return v === null || v === undefined ? undefined : (v as T)
}
function num(row: FutuRecord | undefined, key: string, digits = 2): string {
  const v = pick<number | string>(row, key)
  if (v === undefined) return '-'
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n.toFixed(digits) : String(v)
}
function pct(v: unknown, digits = 2): string {
  if (v === undefined || v === null || v === '') return '-'
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n)) return '-'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(digits)}%`
}
function money(v: unknown, digits = 0): string {
  if (v === undefined || v === null || v === '') return '-'
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n)) return '-'
  return n.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}
function pnlClass(v: unknown): string {
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n) || n === 0) return 'text-gray-700'
  return n > 0 ? 'text-red-600' : 'text-green-600'
}

// ─── 页面 ───
export default function FutuPage() {
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['futu-status'],
    queryFn: fetchStatus,
    refetchInterval: 30_000,
  })

  const disabled = !status?.enabled
  const connected = !!status?.detail?.connected

  const tabs = [
    { id: 'positions', label: '持仓与资金' },
    { id: 'quote', label: '个股详情' },
    { id: 'plate', label: '板块热度' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold">富途看板</h1>
          <p className="text-sm text-gray-500 mt-1">只读行情/持仓/板块，不含下单入口</p>
        </div>
        <StatusBadge loading={statusLoading} enabled={!!status?.enabled} connected={connected} />
      </div>

      {disabled && (
        <Card>
          <div className="p-4 text-sm text-gray-600">
            富途集成尚未启用（<code>FUTU_ENABLED=false</code>）。请在服务器 <code>.env</code> 中开启并重启后端。
            {status?.detail?.reason ? <div className="mt-2 text-gray-400">detail: {String(status.detail.reason)}</div> : null}
          </div>
        </Card>
      )}

      {!disabled && (
        <Tabs tabs={tabs} defaultTab="positions">
          {(active) => (
            <>
              {active === 'positions' && <PositionsPanel />}
              {active === 'quote' && <QuotePanel />}
              {active === 'plate' && <PlatePanel />}
            </>
          )}
        </Tabs>
      )}
    </div>
  )
}

function StatusBadge({ loading, enabled, connected }: { loading: boolean; enabled: boolean; connected: boolean }) {
  if (loading) return <Badge variant="default">检测中…</Badge>
  if (!enabled) return <Badge variant="default">未启用</Badge>
  if (!connected) return <Badge variant="warning">OpenD 未连接</Badge>
  return <Badge variant="success">已连接</Badge>
}

// ─── Tab 1: 持仓与资金 ───
function PositionsPanel() {
  const positions = useQuery({ queryKey: ['futu-positions'], queryFn: fetchPositions, refetchInterval: 30_000 })
  const account = useQuery({ queryKey: ['futu-account'], queryFn: fetchAccount, refetchInterval: 30_000 })
  const acc = account.data?.data ?? {}
  const rows = positions.data?.records ?? []

  const totalMv = pick<number>(acc, 'market_val') ?? 0
  const totalCash = pick<number>(acc, 'cash') ?? 0
  const totalAssets = pick<number>(acc, 'total_assets') ?? totalMv + totalCash

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard label="总资产" value={money(totalAssets, 2)} />
        <StatCard label="持仓市值" value={money(totalMv, 2)} />
        <StatCard label="可用现金" value={money(totalCash, 2)} />
        <StatCard label="购买力" value={money(pick<number>(acc, 'power'), 2)} />
      </div>

      <Card>
        <CardHeader
          title={`持仓（${rows.length}）`}
          description={positions.data ? `${positions.data.trd_env} / ${positions.data.trd_market}` : ''}
          action={
            <Button size="sm" variant="ghost" onClick={() => { positions.refetch(); account.refetch() }}>
              刷新
            </Button>
          }
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-gray-500 uppercase font-mono">
              <tr className="border-b border-cream-300">
                <th className="text-left px-4 py-2">代码</th>
                <th className="text-left px-4 py-2">名称</th>
                <th className="text-right px-4 py-2">持仓</th>
                <th className="text-right px-4 py-2">可卖</th>
                <th className="text-right px-4 py-2">成本</th>
                <th className="text-right px-4 py-2">现价</th>
                <th className="text-right px-4 py-2">市值</th>
                <th className="text-right px-4 py-2">盈亏</th>
                <th className="text-right px-4 py-2">盈亏%</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={9} className="text-center text-gray-400 py-8">
                  {positions.isLoading ? '加载中…' : '暂无持仓'}
                </td></tr>
              )}
              {rows.map((r, i) => (
                <tr key={String(pick(r, 'code') ?? i)} className="border-b border-cream-200 hover:bg-cream-100">
                  <td className="px-4 py-2 font-mono">{String(pick(r, 'code') ?? '-')}</td>
                  <td className="px-4 py-2">{String(pick(r, 'stock_name') ?? '-')}</td>
                  <td className="px-4 py-2 text-right">{money(pick(r, 'qty'), 0)}</td>
                  <td className="px-4 py-2 text-right">{money(pick(r, 'can_sell_qty'), 0)}</td>
                  <td className="px-4 py-2 text-right">{num(r, 'cost_price')}</td>
                  <td className="px-4 py-2 text-right">{num(r, 'nominal_price')}</td>
                  <td className="px-4 py-2 text-right">{money(pick(r, 'market_val'), 2)}</td>
                  <td className={`px-4 py-2 text-right font-medium ${pnlClass(pick(r, 'pl_val'))}`}>{money(pick(r, 'pl_val'), 2)}</td>
                  <td className={`px-4 py-2 text-right font-medium ${pnlClass(pick(r, 'pl_ratio'))}`}>{pct(pick(r, 'pl_ratio'))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <div className="p-4">
        <div className="text-xs text-gray-500 font-mono uppercase tracking-wide">{label}</div>
        <div className="text-2xl font-bold mt-1 font-mono">{value}</div>
      </div>
    </Card>
  )
}

// ─── Tab 2: 个股详情 ───
function QuotePanel() {
  const [input, setInput] = useState('US.AAPL')
  const [code, setCode] = useState('US.AAPL')

  const snap = useQuery({
    queryKey: ['futu-snap', code],
    queryFn: () => fetchSnapshot([code]),
    enabled: !!code,
  })
  const ob = useQuery({
    queryKey: ['futu-ob', code],
    queryFn: () => fetchOrderBook(code, 10),
    enabled: !!code,
    refetchInterval: 5_000,
  })
  const cap = useQuery({
    queryKey: ['futu-cap', code],
    queryFn: () => fetchCapitalDistribution(code),
    enabled: !!code,
  })
  const kl = useQuery({
    queryKey: ['futu-kl', code],
    queryFn: () => fetchKline(code, 'K_DAY', '', '', 30),
    enabled: !!code,
  })

  const row = snap.data?.records[0]
  const bid = (ob.data?.data?.['Bid'] as unknown[]) ?? []
  const ask = (ob.data?.data?.['Ask'] as unknown[]) ?? []
  const capData = cap.data?.data ?? {}
  const klRecords = kl.data?.records ?? []

  return (
    <div className="space-y-6">
      <Card>
        <div className="p-4 flex flex-wrap items-center gap-3">
          <label className="text-sm font-medium">代码</label>
          <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="US.AAPL / HK.00700" className="w-48" />
          <Button size="sm" onClick={() => setCode(input.trim().toUpperCase())}>查询</Button>
          <span className="text-xs text-gray-400">格式：市场.代码，如 US.AAPL / HK.00700</span>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard label="现价" value={num(row, 'last_price')} />
        <StatCard label="涨跌%" value={pct(pick(row, 'change_rate'))} />
        <StatCard label="成交量" value={money(pick(row, 'volume'), 0)} />
        <StatCard label="成交额" value={money(pick(row, 'turnover'), 0)} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader title="买卖盘 (Top 10)" description={code} />
          <div className="grid grid-cols-2 text-xs">
            <div>
              <div className="px-4 py-2 text-gray-500 font-mono">卖盘</div>
              {ask.length === 0 && <div className="px-4 py-2 text-gray-400">-</div>}
              {ask.slice().reverse().map((row10, i) => {
                const arr = Array.isArray(row10) ? row10 as unknown[] : []
                return (
                  <div key={`a-${i}`} className="px-4 py-1 flex justify-between border-b border-cream-200">
                    <span className="text-green-600 font-mono">{String(arr[0] ?? '-')}</span>
                    <span className="font-mono">{money(arr[1], 0)}</span>
                  </div>
                )
              })}
            </div>
            <div>
              <div className="px-4 py-2 text-gray-500 font-mono">买盘</div>
              {bid.length === 0 && <div className="px-4 py-2 text-gray-400">-</div>}
              {bid.map((row10, i) => {
                const arr = Array.isArray(row10) ? row10 as unknown[] : []
                return (
                  <div key={`b-${i}`} className="px-4 py-1 flex justify-between border-b border-cream-200">
                    <span className="text-red-600 font-mono">{String(arr[0] ?? '-')}</span>
                    <span className="font-mono">{money(arr[1], 0)}</span>
                  </div>
                )
              })}
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="资金流入分布" description={code} />
          <div className="p-4 grid grid-cols-2 gap-3 text-sm">
            <FlowRow label="超大单流入" value={pick(capData, 'capital_in_super')} pos />
            <FlowRow label="超大单流出" value={pick(capData, 'capital_out_super')} />
            <FlowRow label="大单流入" value={pick(capData, 'capital_in_big')} pos />
            <FlowRow label="大单流出" value={pick(capData, 'capital_out_big')} />
            <FlowRow label="中单流入" value={pick(capData, 'capital_in_mid')} pos />
            <FlowRow label="中单流出" value={pick(capData, 'capital_out_mid')} />
            <FlowRow label="小单流入" value={pick(capData, 'capital_in_small')} pos />
            <FlowRow label="小单流出" value={pick(capData, 'capital_out_small')} />
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="日 K（最近 30 根）" description={code} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-gray-500 uppercase font-mono">
              <tr className="border-b border-cream-300">
                <th className="text-left px-4 py-2">日期</th>
                <th className="text-right px-4 py-2">开</th>
                <th className="text-right px-4 py-2">高</th>
                <th className="text-right px-4 py-2">低</th>
                <th className="text-right px-4 py-2">收</th>
                <th className="text-right px-4 py-2">成交量</th>
                <th className="text-right px-4 py-2">涨跌%</th>
              </tr>
            </thead>
            <tbody>
              {klRecords.length === 0 && (
                <tr><td colSpan={7} className="text-center text-gray-400 py-6">
                  {kl.isLoading ? '加载中…' : '暂无数据'}
                </td></tr>
              )}
              {klRecords.slice().reverse().map((r, i) => (
                <tr key={String(pick(r, 'time_key') ?? i)} className="border-b border-cream-200">
                  <td className="px-4 py-2 font-mono">{String(pick(r, 'time_key') ?? '-')}</td>
                  <td className="px-4 py-2 text-right">{num(r, 'open')}</td>
                  <td className="px-4 py-2 text-right">{num(r, 'high')}</td>
                  <td className="px-4 py-2 text-right">{num(r, 'low')}</td>
                  <td className="px-4 py-2 text-right">{num(r, 'close')}</td>
                  <td className="px-4 py-2 text-right">{money(pick(r, 'volume'), 0)}</td>
                  <td className={`px-4 py-2 text-right ${pnlClass(pick(r, 'change_rate'))}`}>{pct(pick(r, 'change_rate'))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function FlowRow({ label, value, pos }: { label: string; value: unknown; pos?: boolean }) {
  return (
    <div className="flex justify-between items-center py-1 border-b border-cream-200">
      <span className="text-gray-600">{label}</span>
      <span className={`font-mono font-medium ${pos ? 'text-red-600' : 'text-green-600'}`}>
        {money(value, 0)}
      </span>
    </div>
  )
}

// ─── Tab 3: 板块热度 ───
function PlatePanel() {
  const [market, setMarket] = useState<'US' | 'HK'>('US')
  const [plateClass, setPlateClass] = useState<'INDUSTRY' | 'CONCEPT' | 'REGION'>('INDUSTRY')
  const [selectedPlate, setSelectedPlate] = useState<string>('')

  const plates = useQuery({
    queryKey: ['futu-plates', market, plateClass],
    queryFn: () => fetchPlateList(market, plateClass),
  })
  const stocks = useQuery({
    queryKey: ['futu-plate-stocks', selectedPlate],
    queryFn: () => fetchPlateStocks(selectedPlate),
    enabled: !!selectedPlate,
  })

  const plateRows = plates.data?.records ?? []
  const stockRows = useMemo(() => stocks.data?.records ?? [], [stocks.data])

  return (
    <div className="space-y-6">
      <Card>
        <div className="p-4 flex flex-wrap items-center gap-3">
          <label className="text-sm">市场</label>
          <select
            value={market}
            onChange={(e) => { setMarket(e.target.value as 'US' | 'HK'); setSelectedPlate('') }}
            className="border border-cream-300 rounded px-2 py-1 text-sm"
          >
            <option value="US">美股</option>
            <option value="HK">港股</option>
          </select>
          <label className="text-sm ml-4">分类</label>
          <select
            value={plateClass}
            onChange={(e) => { setPlateClass(e.target.value as 'INDUSTRY' | 'CONCEPT' | 'REGION'); setSelectedPlate('') }}
            className="border border-cream-300 rounded px-2 py-1 text-sm"
          >
            <option value="INDUSTRY">行业</option>
            <option value="CONCEPT">概念</option>
            <option value="REGION">地域</option>
          </select>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader title={`板块列表（${plateRows.length}）`} />
          <div className="overflow-y-auto max-h-[560px]">
            <table className="w-full text-sm">
              <thead className="text-xs text-gray-500 uppercase font-mono sticky top-0 bg-white">
                <tr className="border-b border-cream-300">
                  <th className="text-left px-4 py-2">代码</th>
                  <th className="text-left px-4 py-2">名称</th>
                </tr>
              </thead>
              <tbody>
                {plateRows.length === 0 && (
                  <tr><td colSpan={2} className="text-center text-gray-400 py-6">{plates.isLoading ? '加载中…' : '暂无数据'}</td></tr>
                )}
                {plateRows.map((r, i) => {
                  const c = String(pick(r, 'code') ?? '')
                  return (
                    <tr
                      key={c || i}
                      onClick={() => setSelectedPlate(c)}
                      className={`border-b border-cream-200 cursor-pointer hover:bg-cream-100 ${selectedPlate === c ? 'bg-cream-200' : ''}`}
                    >
                      <td className="px-4 py-2 font-mono text-xs">{c || '-'}</td>
                      <td className="px-4 py-2">{String(pick(r, 'plate_name') ?? '-')}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <CardHeader
            title={selectedPlate ? `成分股（${stockRows.length}）` : '成分股'}
            description={selectedPlate || '请从左侧选择板块'}
          />
          <div className="overflow-y-auto max-h-[560px]">
            <table className="w-full text-sm">
              <thead className="text-xs text-gray-500 uppercase font-mono sticky top-0 bg-white">
                <tr className="border-b border-cream-300">
                  <th className="text-left px-4 py-2">代码</th>
                  <th className="text-left px-4 py-2">名称</th>
                  <th className="text-right px-4 py-2">股票类型</th>
                </tr>
              </thead>
              <tbody>
                {!selectedPlate && (
                  <tr><td colSpan={3} className="text-center text-gray-400 py-6">未选择板块</td></tr>
                )}
                {selectedPlate && stockRows.length === 0 && (
                  <tr><td colSpan={3} className="text-center text-gray-400 py-6">{stocks.isLoading ? '加载中…' : '暂无数据'}</td></tr>
                )}
                {stockRows.map((r, i) => (
                  <tr key={String(pick(r, 'code') ?? i)} className="border-b border-cream-200">
                    <td className="px-4 py-2 font-mono text-xs">{String(pick(r, 'code') ?? '-')}</td>
                    <td className="px-4 py-2">{String(pick(r, 'stock_name') ?? '-')}</td>
                    <td className="px-4 py-2 text-right text-gray-500">{String(pick(r, 'stock_type') ?? '-')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  )
}
