import { Routes, Route } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { AppLayout } from '@/components/layout/AppLayout'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { AdminRoute } from '@/components/auth/AdminRoute'

// Lazy-loaded pages
const LoginPage = lazy(() => import('@/pages/LoginPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const ReportPage = lazy(() => import('@/pages/ReportPage'))
const ScreenerPage = lazy(() => import('@/pages/ScreenerPage'))
const SectorStrengthPage = lazy(() => import('@/pages/SectorStrengthPage'))
const VcpMonitorPage = lazy(() => import('@/pages/VcpMonitorPage'))
const StorageReportPage = lazy(() => import('@/pages/StorageReportPage'))
const FutuPage = lazy(() => import('@/pages/FutuPage'))
const BacktestPage = lazy(() => import('@/pages/BacktestPage'))
const XMonitorPage = lazy(() => import('@/pages/XMonitorPage'))
const WatchlistPage = lazy(() => import('@/pages/WatchlistPage'))
const ChatPage = lazy(() => import('@/pages/ChatPage'))
const ReportAdminPage = lazy(() => import('@/pages/ReportAdminPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))
const UserAdminPage = lazy(() => import('@/pages/UserAdminPage'))
const ProfilePage = lazy(() => import('@/pages/ProfilePage'))

function PageLoader() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="w-6 h-6 border-2 border-cream-300 border-t-copper rounded-full animate-spin" />
    </div>
  )
}

export default function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        {/* 公开路由：登录页 */}
        <Route path="/login" element={<LoginPage />} />

        {/* 需要登录的路由 */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/report" element={<ReportPage />} />
            <Route path="/screener" element={<ScreenerPage />} />
            <Route path="/sector-strength" element={<SectorStrengthPage />} />
            <Route path="/vcp-monitor" element={<VcpMonitorPage />} />
            <Route path="/storage-report" element={<StorageReportPage />} />
            <Route path="/backtest" element={<BacktestPage />} />
            <Route path="/x-monitor" element={<XMonitorPage />} />
            <Route path="/watchlist" element={<WatchlistPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/profile" element={<ProfilePage />} />

            {/* 仅管理员 */}
            <Route element={<AdminRoute />}>
              <Route path="/futu" element={<FutuPage />} />
              <Route path="/report-admin" element={<ReportAdminPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/admin/users" element={<UserAdminPage />} />
            </Route>
          </Route>
        </Route>
      </Routes>
    </Suspense>
  )
}
