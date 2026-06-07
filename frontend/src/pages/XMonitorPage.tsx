import { Card } from '@/components/ui'

export default function XMonitorPage() {
  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          X Sentiment Monitor
        </span>
        <h1 className="page-title">X <span className="text-copper">舆情监控</span></h1>
      </div>
      <Card>
        <p className="text-sm text-gray-500">X 舆情监控页面 — 待实现</p>
      </Card>
    </div>
  )
}
