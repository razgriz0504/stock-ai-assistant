import { create } from 'zustand'
import { api } from '@/api/client'

// ── 类型定义 ──────────────────────────────────────────────────────

export interface AuthUser {
  id: number
  username: string
  display_name: string
  role: 'admin' | 'user'
  is_active: boolean
  created_at: string | null
  last_login_at: string | null
}

interface LoginResponse {
  access_token: string
  token_type: string
  expires_in_days: number
  user: AuthUser
}

interface AuthState {
  token: string | null
  user: AuthUser | null
  isAuthenticated: boolean
  loading: boolean
  error: string | null
  initialized: boolean

  login: (username: string, password: string) => Promise<void>
  logout: () => void
  fetchMe: () => Promise<void>
  changePassword: (oldPassword: string, newPassword: string) => Promise<void>
  hydrate: () => Promise<void>
}

const STORAGE_KEY = 'stockai_token'

function loadToken(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function saveToken(token: string | null) {
  try {
    if (token) localStorage.setItem(STORAGE_KEY, token)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: loadToken(),
  user: null,
  isAuthenticated: !!loadToken(),
  loading: false,
  error: null,
  initialized: false,

  login: async (username: string, password: string) => {
    set({ loading: true, error: null })
    try {
      const res = await api.post<LoginResponse>('/api/auth/login', { username, password })
      const { access_token, user } = res.data
      saveToken(access_token)
      set({
        token: access_token,
        user,
        isAuthenticated: true,
        loading: false,
        error: null,
        initialized: true,
      })
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      const msg = err.response?.data?.detail || err.message || '登录失败'
      set({ loading: false, error: msg, isAuthenticated: false, user: null, token: null })
      saveToken(null)
      throw new Error(msg)
    }
  },

  logout: () => {
    saveToken(null)
    set({ token: null, user: null, isAuthenticated: false, error: null })
  },

  fetchMe: async () => {
    const token = get().token
    if (!token) {
      set({ isAuthenticated: false, user: null, initialized: true })
      return
    }
    try {
      const res = await api.get<AuthUser>('/api/auth/me')
      set({ user: res.data, isAuthenticated: true, initialized: true })
    } catch {
      // 401 已由拦截器统一登出，这里只兜底
      saveToken(null)
      set({ token: null, user: null, isAuthenticated: false, initialized: true })
    }
  },

  changePassword: async (oldPassword: string, newPassword: string) => {
    await api.post('/api/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    })
  },

  hydrate: async () => {
    if (get().initialized) return
    const token = get().token
    if (!token) {
      set({ initialized: true })
      return
    }
    await get().fetchMe()
  },
}))

/** 供拦截器使用：token 失效时清空状态 */
export function clearAuthOnUnauthorized() {
  saveToken(null)
  useAuthStore.setState({
    token: null,
    user: null,
    isAuthenticated: false,
    error: '登录已过期，请重新登录',
  })
}
