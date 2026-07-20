#!/usr/bin/env bash
# ============================================================
# 富途 OpenD 一键部署脚本（Ubuntu / Debian，仅需 root 权限）
# ------------------------------------------------------------
# 用途：把 OpenD Linux 版下载到 /opt/futu-opend，配置 systemd，
#       绑定 127.0.0.1:11111（不暴露公网），开机自启。
# 前置：apt 包管理、curl、tar、systemd
# 用法：sudo bash scripts/setup_futu_opend.sh [OPEND_URL]
#       未传参时使用默认 URL（可能过期，请从官网 https://openapi.futunn.com 拿最新链接）
# 首次登录：安装完 systemctl start futu-opend 后，
#          journalctl -u futu-opend -f 查看登录二维码/短信提示，
#          用手机 Futu App 扫码或输入验证码即可。
# ============================================================

set -euo pipefail

INSTALL_DIR="/opt/futu-opend"
SERVICE_FILE="/etc/systemd/system/futu-opend.service"
BIND_IP="127.0.0.1"
BIND_PORT="11111"
# 默认下载地址（如失效请到 https://openapi.futunn.com 首页拿最新链接后作为第一个参数传入）
DEFAULT_URL="https://softwarefile.futunn.com/software/opend/OpenD_Linux_9.3.5308_x86_64.tar.gz"
OPEND_URL="${1:-$DEFAULT_URL}"

echo "[futu-opend] 安装目录：$INSTALL_DIR"
echo "[futu-opend] 下载地址：$OPEND_URL"

if [ "$(id -u)" != "0" ]; then
  echo "[futu-opend] 需 root 权限执行（sudo bash $0）" >&2
  exit 1
fi

command -v curl >/dev/null || { echo "[futu-opend] 请先安装 curl" >&2; exit 1; }
command -v tar  >/dev/null || { echo "[futu-opend] 请先安装 tar"  >&2; exit 1; }

# 1) 下载 & 解压（支持 file:///path 本地文件路径，绕过云 IP 无法访问 Futu CDN 的情况）
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
if [[ "$OPEND_URL" == file://* ]]; then
  LOCAL_PATH="${OPEND_URL#file://}"
  echo "[futu-opend] 使用本地文件：$LOCAL_PATH"
  [ -f "$LOCAL_PATH" ] || { echo "[futu-opend] 本地文件不存在：$LOCAL_PATH" >&2; exit 1; }
  cp "$LOCAL_PATH" "$TMP_DIR/opend.tar.gz"
elif [[ "$OPEND_URL" == /* ]]; then
  echo "[futu-opend] 使用本地文件：$OPEND_URL"
  [ -f "$OPEND_URL" ] || { echo "[futu-opend] 本地文件不存在：$OPEND_URL" >&2; exit 1; }
  cp "$OPEND_URL" "$TMP_DIR/opend.tar.gz"
else
  echo "[futu-opend] 下载中..."
  curl -fSL --connect-timeout 30 "$OPEND_URL" -o "$TMP_DIR/opend.tar.gz"
fi
mkdir -p "$INSTALL_DIR"
tar -xzf "$TMP_DIR/opend.tar.gz" -C "$INSTALL_DIR" --strip-components=1
# 兼容不同压缩包结构：如果解压出的还是子目录，把内容再摊平一次
if [ ! -x "$INSTALL_DIR/FutuOpenD" ] && [ -d "$INSTALL_DIR"/*OpenD* ]; then
  INNER_DIR=$(find "$INSTALL_DIR" -maxdepth 1 -type d -name '*OpenD*' | head -n1)
  if [ -n "$INNER_DIR" ]; then
    mv "$INNER_DIR"/* "$INSTALL_DIR"/
    rm -rf "$INNER_DIR"
  fi
fi

if [ ! -x "$INSTALL_DIR/FutuOpenD" ]; then
  echo "[futu-opend] 解压后未找到 FutuOpenD 可执行文件，请手动检查 $INSTALL_DIR" >&2
  exit 1
fi

# 2) 写 systemd unit
echo "[futu-opend] 写入 $SERVICE_FILE"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Futu OpenD (read-only local gateway, bound to $BIND_IP:$BIND_PORT)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/FutuOpenD -ip=$BIND_IP -port=$BIND_PORT
Restart=on-failure
RestartSec=10
# 只绑 loopback，不需要开放端口。日志走 journalctl 便于扫码/短信登录。
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 3) 启用并启动
systemctl daemon-reload
systemctl enable futu-opend
systemctl restart futu-opend

sleep 2
echo "[futu-opend] 当前状态："
systemctl --no-pager status futu-opend | head -n 15 || true

cat <<'HINT'

============================================================
下一步（首次登录）：
  1) journalctl -u futu-opend -f
     观察输出中的登录二维码 URL 或短信验证码提示
  2) 用手机 Futu App 扫码或输入验证码完成登录
  3) 登录成功后即可从 127.0.0.1:11111 调用 API
  4) 在项目 .env 里设置 FUTU_ENABLED=true
     然后 systemctl restart stock-ai-assistant

Session 过期后重新执行第 1-2 步即可。
============================================================
HINT
