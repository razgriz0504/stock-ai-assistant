import axios from 'axios'

const baseURL = import.meta.env.VITE_API_URL || ''

export const api = axios.create({
  baseURL,
  timeout: 60_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor: 自动附加 Authorization 头
api.interceptors.request.use((config) => {
  try {
    const token = localStorage.getItem('stockai_token')
    if (token) {
      config.headers = config.headers || {}
      config.headers.Authorization = `Bearer ${token}`
    }
  } catch {
    /* ignore storage errors */
  }
  return config
})

// Response interceptor: 401 自动登出并跳登录
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    if (status === 401) {
      // 避免登录接口自身循环
      const url: string = error.config?.url || ''
      if (!url.includes('/api/auth/login')) {
        // 动态引入避免循环依赖
        import('@/stores/authStore').then((mod) => {
          mod.clearAuthOnUnauthorized()
          if (window.location.pathname !== '/login') {
            const from = window.location.pathname + window.location.search
            window.location.href = `/login?from=${encodeURIComponent(from)}`
          }
        })
      }
    }
    console.error('[API Error]', status, error.message)
    return Promise.reject(error)
  },
)
