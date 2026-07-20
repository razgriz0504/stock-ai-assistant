import { Routes, Route } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { AppLayout } from '@/components/layout/AppLayout'

// Lazy-loaded pages
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
        <Route element={<AppLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/report" element={<ReportPage />} />
          <Route path="/screener" element={<ScreenerPage />} />
          <Route path="/sector-strength" element={<SectorStrengthPage />} />
          <Route path="/vcp-monitor" element={<VcpMonitorPage />} />
          <Route path="/storage-report" element={<StorageReportPage />} />
          <Route path="/futu" element={<FutuPage />} />
          <Route path="/backtest" element={<BacktestPage />} />
          <Route path="/x-monitor" element={<XMonitorPage />} />
          <Route path="/watchlist" element={<WatchlistPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/report-admin" element={<ReportAdminPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
