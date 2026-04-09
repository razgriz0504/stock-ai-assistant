"""飞书 API 客户端 - 消息发送（文本/图片/卡片）"""
import logging
import time
import httpx

from config import settings

logger = logging.getLogger(__name__)

FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

# tenant_access_token 缓存
_token_cache = {"token": "", "expire_time": 0}


async def _get_tenant_access_token() -> str:
    """获取飞书 tenant_access_token（带缓存）"""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expire_time"]:
        return _token_cache["token"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": settings.feishu_app_id,
                "app_secret": settings.feishu_app_secret,
            },
        )
        data = resp.json()
        if data.get("code") != 0:
            logger.error(f"Failed to get feishu token: {data}")
            raise RuntimeError(f"飞书 token 获取失败: {data.get('msg')}")

        _token_cache["token"] = data["tenant_access_token"]
        _token_cache["expire_time"] = now + data.get("expire", 7200) - 300  # 提前5分钟刷新
        return _token_cache["token"]


async def _get_headers() -> dict:
    token = await _get_tenant_access_token()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def send_text(chat_id: str, text: str):
    """发送文本消息"""
    headers = await _get_headers()
    body = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": f'{{"text": {__import__("json").dumps(text, ensure_ascii=False)}}}',
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{FEISHU_BASE_URL}/im/v1/messages?receive_id_type=chat_id",
            headers=headers,
            json=body,
        )
        result = resp.json()
        if result.get("code") != 0:
            logger.error(f"Send text failed: {result}")
        return result


async def send_image(chat_id: str, image_path: str):
    """发送图片消息（先上传到飞书，再发送）"""
    headers = await _get_headers()

    # 1. 上传图片
    upload_headers = {"Authorization": headers["Authorization"]}
    async with httpx.AsyncClient() as client:
        with open(image_path, "rb") as f:
            resp = await client.post(
                f"{FEISHU_BASE_URL}/im/v1/images",
                headers=upload_headers,
                data={"image_type": "message"},
                files={"image": ("chart.png", f, "image/png")},
            )
        upload_result = resp.json()
        if upload_result.get("code") != 0:
            logger.error(f"Upload image failed: {upload_result}")
            return upload_result

        image_key = upload_result["data"]["image_key"]

    # 2. 发送图片消息
    body = {
        "receive_id": chat_id,
        "msg_type": "image",
        "content": f'{{"image_key": "{image_key}"}}',
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{FEISHU_BASE_URL}/im/v1/messages?receive_id_type=chat_id",
            headers=headers,
            json=body,
        )
        result = resp.json()
        if result.get("code") != 0:
            logger.error(f"Send image failed: {result}")
        return result


async def reply_text(message_id: str, text: str):
    """回复消息"""
    headers = await _get_headers()
    body = {
        "msg_type": "text",
        "content": f'{{"text": {__import__("json").dumps(text, ensure_ascii=False)}}}',
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{FEISHU_BASE_URL}/im/v1/messages/{message_id}/reply",
            headers=headers,
            json=body,
        )
        result = resp.json()
        if result.get("code") != 0:
            logger.error(f"Reply failed: {result}")
        return result
