"""AI 聊天 REST API（前端 SPA: ChatPage.tsx）"""
import logging
from fastapi import APIRouter
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
