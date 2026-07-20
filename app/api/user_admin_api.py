"""用户管理 API（admin only）：列表 / 创建 / 修改 / 删除。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.models import User, get_db
from app.auth.dependencies import require_admin
from app.auth.security import hash_password
from app.api.auth_api import UserInfo

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin)],
)


# ── Schemas ────────────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(default="", max_length=128)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=128)
    role: Optional[str] = Field(default=None, pattern="^(admin|user)$")
    is_active: Optional[bool] = None
    new_password: Optional[str] = Field(default=None, min_length=6, max_length=128)


class UserDetail(UserInfo):
    created_at: Optional[str] = None
    last_login_at: Optional[str] = None

    @classmethod
    def from_user(cls, u: User) -> "UserDetail":
        return cls(
            id=u.id,
            username=u.username,
            display_name=u.display_name or "",
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else None,
            last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
        )


# ── Helpers ────────────────────────────────────────────────────

def _first_admin_id(db: Session) -> Optional[int]:
    """返回按 id 升序的第一个 admin id（用于保护）。"""
    row = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()
    return row.id if row else None


# ── Routes ─────────────────────────────────────────────────────

@router.get("", response_model=list[UserDetail])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [UserDetail.from_user(u) for u in users]


@router.post("", response_model=UserDetail, status_code=status.HTTP_201_CREATED)
def create_user(req: UserCreateRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )
    u = User(
        username=req.username,
        password_hash=hash_password(req.password),
        display_name=req.display_name,
        role=req.role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    logger.info(f"Admin created user: {u.username} (role={u.role})")
    return UserDetail.from_user(u)


@router.patch("/{user_id}", response_model=UserDetail)
def update_user(
    user_id: int,
    req: UserUpdateRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    first_admin_id = _first_admin_id(db)
    # 保护首个 admin：不允许被降级或禁用
    if u.id == first_admin_id:
        if req.role is not None and req.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the first admin",
            )
        if req.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot disable the first admin",
            )
    # 不允许自我降级/禁用（防止误锁死）
    if u.id == current.id:
        if req.role is not None and req.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote yourself",
            )
        if req.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot disable yourself",
            )

    if req.display_name is not None:
        u.display_name = req.display_name
    if req.role is not None:
        u.role = req.role
    if req.is_active is not None:
        u.is_active = req.is_active
    if req.new_password:
        u.password_hash = hash_password(req.new_password)
    db.commit()
    db.refresh(u)
    logger.info(f"Admin updated user {u.username}: {req.dict(exclude_unset=True, exclude={'new_password'})}")
    return UserDetail.from_user(u)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if u.id == _first_admin_id(db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the first admin",
        )
    if u.id == current.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )
    db.delete(u)
    db.commit()
    logger.info(f"Admin deleted user: {u.username}")
    return None
