import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Card, CardHeader, Button, Badge, Input } from '@/components/ui'
import { Tabs } from '@/components/ui'

interface ReportItem {
  id: number
  version: string
  status: string
  trigger: string
  model_name: string
  report_date: string | null
  error_message: string | null
  created_at: string | null
}

interface ScheduleConfig {
  enabled: boolean
  frequency: string
  day_of_week: string
  hour: number
  minute: number
}

const promptLabels: Record<string, string> = {
  market_system_prompt: '大盘分析',
  capital_system_prompt: '资金面',
  geopolitics_system_prompt: '国际局势',
  sector_system_prompt: '行业轮动',
  stocks_system_prompt: '个股评分',
  yield_curve_system_prompt: '收益率曲线',
  x_tweet_system_prompt: 'X 推文摘要',
  x_monitor_system_prompt: 'X 舆情总结',
  sector_strength_system_prompt: '板块强度',
}

export default function ReportAdminPage() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('reports')
  const [generatingId, setGeneratingId] = useState<number | null>(null)

  // ── Queries ──
  const { data: reports, isLoading: loadingReports } = useQuery<ReportItem[]>({
    queryKey: ['admin-reports'],
    queryFn: async () => (await api.get('/api/admin/reports')).data,
  })

  const { data: prompts } = useQuery<Record<string, string>>({
    queryKey: ['admin-prompts'],
    queryFn: async () => (await api.get('/api/admin/prompts')).data,
  })

  const { data: schedule } = useQuery<ScheduleConfig>({
    queryKey: ['admin-schedule'],
    queryFn: async () => (await api.get('/api/admin/schedule')).data,
  })

  // ── Mutations ──
  const generateMutation = useMutation({
    mutationFn: async () => (await api.post('/api/admin/reports/generate', {})).data,
    onSuccess: (data) => {
      setGeneratingId(data.report_id)
      queryClient.invalidateQueries({ queryKey: ['admin-reports'] })
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || err?.message || '未知错误'
      alert(`生成报告失败: ${detail}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => (await api.delete(`/api/admin/reports/${id}`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-reports'] }),
  })

  // ── Polling for generating report ──
  useEffect(() => {
    if (!generatingId) return
    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/api/admin/reports/${generatingId}/status`)
        if (res.data.status === 'completed' || res.data.status === 'failed') {
          setGeneratingId(null)
          queryClient.invalidateQueries({ queryKey: ['admin-reports'] })
        }
      } catch { /* ignore */ }
    }, 3000)
    return () => clearInterval(interval)
  }, [generatingId, queryClient])

  const tabs = [
    { id: 'reports', label: '版本管理' },
    { id: 'prompts', label: 'Prompt 配置' },
    { id: 'schedule', label: '定时任务' },
  ]

  return (
    <div>
      {/* Header */}
      <div className="flex items-end justify-between mb-8">
        <div>
          <span className="section-label flex items-center gap-2 mb-3">
            <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
            Admin Console
          </span>
          <h1 className="page-title">周报<span className="text-copper">管理</span></h1>
        </div>
        <Button onClick={() => window.open('/report', '_self')} variant="secondary" size="sm">
          ← 返回周报
        </Button>
      </div>

      {/* Tabs */}
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      <div className="mt-6">
        {activeTab === 'reports' && (
          <ReportsTab
            reports={reports || []}
            loading={loadingReports}
            generatingId={generatingId}
            onGenerate={() => generateMutation.mutate()}
            onDelete={(id) => deleteMutation.mutate(id)}
            isGenerating={generateMutation.isPending}
          />
        )}
        {activeTab === 'prompts' && <PromptsTab prompts={prompts} />}
        {activeTab === 'schedule' && <ScheduleTab schedule={schedule} />}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// Reports Tab
// ═══════════════════════════════════════════════════════════════
function ReportsTab({
  reports, loading, generatingId, onGenerate, onDelete, isGenerating,
}: {
  reports: ReportItem[]
  loading: boolean
  generatingId: number | null
  onGenerate: () => void
  onDelete: (id: number) => void
  isGenerating: boolean
}) {
  const statusColor = (s: string): 'success' | 'danger' | 'warning' | 'default' => {
    if (s === 'completed') return 'success'
    if (s === 'failed') return 'danger'
    if (s === 'running') return 'warning'
    return 'default'
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-500">所有已生成的周报版本</p>
        <Button
          onClick={onGenerate}
          disabled={isGenerating || !!generatingId}
        >
          {generatingId ? '生成中...' : '生成新报告'}
        </Button>
      </div>

      {generatingId && (
        <div className="mb-4 px-4 py-3 bg-orange-50 border border-copper/20 rounded-lg flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-copper border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-copper font-medium">正在生成报告 (ID: {generatingId})，请等待...</span>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-10">
          <div className="w-5 h-5 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
        </div>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-cream-300">
                  <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">版本</th>
                  <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">日期</th>
                  <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">状态</th>
                  <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">触发</th>
                  <th className="text-left px-3 py-2 font-mono text-[10px] uppercase text-gray-500">模型</th>
                  <th className="text-right px-3 py-2 font-mono text-[10px] uppercase text-gray-500">操作</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.id} className="border-b border-cream-200 hover:bg-cream-100 transition-colors">
                    <td className="px-3 py-2 font-mono font-semibold text-xs">{r.version}</td>
                    <td className="px-3 py-2 font-mono text-xs text-gray-500">{r.report_date?.slice(0, 10) || '-'}</td>
                    <td className="px-3 py-2">
                      <Badge variant={statusColor(r.status)}>{r.status}</Badge>
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-500">{r.trigger}</td>
                    <td className="px-3 py-2 font-mono text-[10px] text-gray-400">{r.model_name}</td>
                    <td className="px-3 py-2 text-right">
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => { if (confirm('确认删除该报告？')) onDelete(r.id) }}
                      >
                        删除
                      </Button>
                    </td>
                  </tr>
                ))}
                {reports.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center py-8 text-sm text-gray-400">暂无报告</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// Prompts Tab
// ═══════════════════════════════════════════════════════════════
function PromptsTab({ prompts }: { prompts?: Record<string, string> }) {
  const queryClient = useQueryClient()
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  const saveMutation = useMutation({
    mutationFn: async (payload: Record<string, string>) =>
      (await api.post('/api/admin/prompts', payload)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-prompts'] })
      setEditingKey(null)
    },
  })

  if (!prompts) return <div className="text-sm text-gray-400">加载中...</div>

  const promptKeys = Object.keys(promptLabels)

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500 mb-4">
        编辑各章节的 AI 分析 System Prompt。修改后在下次生成报告时生效。
      </p>
      {promptKeys.map((key) => (
        <Card key={key}>
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-heading font-semibold text-sm">{promptLabels[key]}</h4>
            {editingKey === key ? (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => {
                    saveMutation.mutate({ [key]: editValue })
                  }}
                  disabled={saveMutation.isPending}
                >
                  保存
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setEditingKey(null)}>
                  取消
                </Button>
              </div>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditingKey(key)
                  setEditValue((prompts as Record<string, string>)[key] || '')
                }}
              >
                编辑
              </Button>
            )}
          </div>
          {editingKey === key ? (
            <textarea
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              rows={8}
              className="w-full px-3 py-2 text-xs font-mono border border-cream-300 rounded-md bg-cream-50 focus:outline-none focus:border-copper resize-y"
            />
          ) : (
            <pre className="text-xs font-mono text-gray-600 bg-cream-50 p-3 rounded-md overflow-x-auto max-h-[100px] overflow-y-auto whitespace-pre-wrap">
              {(prompts as Record<string, string>)[key]?.slice(0, 200) || '(使用默认)'}
              {((prompts as Record<string, string>)[key]?.length || 0) > 200 && '...'}
            </pre>
          )}
        </Card>
      ))}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// Schedule Tab
// ═══════════════════════════════════════════════════════════════
function ScheduleTab({ schedule }: { schedule?: ScheduleConfig }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<ScheduleConfig>({
    enabled: false, frequency: 'weekly', day_of_week: 'fri', hour: 18, minute: 0,
  })

  useEffect(() => {
    if (schedule) setForm(schedule)
  }, [schedule])

  const saveMutation = useMutation({
    mutationFn: async (payload: ScheduleConfig) =>
      (await api.post('/api/admin/schedule', payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-schedule'] }),
  })

  return (
    <Card>
      <CardHeader title="定时生成配置" description="设置自动生成周报的时间" />
      <div className="space-y-5 mt-4">
        {/* Enabled */}
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            className="w-4 h-4 rounded border-cream-300 accent-copper"
          />
          <span className="text-sm font-medium">启用定时任务</span>
        </label>

        {/* Frequency */}
        <div>
          <label className="block text-xs font-mono uppercase text-gray-500 mb-1">频率</label>
          <select
            value={form.frequency}
            onChange={(e) => setForm({ ...form, frequency: e.target.value })}
            className="px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
          >
            <option value="daily">每日</option>
            <option value="weekly">每周</option>
          </select>
        </div>

        {/* Day of week (if weekly) */}
        {form.frequency === 'weekly' && (
          <Input
            label="星期"
            value={form.day_of_week}
            onChange={(e) => setForm({ ...form, day_of_week: e.target.value })}
            hint="例: fri 或 mon-fri"
          />
        )}

        {/* Time */}
        <div className="flex gap-4">
          <div>
            <label className="block text-xs font-mono uppercase text-gray-500 mb-1">小时</label>
            <input
              type="number"
              min={0}
              max={23}
              value={form.hour}
              onChange={(e) => setForm({ ...form, hour: Number(e.target.value) })}
              className="w-20 px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
            />
          </div>
          <div>
            <label className="block text-xs font-mono uppercase text-gray-500 mb-1">分钟</label>
            <input
              type="number"
              min={0}
              max={59}
              value={form.minute}
              onChange={(e) => setForm({ ...form, minute: Number(e.target.value) })}
              className="w-20 px-3 py-2 text-sm border border-cream-300 rounded-md bg-white focus:outline-none focus:border-copper"
            />
          </div>
        </div>

        <Button onClick={() => saveMutation.mutate(form)} disabled={saveMutation.isPending}>
          {saveMutation.isPending ? '保存中...' : '保存配置'}
        </Button>
      </div>
    </Card>
  )
}
