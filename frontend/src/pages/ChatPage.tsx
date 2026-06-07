import { useState, useRef, useEffect } from 'react'
import { api } from '@/api/client'
import { Button } from '@/components/ui'

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'system', content: '你好！我是美股 AI 助手，可以帮你分析股票、回答市场问题。' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const chatAreaRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (chatAreaRef.current) {
      chatAreaRef.current.scrollTop = chatAreaRef.current.scrollHeight
    }
  }, [messages])

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)

    try {
      const res = await api.post('/api/chat', { message: text })
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.reply }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: '请求失败，请检查网络或后端服务。' }])
    } finally {
      setLoading(false)
    }
  }

  const quickCommands = [
    { label: '分析 NVDA', cmd: '/analyze NVDA' },
    { label: '分析 AAPL', cmd: '/analyze AAPL' },
    { label: '帮助', cmd: '/help' },
  ]

  return (
    <div className="flex flex-col h-[calc(100vh-64px)]">
      {/* Header */}
      <div className="mb-4">
        <span className="section-label flex items-center gap-2 mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-copper inline-block" />
          AI Chat
        </span>
        <h1 className="page-title">AI <span className="text-copper">对话</span></h1>
      </div>

      {/* Chat area */}
      <div
        ref={chatAreaRef}
        className="flex-1 overflow-y-auto space-y-4 mb-4 pr-2"
      >
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`
                max-w-[80%] px-4 py-3 rounded-xl text-sm whitespace-pre-wrap leading-relaxed
                ${msg.role === 'user'
                  ? 'bg-copper text-white rounded-br-sm'
                  : msg.role === 'system'
                    ? 'bg-cream-200 text-gray-600 text-center mx-auto text-xs py-2'
                    : 'bg-white border border-cream-300 text-gray-800 rounded-bl-sm'
                }
              `}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-cream-300 px-4 py-3 rounded-xl rounded-bl-sm text-sm text-gray-500 italic">
              正在思考...
            </div>
          </div>
        )}
      </div>

      {/* Quick commands */}
      <div className="flex gap-2 mb-3">
        {quickCommands.map(({ label, cmd }) => (
          <button
            key={cmd}
            onClick={() => { setInput(cmd); }}
            className="px-3 py-1.5 text-xs font-mono border border-cream-300 rounded-full text-copper hover:bg-cream-200 transition-colors"
          >
            {label}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="flex gap-3">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && sendMessage()}
          placeholder="输入消息... 支持 /analyze SYMBOL、/help 等命令"
          className="flex-1 px-4 py-3 text-sm bg-white border border-cream-300 rounded-lg focus:outline-none focus:border-copper transition-colors"
          disabled={loading}
        />
        <Button variant="primary" onClick={sendMessage} disabled={loading}>
          发送
        </Button>
      </div>
    </div>
  )
}
