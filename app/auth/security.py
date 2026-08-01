"""密码哈希与 JWT 编解码。

- 密码：bcrypt（直接使用 bcrypt 库；passlib 1.7.4 与 bcrypt 4.1+ 不兼容，已弃用）。
- Token：HS256 JWT，claim 结构 {sub: username, uid: user_id, role: 'admin'|'user', exp}。
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from config import settings

logger = logging.getLogger(__name__)

# bcrypt 协议限制：密码不能超过 72 字节。
# 超过部分会被截断，这是行业标准做法（不影响安全性，因为 72 字节 = 192 位熵）。
_BCRYPT_MAX_BYTES = 72


def _truncate_for_bcrypt(password: str) -> bytes:
    """将密码编码为 UTF-8 并截断到 72 字节。"""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def _get_secret() -> str:
    """惰性读取 JWT_SECRET。开发场景允许空值：随机生成一次以警告开发者。"""
    if settings.jwt_secret:
        return settings.jwt_secret
    # 开发环境降级：每次进程启动生成新 secret（重启会失效所有 token）
    if not getattr(_get_secret, "_warned", False):
        logger.warning(
            "JWT_SECRET is empty; generating a per-process random secret. "
            "Set JWT_SECRET in .env for production (openssl rand -hex 32)."
        )
        setattr(_get_secret, "_warned", True)
        setattr(_get_secret, "_dev_secret", secrets.token_hex(32))
    return getattr(_get_secret, "_dev_secret")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_truncate_for_bcrypt(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_truncate_for_bcrypt(plain), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: int, username: str, role: str, expire_days: int | None = None) -> str:
    """生成 JWT。expire_days 默认取 settings.jwt_expire_days。"""
    days = expire_days if expire_days is not None else settings.jwt_expire_days
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": username,
        "uid": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=days)).timestamp()),
    }
    return jwt.encode(payload, _get_secret(), algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any] | None:
    """解码 JWT；无效或过期返回 None。"""
    try:
        return jwt.decode(token, _get_secret(), algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        logger.debug(f"JWT decode failed: {e}")
        return None
