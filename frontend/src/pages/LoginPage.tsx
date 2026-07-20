import { FormEvent, useState } from 'react'
import { useNavigate, useLocation, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { Button, Input, Card } from '@/components/ui'

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login, isAuthenticated, loading, error } = useAuthStore()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  // 已登录直接跳走
  if (isAuthenticated) {
    const params = new URLSearchParams(location.search)
    const from = params.get('from') || '/'
    return <Navigate to={from} replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLocalError(null)
    if (!username.trim() || !password) {
      setLocalError('请输入用户名和密码')
      return
    }
    try {
      await login(username.trim(), password)
      const params = new URLSearchParams(location.search)
      const from = params.get('from') || '/'
      navigate(from, { replace: true })
    } catch {
      // authStore 已把错误写入 state
    }
  }

  const errMsg = localError || error

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream-50 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="font-heading text-3xl font-bold tracking-tight">
            Stock <span className="text-copper">AI</span>
          </h1>
          <p className="text-xs text-gray-500 mt-1 font-mono tracking-widest">ASSISTANT · SIGN IN</p>
        </div>

        <Card>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <Input
              label="用户名"
              type="text"
              autoComplete="username"
              placeholder="admin"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              autoFocus
            />
            <Input
              label="密码"
              type="password"
              autoComplete="current-password"
              placeholder="请输入密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
            />
            {errMsg && (
              <p className="text-xs text-danger">{errMsg}</p>
            )}
            <Button
              type="submit"
              variant="primary"
              className="w-full"
              disabled={loading}
            >
              {loading ? '登录中...' : '登 录'}
            </Button>
          </form>
        </Card>

        <p className="text-center text-xs text-gray-400 mt-6 font-mono">
          没有账号？请联系管理员创建。
        </p>
      </div>
    </div>
  )
}
