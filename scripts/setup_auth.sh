#!/usr/bin/env bash
# ============================================================
# setup_auth.sh —— 一键在服务器上启用账号体系
# 用法：在服务器上进入 /opt/stock-ai-assistant，然后
#     sudo bash scripts/setup_auth.sh
#
# 该脚本会：
#   1. git pull 拉最新代码
#   2. 在 venv 里 pip install -r requirements.txt（新增 jose/passlib 依赖）
#   3. 前端 npm ci && npm run build（如果需要）
#   4. 幂等地把 JWT / INITIAL_ADMIN 变量追加到 .env
#   5. sudo systemctl restart stock-ai
#   6. 打印最近 60 行日志，看 "Initial admin" 相关信息
# ============================================================
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/stock-ai-assistant}"
SERVICE_NAME="${SERVICE_NAME:-stock-ai}"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/venv}"
ENV_FILE="$PROJECT_DIR/.env"

# ─── 可通过环境变量覆盖 ───
ADMIN_USERNAME="${INITIAL_ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${INITIAL_ADMIN_PASSWORD:-465987}"
JWT_ALGORITHM_VAL="${JWT_ALGORITHM:-HS256}"
JWT_EXPIRE_DAYS_VAL="${JWT_EXPIRE_DAYS:-7}"

SKIP_GIT="${SKIP_GIT:-0}"
SKIP_FRONTEND="${SKIP_FRONTEND:-0}"
SKIP_PIP="${SKIP_PIP:-0}"

log()  { echo -e "\033[1;36m[auth-setup]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
die()  { echo -e "\033[1;31m[error]\033[0m $*" >&2; exit 1; }

[[ -d "$PROJECT_DIR" ]] || die "项目目录不存在: $PROJECT_DIR"
cd "$PROJECT_DIR"

# ── 1. 拉最新代码 ─────────────────────────────────────
if [[ "$SKIP_GIT" != "1" ]]; then
    log "1/6 git pull origin main"
    git fetch --quiet origin
    git checkout main
    git pull --ff-only origin main
else
    warn "1/6 跳过 git pull (SKIP_GIT=1)"
fi

log "当前 commit: $(git log -1 --oneline)"

# ── 2. 装 Python 依赖 ─────────────────────────────────
if [[ "$SKIP_PIP" != "1" ]]; then
    log "2/6 pip install -r requirements.txt"
    [[ -d "$VENV_DIR" ]] || die "venv 不存在: $VENV_DIR（请先跑 scripts/setup_server.sh）"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    deactivate
else
    warn "2/6 跳过 pip install (SKIP_PIP=1)"
fi

# ── 3. 前端构建 ───────────────────────────────────────
if [[ "$SKIP_FRONTEND" != "1" ]]; then
    if [[ -d "$PROJECT_DIR/frontend" ]]; then
        log "3/6 前端构建 (npm ci && npm run build)"
        pushd "$PROJECT_DIR/frontend" >/dev/null
        if command -v npm >/dev/null 2>&1; then
            npm ci --silent || npm install --silent
            npm run build
        else
            warn "npm 未安装，跳过前端构建"
        fi
        popd >/dev/null
    else
        warn "3/6 没有 frontend/ 目录，跳过"
    fi
else
    warn "3/6 跳过前端构建 (SKIP_FRONTEND=1)"
fi

# ── 4. 幂等追加 .env 变量 ─────────────────────────────
log "4/6 更新 .env 账号相关变量"
touch "$ENV_FILE"

upsert_env() {
    # upsert_env KEY VALUE
    local key="$1" value="$2"
    if grep -qE "^${key}=" "$ENV_FILE"; then
        # 已存在但为空 → 写入；非空 → 保留
        local current
        current="$(grep -E "^${key}=" "$ENV_FILE" | head -n1 | cut -d= -f2-)"
        if [[ -z "$current" ]]; then
            sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
            log "    ✓ 已填充 ${key}"
        else
            log "    - 保留已有 ${key}"
        fi
    else
        printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
        log "    + 追加 ${key}"
    fi
}

# JWT_SECRET 用 openssl 现场生成
if ! grep -qE "^JWT_SECRET=..*$" "$ENV_FILE"; then
    JWT_SECRET_VAL="$(openssl rand -hex 32)"
    if grep -qE "^JWT_SECRET=" "$ENV_FILE"; then
        sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${JWT_SECRET_VAL}|" "$ENV_FILE"
    else
        printf '\n# ───── 账号体系 ─────\nJWT_SECRET=%s\n' "$JWT_SECRET_VAL" >> "$ENV_FILE"
    fi
    log "    + 生成新的 JWT_SECRET"
else
    log "    - 保留已有 JWT_SECRET"
fi

upsert_env JWT_ALGORITHM         "$JWT_ALGORITHM_VAL"
upsert_env JWT_EXPIRE_DAYS       "$JWT_EXPIRE_DAYS_VAL"
upsert_env INITIAL_ADMIN_USERNAME "$ADMIN_USERNAME"
upsert_env INITIAL_ADMIN_PASSWORD "$ADMIN_PASSWORD"

chmod 600 "$ENV_FILE" || true

# ── 5. 重启后端 ───────────────────────────────────────
log "5/6 systemctl restart ${SERVICE_NAME}"
systemctl restart "$SERVICE_NAME"
sleep 2
systemctl --no-pager status "$SERVICE_NAME" | head -n 12 || true

# ── 6. 查看播种日志 ───────────────────────────────────
log "6/6 最近日志（找 'Initial admin' / 'seeded' 关键字）"
journalctl -u "$SERVICE_NAME" -n 60 --no-pager | \
    grep -Ei "admin|seed|auth|error" || \
    journalctl -u "$SERVICE_NAME" -n 30 --no-pager

echo ""
echo "============================================================"
echo "✅ 完成。若日志出现 'Initial admin created: ${ADMIN_USERNAME}'，"
echo "   浏览器打开登录页，使用："
echo "     用户名: ${ADMIN_USERNAME}"
echo "     密码:   ${ADMIN_PASSWORD}"
echo "   登录后请立刻到「个人中心」修改密码。"
echo ""
echo "如日志未出现该信息，说明 users 表已有数据（说明之前跑过）。"
echo "要重置首个 admin，可执行："
echo "   sqlite3 ${PROJECT_DIR}/db/stock_ai.db \"DELETE FROM users;\""
echo "   sudo systemctl restart ${SERVICE_NAME}"
echo "============================================================"
