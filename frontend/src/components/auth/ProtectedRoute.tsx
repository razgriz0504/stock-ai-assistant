import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

/**
 * 登录守卫：未登录跳 /login?from=当前路径，已登录透传子路由。
 * 首次挂载会触发 hydrate（用 token 拉 /me）。
 */
export function ProtectedRoute() {
  const location = useLocation()
  const { isAuthenticated, token, initialized, hydrate } = useAuthStore()

  useEffect(() => {
    if (!initialized) {
      void hydrate()
    }
  }, [initialized, hydrate])

  // 有 token 但还没 hydrate 完，显示 loading
  if (token && !initialized) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-6 h-6 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
      </div>
    )
  }

  if (!isAuthenticated) {
    const from = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?from=${from}`} replace />
  }

  return <Outlet />
}
