"""FastAPI 认证依赖。

- get_current_user：强制登录；未提供 token / token 无效 → 401。
- require_admin：在 get_current_user 之上要求 role='admin'；否则 403。
- optional_current_user：可选登录（未登录返回 None），供混合公开/登录接口使用。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from db.models import User, get_db
from app.auth.security import decode_token

logger = logging.getLogger(__name__)

# tokenUrl 指向登录端点，供 Swagger UI 展示；实际前端用自己的登录页
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _load_user(db: Session, token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    uid = payload.get("uid")
    if not isinstance(uid, int):
        return None
    user = db.query(User).filter(User.id == uid).first()
    if not user or not user.is_active:
        return None
    return user


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    user = _load_user(db, token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privilege required",
        )
    return user


def optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    return _load_user(db, token)
