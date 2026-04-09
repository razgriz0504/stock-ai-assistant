import logging
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from app.bot.commands import parse_command
from app.analysis.ai_advisor import analyze_with_ai
from app.analysis.chart_generator import generate_chart
from app.llm.client import chat, get_model, set_model, SUPPORTED_MODELS
from app.backtest.engine import run_backtest

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    model: str


@router.post("/api/chat")
async def api_chat(req: ChatRequest):
    text = req.message.strip()
    cmd = parse_command(text)
    try:
        if cmd.command == "help":
            from app.bot.commands import HELP_TEXT
            return ChatResponse(reply=HELP_TEXT, model=get_model())
        elif cmd.command == "analyze":
            report, ai_advice = await analyze_with_ai(cmd.symbol)
            result = f"{report}\n\nAI 分析 ({get_model()}):\n{ai_advice}"
            return ChatResponse(reply=result, model=get_model())
        elif cmd.command == "backtest":
            result = run_backtest(cmd.symbol, cmd.args)
            return ChatResponse(reply=result, model=get_model())
        elif cmd.command == "switch_model":
            actual = set_model(cmd.args)
            info = "\n".join(f"  {k} -> {v}" for k, v in SUPPORTED_MODELS.items())
            return ChatResponse(reply=f"模型已切换: {actual}\n\n支持的模型:\n{info}", model=actual)
        elif cmd.command == "chart":
            return ChatResponse(reply="图表功能请在飞书中使用（网页版暂不支持发送图片）", model=get_model())
        elif cmd.command == "monitor" or cmd.command == "cancel_monitor" or cmd.command == "watchlist":
            return ChatResponse(reply="监控功能请在飞书中使用（需要推送通知）", model=get_model())
        else:
            sys = "你是专业美股交易分析助手，用中文回答。"
            if cmd.symbol:
                sys += f" 用户可能在问关于 {cmd.symbol} 的问题。"
            response = await chat(cmd.args or text, system_prompt=sys)
            return ChatResponse(reply=response, model=get_model())
    except Exception as e:
        logger.error(f"Chat API error: {e}", exc_info=True)
        return ChatResponse(reply=f"处理出错: {e}", model=get_model())


CHAT_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stock AI Assistant</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1923; color: #e0e0e0; height: 100vh; display: flex; flex-direction: column; }
.header { background: #1a2634; padding: 16px 24px; border-bottom: 1px solid #2a3a4a; display: flex; align-items: center; gap: 12px; }
.header h1 { font-size: 18px; color: #4fc3f7; }
.header .status { font-size: 12px; color: #66bb6a; background: #1b3a1b; padding: 4px 10px; border-radius: 12px; }
.chat-area { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.msg { max-width: 85%; padding: 12px 16px; border-radius: 12px; line-height: 1.6; white-space: pre-wrap; font-size: 14px; word-break: break-word; }
.msg.user { align-self: flex-end; background: #1565c0; color: white; border-bottom-right-radius: 4px; }
.msg.bot { align-self: flex-start; background: #1e2d3d; color: #e0e0e0; border-bottom-left-radius: 4px; border: 1px solid #2a3a4a; }
.msg.bot.error { border-color: #c62828; background: #2d1a1a; }
.msg.system { align-self: center; background: transparent; color: #78909c; font-size: 12px; padding: 4px; }
.input-area { padding: 16px 20px; background: #1a2634; border-top: 1px solid #2a3a4a; display: flex; gap: 12px; }
.input-area input { flex: 1; padding: 12px 16px; border-radius: 8px; border: 1px solid #2a3a4a; background: #0f1923; color: #e0e0e0; font-size: 14px; outline: none; }
.input-area input:focus { border-color: #4fc3f7; }
.input-area button { padding: 12px 24px; background: #1565c0; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
.input-area button:hover { background: #1976d2; }
.input-area button:disabled { background: #37474f; cursor: not-allowed; }
.typing { color: #78909c; font-style: italic; }
.quick-cmds { padding: 8px 20px; background: #1a2634; display: flex; gap: 8px; flex-wrap: wrap; }
.quick-cmds button { padding: 6px 12px; background: #263238; color: #4fc3f7; border: 1px solid #2a3a4a; border-radius: 16px; cursor: pointer; font-size: 12px; }
.quick-cmds button:hover { background: #2a3a4a; }
</style>
</head>
<body>
<div class="header">
  <h1>Stock AI Trading Assistant</h1>
  <span class="status" id="status">Running</span>
</div>
<div class="quick-cmds">
  <button onclick="sendQuick('/帮助')">帮助</button>
  <button onclick="sendQuick('/分析 NVDA')">分析 NVDA</button>
  <button onclick="sendQuick('/分析 AAPL')">分析 AAPL</button>
  <button onclick="sendQuick('/分析 TSLA')">分析 TSLA</button>
  <button onclick="sendQuick('/回测 均线交叉 NVDA')">回测 NVDA</button>
  <button onclick="sendQuick('美股大盘今天怎么样？')">问大盘</button>
</div>
<div class="chat-area" id="chat">
  <div class="msg system">输入命令或直接提问，例如: /分析 AAPL 或 "TSLA还能买吗？"</div>
</div>
<div class="input-area">
  <input type="text" id="input" placeholder="输入命令或问题..." autocomplete="off">
  <button id="sendBtn" onclick="send()">发送</button>
</div>
<script>
const chat = document.getElementById('chat');
const input = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
input.addEventListener('keydown', e => { if (e.key === 'Enter' && !sendBtn.disabled) send(); });

function addMsg(text, cls) {
  const d = document.createElement('div');
  d.className = 'msg ' + cls;
  d.textContent = text;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
  return d;
}

function sendQuick(text) { input.value = text; send(); }

async function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addMsg(text, 'user');
  sendBtn.disabled = true;
  const typing = addMsg('正在思考...', 'bot typing');
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text})
    });
    const data = await res.json();
    typing.remove();
    if (data.reply) {
      addMsg(data.reply, 'bot');
    } else if (data.detail) {
      addMsg('错误: ' + JSON.stringify(data.detail), 'bot error');
    }
  } catch(e) {
    typing.remove();
    addMsg('网络错误: ' + e.message, 'bot error');
  }
  sendBtn.disabled = false;
  input.focus();
}
</script>
</body>
</html>"""


@router.get("/chat", response_class=HTMLResponse)
async def chat_page():
    return CHAT_HTML
