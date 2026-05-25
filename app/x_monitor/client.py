"""X API v2 HTTP 客户端

使用同步 requests 直接调用 X API v2 端点，便于通过 asyncio.to_thread() 异步包装。
端点参考：https://developer.x.com/en/docs/x-api/tweets/lookups
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.twitter.com/2"
DEFAULT_TIMEOUT = 30
USER_AGENT = "stock-ai-assistant/1.0 x-monitor"


class XAPIError(Exception):
    """X API 调用异常"""

    def __init__(self, message: str, status: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


def _headers(bearer: str) -> dict:
    return {
        "Authorization": f"Bearer {bearer}",
        "User-Agent": USER_AGENT,
    }


def _request(method: str, url: str, bearer: str, *, params: Optional[dict] = None, retries: int = 1) -> dict:
    """统一的 HTTP 请求封装，处理 429 限流"""
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = requests.request(
                method, url, headers=_headers(bearer), params=params, timeout=DEFAULT_TIMEOUT
            )
            if resp.status_code == 429 and attempt < retries:
                retry_after = int(resp.headers.get("Retry-After", "30"))
                logger.warning("X API 429 rate-limited, sleeping %ds", retry_after)
                time.sleep(min(retry_after, 60))
                continue
            if resp.status_code == 401:
                raise XAPIError("X API 401 Unauthorized — Bearer Token 无效", status=401, payload=resp.text)
            if resp.status_code == 404:
                raise XAPIError("X API 404 Not Found", status=404, payload=resp.text)
            if not resp.ok:
                raise XAPIError(
                    f"X API {resp.status_code} 错误: {resp.text[:300]}",
                    status=resp.status_code,
                    payload=resp.text,
                )
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(2)
                continue
            raise XAPIError(f"X API 请求失败: {exc}") from exc
    if last_exc:
        raise XAPIError(f"X API 请求失败: {last_exc}") from last_exc
    raise XAPIError("X API 请求失败：未知错误")


# ─────────────────────────────────────────────────────────────────
# 公开 API
# ─────────────────────────────────────────────────────────────────

def get_user_id_by_username(username: str, bearer: str) -> dict:
    """根据 username（不带 @）查询 X 用户 ID

    返回: {"id": "1234", "username": "...", "name": "...", "description": "..."}
    """
    username = username.strip().lstrip("@")
    url = f"{BASE_URL}/users/by/username/{username}"
    data = _request(
        "GET",
        url,
        bearer,
        params={"user.fields": "name,description,verified"},
    )
    user = data.get("data") or {}
    if not user.get("id"):
        raise XAPIError(f"用户 @{username} 未找到", status=404, payload=data)
    return {
        "id": user["id"],
        "username": user.get("username", username),
        "name": user.get("name", ""),
        "description": user.get("description", ""),
    }


def fetch_user_tweets(
    user_id: str,
    bearer: str,
    since_id: str = "",
    max_results: int = 20,
) -> list[dict]:
    """拉取指定用户的最近推文（已排除 retweet/reply）

    返回的每条推文 dict 字段：
      - tweet_id (str)
      - text (str)
      - created_at (datetime, UTC)
      - metrics (dict) - public_metrics 原样
    """
    url = f"{BASE_URL}/users/{user_id}/tweets"
    params: dict[str, Any] = {
        "max_results": max(5, min(max_results, 100)),
        "tweet.fields": "created_at,public_metrics,lang",
        "exclude": "retweets,replies",
    }
    if since_id:
        params["since_id"] = since_id
    data = _request("GET", url, bearer, params=params)
    tweets = data.get("data") or []
    out: list[dict] = []
    for t in tweets:
        try:
            created = datetime.strptime(t["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ")
        except (KeyError, ValueError):
            try:
                created = datetime.strptime(t["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            except (KeyError, ValueError):
                created = datetime.utcnow()
        out.append({
            "tweet_id": t["id"],
            "text": t.get("text", ""),
            "created_at": created,
            "metrics": t.get("public_metrics", {}),
            "lang": t.get("lang", ""),
        })
    return out


def validate_bearer(bearer: str) -> tuple[bool, str]:
    """快速验证 Bearer Token 是否有效

    返回 (is_valid, message)
    """
    if not bearer or not bearer.strip():
        return False, "Bearer Token 为空"
    try:
        # 用一个稳定的公开账号验证
        get_user_id_by_username("X", bearer)
        return True, "Bearer Token 有效"
    except XAPIError as exc:
        return False, str(exc)
    except Exception as exc:  # pragma: no cover
        return False, f"未知错误: {exc}"
