#!/bin/bash
# ============================================
# 美股 AI 交易助手 - 服务器初始化脚本
# 适用于: 阿里云轻量级应用服务器 Ubuntu 22.04/24.04
# ============================================
set -e

echo "=============================="
echo "开始初始化服务器环境..."
echo "=============================="

# 1. 系统更新
echo "[1/7] 更新系统包..."
apt update && apt upgrade -y

# 2. 安装基础依赖
echo "[2/7] 安装基础依赖..."
apt install -y python3.11 python3.11-venv python3-pip nginx certbot python3-certbot-nginx git

# 3. 配置 2GB Swap (防止 OOM)
echo "[3/7] 配置 2GB Swap 交换分区..."
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "Swap 配置完成"
else
    echo "Swap 已存在，跳过"
fi
# 调整 swappiness，让系统不到万不得已不用 swap
sysctl vm.swappiness=10
echo 'vm.swappiness=10' >> /etc/sysctl.conf

# 4. 创建项目目录和虚拟环境
echo "[4/7] 创建项目目录..."
mkdir -p /opt/stock-ai-assistant
cd /opt/stock-ai-assistant
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# 5. 配置 Nginx (需要替换 YOUR_DOMAIN)
echo "[5/7] 配置 Nginx..."
cat > /etc/nginx/sites-available/stock-ai <<'NGINX_CONF'
server {
    listen 80;
    server_name YOUR_DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 飞书 webhook 可能发送较大的消息体
        client_max_body_size 10M;

        # 超时设置（回测等耗时操作）
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
    }
}
NGINX_CONF

ln -sf /etc/nginx/sites-available/stock-ai /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo ""
echo "========================================"
echo "请手动执行以下步骤:"
echo "1. 编辑 /etc/nginx/sites-available/stock-ai"
echo "   将 YOUR_DOMAIN 替换为你的实际域名"
echo "2. 运行: sudo certbot --nginx -d 你的域名"
echo "   申请 SSL 证书（飞书要求 HTTPS）"
echo "========================================"

# 6. 创建 systemd 服务文件
echo "[6/7] 创建 systemd 服务..."
cat > /etc/systemd/system/stock-ai.service <<'SYSTEMD_CONF'
[Unit]
Description=Stock AI Trading Assistant
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/stock-ai-assistant
Environment=PATH=/opt/stock-ai-assistant/venv/bin:/usr/bin
ExecStart=/opt/stock-ai-assistant/venv/bin/gunicorn main:app \
    -k uvicorn.workers.UvicornWorker \
    --workers 1 \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --graceful-timeout 30 \
    --access-logfile /opt/stock-ai-assistant/access.log \
    --error-logfile /opt/stock-ai-assistant/error.log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SYSTEMD_CONF

systemctl daemon-reload
systemctl enable stock-ai

# 7. 防火墙配置
echo "[7/7] 配置防火墙..."
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp
echo "y" | ufw enable 2>/dev/null || true

echo ""
echo "=============================="
echo "服务器初始化完成!"
echo ""
echo "下一步:"
echo "1. 上传代码到 /opt/stock-ai-assistant/"
echo "2. cd /opt/stock-ai-assistant && source venv/bin/activate"
echo "3. pip install -r requirements.txt"
echo "4. cp .env.example .env && nano .env  (填入 API Keys)"
echo "5. 替换 Nginx 配置中的域名 + 申请 SSL 证书"
echo "6. sudo systemctl start stock-ai"
echo "=============================="
