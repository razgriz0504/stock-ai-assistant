import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Card, CardHeader, Button, Input, Badge, Tabs } from '@/components/ui'

interface XAccount {
  id: number
  username: string
  display_name: string
  category: string
  enabled: boolean
  last_fetched_at: string | null
}

interface XTweet {
  id: number
  tweet_id: string
  username: string
  text: string
  text_zh: string
  sentiment: string
  key_points: string[]
  impact_assets: string[]
  market_impact: string
  created_at_x: string | null
}

export default function XMonitorPage() {
  const queryClient = useQueryClient()
  const [filterDays, setFilterDays] = useState(7)
  const [filterUser, setFilterUser] = useState('')

  // Accounts
  const { data: accountsData } = useQuery({
    queryKey: ['x-accounts'],
    queryFn: async () => (await api.get('/api/x-monitor/accounts')).data,
  })

  // Tweets
  const { data: tweetsData, isLoading: tweetsLoading } = useQuery({
    queryKey: ['x-tweets', filterDays, filterUser],
    queryFn: async () => {
      const params = new URLSearchParams({ days: String(filterDays) })
      if (filterUser) params.set('username', filterUser)
      return (await api.get(`/api/x-monitor/tweets?${params}`)).data
    },
  })

  // Config
  const { data: configData } = useQuery({
    queryKey: ['x-config'],
    queryFn: async () => (await api.get('/api/x-monitor/config')).data,
  })

  // Fetch now
  const fetchNowMutation = useMutation({
    mutationFn: async () => (await api.post('/api/x-monitor/fetch-now')).data,
    onSuccess: () => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['x-tweets'] })
        queryClient.invalidateQueries({ queryKey: ['x-accounts'] })
      }, 3000)
    },
  })

  const accounts: XAccount[] = accountsData?.accounts || []
  const tweets: XTweet[] = tweetsData?.tweets || []
  const config = configData || {}

  const sentimentBadge = (s: string) => {
    if (s === 'bullish') return <Badge variant="success">看涨</Badge>
    if (s === 'bearish') return <Badge variant="danger">看跌</Badge>
    return <Badge>中性</Badge>
  }

  const tabs = [
    { id: 'tweets', label: '推文流' },
    { id: 'accounts', label: '账号管理' },
    { id: 'config', label: '抓取配置' },
  ]

  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          X Sentiment Monitor
        </span>
        <h1 className="page-title">X <span className="text-copper">舆情监控</span></h1>
        <p className="text-sm text-gray-500 mt-2">
          捕捉关键账号在 X 上的言论 → AI 翻译/总结/影响评估
        </p>
      </div>

      <Tabs tabs={tabs} defaultTab="tweets">
        {(activeTab) => (
          <>
            {/* Tweets Tab */}
            {activeTab === 'tweets' && (
              <div>
                {/* Filters */}
                <div className="flex gap-3 mb-6 items-center">
                  <select
                    value={filterUser}
                    onChange={e => setFilterUser(e.target.value)}
                    className="px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
                  >
                    <option value="">全部账号</option>
                    {accounts.map(a => (
                      <option key={a.username} value={a.username}>@{a.username}</option>
                    ))}
                  </select>
                  <select
                    value={filterDays}
                    onChange={e => setFilterDays(Number(e.target.value))}
                    className="px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
                  >
                    <option value={1}>最近 1 天</option>
                    <option value={3}>最近 3 天</option>
                    <option value={7}>最近 7 天</option>
                    <option value={30}>最近 30 天</option>
                  </select>
                  <Button size="sm" onClick={() => fetchNowMutation.mutate()} disabled={fetchNowMutation.isPending}>
                    {fetchNowMutation.isPending ? '抓取中...' : '立即抓取'}
                  </Button>
                  {fetchNowMutation.isSuccess && (
                    <span className="text-xs text-success">抓取完成</span>
                  )}
                </div>

                {/* Tweet list */}
                {tweetsLoading ? (
                  <div className="flex justify-center py-12">
                    <div className="w-6 h-6 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
                  </div>
                ) : tweets.length === 0 ? (
                  <Card>
                    <p className="text-center text-sm text-gray-500 py-8">暂无推文数据，请配置 Bearer Token 后点击"立即抓取"</p>
                  </Card>
                ) : (
                  <div className="space-y-4">
                    {tweets.map(t => (
                      <Card key={t.id} hover>
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <span className="font-heading font-semibold text-sm">@{t.username}</span>
                            {sentimentBadge(t.sentiment)}
                          </div>
                          {t.created_at_x && (
                            <span className="font-mono text-xs text-gray-400">
                              {new Date(t.created_at_x).toLocaleDateString('zh-CN')}
                            </span>
                          )}
                        </div>
                        {t.text_zh && <p className="text-sm leading-relaxed mb-2">{t.text_zh}</p>}
                        {t.text && <p className="text-xs text-gray-500 italic mb-3">{t.text}</p>}
                        {t.impact_assets && t.impact_assets.length > 0 && (
                          <div className="flex gap-1.5 flex-wrap mb-2">
                            {t.impact_assets.map((asset, i) => (
                              <span key={i} className="font-mono text-xs px-2 py-0.5 rounded bg-cream-200 text-copper">
                                {asset}
                              </span>
                            ))}
                          </div>
                        )}
                        {t.market_impact && (
                          <div className="text-xs text-gray-600 bg-cream-100 rounded-md p-3 mt-2">
                            {t.market_impact}
                          </div>
                        )}
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Accounts Tab */}
            {activeTab === 'accounts' && (
              <Card>
                <CardHeader title={`监控账号（${accounts.length}）`} />
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-cream-300">
                        <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">Username</th>
                        <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">名称</th>
                        <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">分类</th>
                        <th className="text-center px-3 py-2 font-mono text-[10px] uppercase text-gray-500">状态</th>
                        <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">最近抓取</th>
                      </tr>
                    </thead>
                    <tbody>
                      {accounts.map(a => (
                        <tr key={a.id} className="border-b border-cream-200 hover:bg-cream-50">
                          <td className="px-3 py-2.5 font-mono text-xs font-semibold">@{a.username}</td>
                          <td className="px-3 py-2.5 text-xs">{a.display_name}</td>
                          <td className="px-3 py-2.5"><Badge>{a.category}</Badge></td>
                          <td className="px-3 py-2.5 text-center">
                            <Badge variant={a.enabled ? 'success' : 'default'}>
                              {a.enabled ? '启用' : '禁用'}
                            </Badge>
                          </td>
                          <td className="px-3 py-2.5 text-xs text-gray-500 font-mono">
                            {a.last_fetched_at ? new Date(a.last_fetched_at).toLocaleString('zh-CN') : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}

            {/* Config Tab */}
            {activeTab === 'config' && (
              <ConfigPanel config={config} />
            )}
          </>
        )}
      </Tabs>
    </div>
  )
}

function ConfigPanel({ config }: { config: Record<string, unknown> }) {
  const queryClient = useQueryClient()
  const [token, setToken] = useState('')
  const [interval, setInterval_] = useState(String(config.x_monitor_interval_hours || 4))
  const [status, setStatus] = useState('')

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        x_monitor_interval_hours: parseInt(interval) || 4,
      }
      if (token.trim()) payload.x_api_bearer_token = token.trim()
      await api.post('/api/x-monitor/config', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['x-config'] })
      setToken('')
      setStatus('配置已保存')
      setTimeout(() => setStatus(''), 3000)
    },
  })

  return (
    <Card>
      <CardHeader title="抓取配置" label="X API Configuration" />
      <div className="space-y-4 max-w-lg">
        <Input
          label="X API Bearer Token"
          type="password"
          value={token}
          onChange={e => setToken(e.target.value)}
          placeholder={config.token_configured ? '••••••••（已配置，留空保持不变）' : '输入 Bearer Token'}
          hint="或通过环境变量 X_API_BEARER_TOKEN 配置"
        />
        <Input
          label="抓取间隔（小时）"
          type="number"
          value={interval}
          onChange={e => setInterval_(e.target.value)}
        />
        <div className="flex items-center gap-4">
          <Button variant="primary" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
            保存配置
          </Button>
          {status && <span className="text-sm text-success">{status}</span>}
        </div>
      </div>
    </Card>
  )
}
