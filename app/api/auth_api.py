"""认证 API：登录 / 当前用户 / 修改密码。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.models import User, get_db
from app.auth.dependencies import get_current_user
from app.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Schemas ────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool

    @classmethod
    def from_user(cls, u: User) -> "UserInfo":
        return cls(
            id=u.id,
            username=u.username,
            display_name=u.display_name or "",
            role=u.role,
            is_active=u.is_active,
        )


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_days: int
    user: UserInfo


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


# ── Routes ─────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        # 统一提示：不区分"用户不存在"与"密码错误"，避免用户名枚举
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    return LoginResponse(
        access_token=token,
        expires_in_days=settings.jwt_expire_days,
        user=UserInfo.from_user(user),
    )


@router.get("/me", response_model=UserInfo)
def me(current: User = Depends(get_current_user)):
    return UserInfo.from_user(current)


@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(req.old_password, current.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect",
        )
    if req.old_password == req.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from old password",
        )
    current.password_hash = hash_password(req.new_password)
    db.commit()
    logger.info(f"User {current.username} changed password")
    return {"ok": True}
