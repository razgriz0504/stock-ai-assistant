import { FormEvent, useState } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { Card, CardHeader, Button, Input, Badge } from '@/components/ui'

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user)
  const changePassword = useAuthStore((s) => s.changePassword)

  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [status, setStatus] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)
  const [loading, setLoading] = useState(false)

  function flash(msg: string, type: 'ok' | 'err' = 'ok') {
    setStatus({ msg, type })
    setTimeout(() => setStatus(null), 4000)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!oldPassword || !newPassword) {
      flash('请填写完整', 'err')
      return
    }
    if (newPassword.length < 6) {
      flash('新密码至少 6 位', 'err')
      return
    }
    if (newPassword !== confirmPassword) {
      flash('两次输入的新密码不一致', 'err')
      return
    }
    setLoading(true)
    try {
      await changePassword(oldPassword, newPassword)
      flash('密码已修改')
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      flash(err.response?.data?.detail || err.message || '修改失败', 'err')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          My Profile
        </span>
        <h1 className="page-title">个人<span className="text-copper">中心</span></h1>
        <p className="text-sm text-gray-500 mt-2">查看账号信息、修改密码</p>
      </div>

      {/* 账号信息 */}
      <Card className="mb-6">
        <CardHeader title="账号信息" label="Account" />
        {user ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
              <div className="font-mono text-[10px] tracking-widest uppercase text-gray-500 mb-1">用户名</div>
              <div>{user.username}</div>
            </div>
            <div>
              <div className="font-mono text-[10px] tracking-widest uppercase text-gray-500 mb-1">显示名</div>
              <div>{user.display_name || '-'}</div>
            </div>
            <div>
              <div className="font-mono text-[10px] tracking-widest uppercase text-gray-500 mb-1">角色</div>
              <Badge variant={user.role === 'admin' ? 'warning' : 'default'}>
                {user.role === 'admin' ? '管理员' : '普通用户'}
              </Badge>
            </div>
            <div>
              <div className="font-mono text-[10px] tracking-widest uppercase text-gray-500 mb-1">上次登录</div>
              <div className="text-gray-600">
                {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : '-'}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-gray-500">加载中...</div>
        )}
      </Card>

      {/* 修改密码 */}
      <Card>
        <CardHeader title="修改密码" label="Change Password" />
        <form className="space-y-4 max-w-md" onSubmit={handleSubmit}>
          <Input
            label="当前密码"
            type="password"
            autoComplete="current-password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            disabled={loading}
          />
          <Input
            label="新密码（至少 6 位）"
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            disabled={loading}
          />
          <Input
            label="确认新密码"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            disabled={loading}
          />
          {status && (
            <p className={`text-xs ${status.type === 'ok' ? 'text-success' : 'text-danger'}`}>
              {status.msg}
            </p>
          )}
          <Button type="submit" variant="primary" disabled={loading}>
            {loading ? '提交中...' : '确认修改'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
