import { Card } from '@/components/ui'

export default function ChatPage() {
  return (
    <div>
      <div className="mb-8">
        <span className="section-label flex items-center gap-2 mb-3">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          AI Chat
        </span>
        <h1 className="page-title">AI <span className="text-copper">对话</span></h1>
      </div>
      <Card>
        <p className="text-sm text-gray-500">AI 对话页面 — 待实现</p>
      </Card>
    </div>
  )
}
