"""飞书 Webhook 接收端 - 处理飞书事件回调"""
import json
import logging
import hashlib
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from config import settings
from app.bot.message_handler import handle_message

logger = logging.getLogger(__name__)
router = APIRouter()

# 消息去重缓存（简单 set，单进程场景够用）
_processed_messages: set = set()
_MAX_CACHE_SIZE = 1000


def _deduplicate(message_id: str) -> bool:
    """返回 True 表示是重复消息，应该跳过"""
    if message_id in _processed_messages:
        return True
    _processed_messages.add(message_id)
    # 防止缓存无限增长
    if len(_processed_messages) > _MAX_CACHE_SIZE:
        _processed_messages.clear()
    return False


@router.post("/api/feishu/webhook")
async def feishu_webhook(request: Request):
    """
    飞书事件回调入口。
    关键: 必须在 3 秒内返回 HTTP 200，否则飞书认为超时并重发。
    耗时操作通过 BackgroundTasks 异步执行。
    """
    body = await request.json()

    # 1. URL 验证（飞书首次配置回调时会发送验证请求）
    if body.get("type") == "url_verification":
        challenge = body.get("challenge", "")
        return JSONResponse({"challenge": challenge})

    # 2. 验证 token
    token = body.get("header", {}).get("token", "")
    if settings.feishu_verification_token and token != settings.feishu_verification_token:
        logger.warning(f"Invalid verification token: {token}")
        return JSONResponse({"code": 403, "msg": "invalid token"}, status_code=403)

    # 3. 处理事件
    event = body.get("event", {})
    event_type = body.get("header", {}).get("event_type", "")

    if event_type == "im.message.receive_v1":
        message = event.get("message", {})
        message_id = message.get("message_id", "")

        # 消息去重
        if _deduplicate(message_id):
            logger.debug(f"Duplicate message skipped: {message_id}")
            return JSONResponse({"code": 0, "msg": "ok"})

        chat_id = message.get("chat_id", "")
        msg_type = message.get("message_type", "")
        sender_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")

        # 只处理文本消息
        if msg_type == "text":
            content = json.loads(message.get("content", "{}"))
            text = content.get("text", "").strip()

            if text:
                # 立即返回 200，然后在后台处理（避免飞书 3 秒超时）
                import asyncio
                asyncio.get_event_loop().create_task(
                    handle_message(chat_id, message_id, sender_id, text)
                )

    # 必须在 3 秒内返回
    return JSONResponse({"code": 0, "msg": "ok"})
