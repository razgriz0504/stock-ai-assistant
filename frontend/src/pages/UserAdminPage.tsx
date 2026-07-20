import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Card, CardHeader, Button, Input, Badge } from '@/components/ui'
import { useAuthStore, AuthUser } from '@/stores/authStore'

interface UserItem extends AuthUser {}

interface CreateForm {
  username: string
  password: string
  display_name: string
  role: 'admin' | 'user'
}

const EMPTY_CREATE: CreateForm = {
  username: '',
  password: '',
  display_name: '',
  role: 'user',
}

export default function UserAdminPage() {
  const queryClient = useQueryClient()
  const currentUser = useAuthStore((s) => s.user)

  const [createForm, setCreateForm] = useState<CreateForm>(EMPTY_CREATE)
  const [resetPasswordFor, setResetPasswordFor] = useState<{ id: number; value: string } | null>(null)
  const [status, setStatus] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)

  function flash(msg: string, type: 'ok' | 'err' = 'ok') {
    setStatus({ msg, type })
    setTimeout(() => setStatus(null), 3000)
  }

  const { data: users = [], isLoading } = useQuery<UserItem[]>({
    queryKey: ['admin-users'],
    queryFn: async () => {
      const res = await api.get('/api/admin/users')
      return res.data
    },
  })

  const createMut = useMutation({
    mutationFn: async (form: CreateForm) => {
      await api.post('/api/admin/users', {
        username: form.username.trim(),
        password: form.password,
        display_name: form.display_name.trim(),
        role: form.role,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      setCreateForm(EMPTY_CREATE)
      flash('用户已创建')
    },
    onError: (e: unknown) => {
      const err = e as { response?: { data?: { detail?: string } } }
      flash(err.response?.data?.detail || '创建失败', 'err')
    },
  })

  const updateMut = useMutation({
    mutationFn: async ({ id, patch }: { id: number; patch: Record<string, unknown> }) => {
      await api.patch(`/api/admin/users/${id}`, patch)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      flash('已更新')
    },
    onError: (e: unknown) => {
      const err = e as { response?: { data?: { detail?: string } } }
      flash(err.response?.data?.detail || '操作失败', 'err')
    },
  })

  const deleteMut = useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/api/admin/users/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      flash('已删除')
    },
    onError: (e: unknown) => {
      const err = e as { response?: { data?: { detail?: string } } }
      flash(err.response?.data?.detail || '删除失败', 'err')
    },
  })

  const firstAdminId = users.filter((u) => u.role === 'admin').reduce<number | null>(
    (min, u) => (min === null ? u.id : Math.min(min, u.id)),
    null,
  )

  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          User Admin
        </span>
        <h1 className="page-title">用户<span className="text-copper">管理</span></h1>
        <p className="text-sm text-gray-500 mt-2">创建、禁用、删除账号，或重置密码</p>
      </div>

      {status && (
        <div className={`mb-4 text-sm ${status.type === 'ok' ? 'text-success' : 'text-danger'}`}>
          {status.msg}
        </div>
      )}

      {/* 新建用户 */}
      <Card className="mb-6">
        <CardHeader title="新建用户" label="Create User" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <Input
            label="用户名"
            placeholder="alice"
            value={createForm.username}
            onChange={(e) => setCreateForm((f) => ({ ...f, username: e.target.value }))}
          />
          <Input
            label="初始密码"
            type="password"
            placeholder="至少 6 位"
            value={createForm.password}
            onChange={(e) => setCreateForm((f) => ({ ...f, password: e.target.value }))}
          />
          <Input
            label="显示名（可选）"
            placeholder="Alice"
            value={createForm.display_name}
            onChange={(e) => setCreateForm((f) => ({ ...f, display_name: e.target.value }))}
          />
          <div className="space-y-1.5">
            <label className="block font-mono text-[10px] tracking-[1.5px] uppercase text-gray-500">
              角色
            </label>
            <select
              className="w-full px-3.5 py-2.5 text-sm bg-white border border-cream-300 rounded-md focus:outline-none focus:border-copper"
              value={createForm.role}
              onChange={(e) => setCreateForm((f) => ({ ...f, role: e.target.value as 'admin' | 'user' }))}
            >
              <option value="user">普通用户</option>
              <option value="admin">管理员</option>
            </select>
          </div>
        </div>
        <div className="mt-4">
          <Button
            variant="primary"
            disabled={createMut.isPending}
            onClick={() => {
              if (!createForm.username.trim() || !createForm.password) {
                flash('请填写用户名和密码', 'err')
                return
              }
              createMut.mutate(createForm)
            }}
          >
            {createMut.isPending ? '创建中...' : '创建用户'}
          </Button>
        </div>
      </Card>

      {/* 用户列表 */}
      <Card>
        <CardHeader title="用户列表" label={`Total ${users.length}`} />
        {isLoading ? (
          <div className="py-10 text-center text-sm text-gray-500">加载中...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-gray-500 border-b border-cream-300">
                  <th className="py-2 pr-4">ID</th>
                  <th className="py-2 pr-4">用户名</th>
                  <th className="py-2 pr-4">显示名</th>
                  <th className="py-2 pr-4">角色</th>
                  <th className="py-2 pr-4">状态</th>
                  <th className="py-2 pr-4">上次登录</th>
                  <th className="py-2 pr-4">操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const isSelf = currentUser?.id === u.id
                  const isFirstAdmin = firstAdminId === u.id
                  const locked = isSelf || isFirstAdmin
                  return (
                    <tr key={u.id} className="border-b border-cream-200">
                      <td className="py-3 pr-4 font-mono text-xs">{u.id}</td>
                      <td className="py-3 pr-4">{u.username}{isSelf && <span className="ml-1 text-xs text-gray-400">(我)</span>}</td>
                      <td className="py-3 pr-4 text-gray-600">{u.display_name || '-'}</td>
                      <td className="py-3 pr-4">
                        <Badge variant={u.role === 'admin' ? 'warning' : 'default'}>
                          {u.role === 'admin' ? '管理员' : '用户'}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4">
                        <Badge variant={u.is_active ? 'success' : 'default'}>
                          {u.is_active ? '启用' : '禁用'}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4 text-xs text-gray-500">
                        {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : '-'}
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex flex-wrap gap-2">
                          <Button
                            variant="ghost"
                            className="!py-1 !px-2 text-xs"
                            disabled={locked}
                            onClick={() => updateMut.mutate({
                              id: u.id,
                              patch: { role: u.role === 'admin' ? 'user' : 'admin' },
                            })}
                          >
                            {u.role === 'admin' ? '降为用户' : '提为管理员'}
                          </Button>
                          <Button
                            variant="ghost"
                            className="!py-1 !px-2 text-xs"
                            disabled={locked}
                            onClick={() => updateMut.mutate({
                              id: u.id,
                              patch: { is_active: !u.is_active },
                            })}
                          >
                            {u.is_active ? '禁用' : '启用'}
                          </Button>
                          <Button
                            variant="ghost"
                            className="!py-1 !px-2 text-xs"
                            onClick={() => setResetPasswordFor({ id: u.id, value: '' })}
                          >
                            重置密码
                          </Button>
                          <Button
                            variant="ghost"
                            className="!py-1 !px-2 text-xs text-danger"
                            disabled={locked}
                            onClick={() => {
                              if (confirm(`确定删除用户 ${u.username} ?`)) {
                                deleteMut.mutate(u.id)
                              }
                            }}
                          >
                            删除
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
                {users.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-sm text-gray-500">
                      暂无用户
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* 重置密码弹窗 */}
      {resetPasswordFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="font-heading text-lg font-bold mb-4">重置密码</h3>
            <Input
              label="新密码"
              type="password"
              placeholder="至少 6 位"
              value={resetPasswordFor.value}
              onChange={(e) => setResetPasswordFor((s) => (s ? { ...s, value: e.target.value } : s))}
              autoFocus
            />
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="ghost" onClick={() => setResetPasswordFor(null)}>取消</Button>
              <Button
                variant="primary"
                disabled={!resetPasswordFor.value || resetPasswordFor.value.length < 6}
                onClick={() => {
                  const target = resetPasswordFor
                  if (!target) return
                  updateMut.mutate(
                    { id: target.id, patch: { new_password: target.value } },
                    { onSuccess: () => setResetPasswordFor(null) },
                  )
                }}
              >
                确认重置
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
