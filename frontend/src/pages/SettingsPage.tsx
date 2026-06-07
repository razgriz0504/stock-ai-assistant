import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Card, CardHeader, Button, Input, Badge } from '@/components/ui'

interface SettingsData {
  current_model: string
  models: Record<string, { display_name: string; provider: string; available: boolean }>
  api_keys: Record<string, { label: string; provider: string; configured: boolean }>
}

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [keyValues, setKeyValues] = useState<Record<string, string>>({})
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [status, setStatus] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)

  const { data, isLoading } = useQuery<SettingsData>({
    queryKey: ['settings'],
    queryFn: async () => {
      const res = await api.get('/api/settings')
      return res.data
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    select: (d: any) => {
      if (!selectedModel && d.current_model) setSelectedModel(d.current_model)
      return d
    },
  })

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload: { default_model?: string; api_keys?: Record<string, string> } = {}
      if (selectedModel && selectedModel !== data?.current_model) {
        payload.default_model = selectedModel
      }
      const nonEmptyKeys = Object.fromEntries(
        Object.entries(keyValues).filter(([, v]) => v.trim())
      )
      if (Object.keys(nonEmptyKeys).length > 0) {
        payload.api_keys = nonEmptyKeys
      }
      await api.post('/api/settings', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setKeyValues({})
      setStatus({ msg: '设置已保存', type: 'ok' })
      setTimeout(() => setStatus(null), 3000)
    },
    onError: () => {
      setStatus({ msg: '保存失败', type: 'err' })
      setTimeout(() => setStatus(null), 3000)
    },
  })

  if (isLoading || !data) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-6 h-6 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          Settings
        </span>
        <h1 className="page-title">系统<span className="text-copper">设置</span></h1>
        <p className="text-sm text-gray-500 mt-2">配置 AI 模型和 API 密钥</p>
      </div>

      {/* Model Selection */}
      <Card className="mb-6">
        <CardHeader title="默认模型" label="LLM Configuration" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {Object.entries(data.models).map(([key, model]) => (
            <button
              key={key}
              onClick={() => setSelectedModel(key)}
              className={`
                text-left p-4 rounded-lg border transition-all
                ${selectedModel === key
                  ? 'border-copper bg-orange-50/50'
                  : 'border-cream-300 hover:border-copper/40'
                }
              `}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-xs font-semibold">{model.display_name}</span>
                <Badge variant={model.available ? 'success' : 'default'}>
                  {model.available ? '可用' : '未配置'}
                </Badge>
              </div>
              <span className="text-xs text-gray-500">{model.provider}</span>
            </button>
          ))}
        </div>
      </Card>

      {/* API Keys */}
      <Card className="mb-6">
        <CardHeader title="API 密钥" label="Provider Keys" />
        <div className="space-y-4">
          {Object.entries(data.api_keys).map(([field, info]) => (
            <div key={field} className="flex items-end gap-4">
              <div className="flex-1">
                <Input
                  label={info.label}
                  type="password"
                  placeholder={info.configured ? '••••••••（已配置，留空保持不变）' : '输入 API Key'}
                  value={keyValues[field] || ''}
                  onChange={e => setKeyValues(prev => ({ ...prev, [field]: e.target.value }))}
                />
              </div>
              <Badge variant={info.configured ? 'success' : 'warning'} className="mb-2">
                {info.configured ? '已配置' : '未配置'}
              </Badge>
            </div>
          ))}
        </div>
      </Card>

      {/* Save */}
      <div className="flex items-center gap-4">
        <Button variant="primary" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
          {saveMutation.isPending ? '保存中...' : '保存设置'}
        </Button>
        {status && (
          <span className={`text-sm ${status.type === 'ok' ? 'text-success' : 'text-danger'}`}>
            {status.msg}
          </span>
        )}
      </div>
    </div>
  )
}
