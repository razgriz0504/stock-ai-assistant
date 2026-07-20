import { useEffect } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

/**
 * 管理员守卫：登录且 role='admin' 才允许通过；否则回首页。
 * 必须嵌套在 ProtectedRoute 之下。
 */
export function AdminRoute() {
  const { user } = useAuthStore()

  useEffect(() => {
    if (user && user.role !== 'admin') {
      // 简单提示（后续可接 toast 组件）
      console.warn('[AdminRoute] 需要管理员权限')
    }
  }, [user])

  if (!user) {
    // ProtectedRoute 会先拦截，但兜底一次
    return <Navigate to="/login" replace />
  }
  if (user.role !== 'admin') {
    return <Navigate to="/" replace />
  }
  return <Outlet />
}
