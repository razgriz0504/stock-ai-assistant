"""AI 聊天 REST API（前端 SPA: ChatPage.tsx）

对话历史按用户隔离持久化到 `chat_conversations` + `chat_messages` 两张表；
POST /api/chat 若不带 conversation_id 会自动新建一条对话；带则追加消息。
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.bot.commands import parse_command
from app.analysis.ai_advisor import analyze_with_ai
from app.analysis.chart_generator import generate_chart
from app.llm.client import chat, get_model, set_model, SUPPORTED_MODELS
from app.backtest.engine import run_backtest
from db.models import ChatConversation, ChatMessage, SessionLocal, User

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Pydantic ───────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None


class ChatResponse(BaseModel):
    reply: str
    model: str
    conversation_id: int


class ConversationSummary(BaseModel):
    id: int
    title: str
    model: str
    created_at: Optional[str]
    updated_at: Optional[str]


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    model: str
    created_at: Optional[str]


class ConversationDetail(BaseModel):
    id: int
    title: str
    model: str
    created_at: Optional[str]
    updated_at: Optional[str]
    messages: list[MessageOut]


# ── 工具 ───────────────────────────────────────────────────────────


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _title_from_first_message(text: str, max_len: int = 40) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:max_len] if text else "新对话"


def _ensure_conversation(
    db: Session, user_id: int, conversation_id: Optional[int], first_message: str, model_name: str
) -> ChatConversation:
    """获取或新建当前用户的对话，跨用户访问返回 404。"""
    if conversation_id is not None:
        conv = (
            db.query(ChatConversation)
            .filter(ChatConversation.id == conversation_id)
            .filter(ChatConversation.user_id == user_id)
            .first()
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv

    conv = ChatConversation(
        user_id=user_id,
        title=_title_from_first_message(first_message),
        model=model_name,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _append_message(db: Session, conversation_id: int, role: str, content: str, model_name: str) -> None:
    msg = ChatMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        model=model_name,
    )
    db.add(msg)
    # 更新对话 updated_at
    conv = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
    if conv:
        conv.updated_at = datetime.now(timezone.utc)
    db.commit()


async def _run_command(cmd, text: str) -> str:
    """封装原有命令分发逻辑，返回文本回复。"""
    if cmd.command == "help":
        from app.bot.commands import HELP_TEXT
        return HELP_TEXT
    if cmd.command == "analyze":
        report, ai_advice = await analyze_with_ai(cmd.symbol)
        return f"{report}\n\nAI 分析 ({get_model()}):\n{ai_advice}"
    if cmd.command == "backtest":
        return run_backtest(cmd.symbol, cmd.args)
    if cmd.command == "switch_model":
        actual = set_model(cmd.args)
        info = "\n".join(f"  {k} -> {v}" for k, v in SUPPORTED_MODELS.items())
        return f"模型已切换: {actual}\n\n支持的模型:\n{info}"
    if cmd.command == "chart":
        return "图表功能请在飞书中使用（网页版暂不支持发送图片）"
    if cmd.command in ("monitor", "cancel_monitor", "watchlist"):
        return "监控功能请在飞书中使用（需要推送通知）"

    sys = "你是专业美股交易分析助手，用中文回答。"
    if cmd.symbol:
        sys += f" 用户可能在问关于 {cmd.symbol} 的问题。"
    return await chat(cmd.args or text, system_prompt=sys)


# ── 主对话接口 ──────────────────────────────────────────────────────


@router.post("/api/chat", response_model=ChatResponse)
async def api_chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    text = (req.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="message 不能为空")

    model_name = get_model()
    cmd = parse_command(text)

    db = SessionLocal()
    try:
        conv = _ensure_conversation(db, current_user.id, req.conversation_id, text, model_name)
        _append_message(db, conv.id, "user", text, model_name)
        try:
            reply = await _run_command(cmd, text)
        except Exception as e:
            logger.error(f"Chat API error: {e}", exc_info=True)
            reply = f"处理出错: {e}"
        _append_message(db, conv.id, "assistant", reply, model_name)
        return ChatResponse(reply=reply, model=model_name, conversation_id=conv.id)
    finally:
        db.close()


# ── 会话管理 ────────────────────────────────────────────────────────


@router.get("/api/chat/conversations", response_model=list[ConversationSummary])
async def list_conversations(current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        rows = (
            db.query(ChatConversation)
            .filter(ChatConversation.user_id == current_user.id)
            .order_by(ChatConversation.updated_at.desc().nullslast(), ChatConversation.id.desc())
            .limit(200)
            .all()
        )
        return [
            ConversationSummary(
                id=r.id,
                title=r.title or "新对话",
                model=r.model or "",
                created_at=_iso(r.created_at),
                updated_at=_iso(r.updated_at),
            )
            for r in rows
        ]
    finally:
        db.close()


@router.get("/api/chat/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        conv = (
            db.query(ChatConversation)
            .filter(ChatConversation.id == conversation_id)
            .filter(ChatConversation.user_id == current_user.id)
            .first()
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conv.id)
            .order_by(ChatMessage.id.asc())
            .all()
        )
        return ConversationDetail(
            id=conv.id,
            title=conv.title or "新对话",
            model=conv.model or "",
            created_at=_iso(conv.created_at),
            updated_at=_iso(conv.updated_at),
            messages=[
                MessageOut(
                    id=m.id,
                    role=m.role,
                    content=m.content or "",
                    model=m.model or "",
                    created_at=_iso(m.created_at),
                )
                for m in msgs
            ],
        )
    finally:
        db.close()


@router.delete("/api/chat/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        conv = (
            db.query(ChatConversation)
            .filter(ChatConversation.id == conversation_id)
            .filter(ChatConversation.user_id == current_user.id)
            .first()
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        db.query(ChatMessage).filter(ChatMessage.conversation_id == conv.id).delete()
        db.delete(conv)
        db.commit()
        return {"success": True}
    finally:
        db.close()
