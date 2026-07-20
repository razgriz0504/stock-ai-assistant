"""账户体系：JWT 认证 + 依赖 + 首个 admin 播种。"""
from app.auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)
from app.auth.dependencies import (
    get_current_user,
    require_admin,
    optional_current_user,
    oauth2_scheme,
)
from app.auth.seed import ensure_initial_admin

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_token",
    "get_current_user",
    "require_admin",
    "optional_current_user",
    "oauth2_scheme",
    "ensure_initial_admin",
]
