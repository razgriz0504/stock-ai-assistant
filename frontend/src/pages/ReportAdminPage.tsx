import { Card } from '@/components/ui'

export default function ReportAdminPage() {
  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          Admin Console
        </span>
        <h1 className="page-title">周报<span className="text-copper">管理</span></h1>
      </div>
      <Card>
        <p className="text-sm text-gray-500">报告管理页面 — 待实现</p>
      </Card>
    </div>
  )
}
