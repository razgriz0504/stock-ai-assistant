"""首个 admin 用户播种：users 表为空且 .env 提供 INITIAL_ADMIN_PASSWORD 时生效。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from db.models import SessionLocal, User
from app.auth.security import hash_password
from config import settings

logger = logging.getLogger(__name__)


def ensure_initial_admin() -> None:
    """若 users 表为空，用 INITIAL_ADMIN_USERNAME / INITIAL_ADMIN_PASSWORD 创建首个 admin。

    - 表非空 → 跳过（后续 admin 通过管理页创建）。
    - INITIAL_ADMIN_PASSWORD 为空 → 跳过并警告。
    """
    db = SessionLocal()
    try:
        count = db.query(User).count()
        if count > 0:
            return
        username = (settings.initial_admin_username or "admin").strip()
        password = (settings.initial_admin_password or "").strip()
        if not password:
            logger.warning(
                "users table is empty but INITIAL_ADMIN_PASSWORD is not set; "
                "no admin will be seeded. Set INITIAL_ADMIN_PASSWORD in .env and restart."
            )
            return
        admin = User(
            username=username,
            password_hash=hash_password(password),
            display_name="Administrator",
            role="admin",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(admin)
        db.commit()
        logger.info(f"Seeded initial admin user: {username}")
    except Exception as e:
        logger.error(f"ensure_initial_admin failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
