#!/bin/bash
set -e

# =============================================================================
# Prism v2 一键部署脚本（阿里云 / 国内服务器）
# 用法: bash deploy.sh
# 前提: 已安装 Docker + Docker Compose
# =============================================================================

echo "=== Prism v2 部署 ==="

# ---- 1. 检查 Docker ----
if ! command -v docker &> /dev/null; then
    echo "Docker 未安装。安装中..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker && systemctl start docker
    echo "Docker 安装完成"
fi

if ! docker compose version &> /dev/null; then
    echo "Docker Compose 未安装。请安装 docker-compose-plugin"
    exit 1
fi

# ---- 2. 拉代码 ----
INSTALL_DIR="/opt/prism"
if [ -d "$INSTALL_DIR" ]; then
    echo "目录 $INSTALL_DIR 已存在，更新代码..."
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || true
else
    echo "克隆代码..."
    git clone https://github.com/Jaydenlk/Prism.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ---- 3. 配置 .env ----
if [ ! -f .env ]; then
    echo ""
    echo "=== 需要配置 .env ==="
    echo "请将本地的 .env 文件内容粘贴到 $INSTALL_DIR/.env"
    echo "或者从本地 scp: scp .env root@服务器:$INSTALL_DIR/.env"
    echo ""
    echo "最少需要以下变量："
    echo "  POSTGRES_PASSWORD=<随机密码>"
    echo "  JWT_SECRET=<32字符以上>"
    echo "  ENCRYPTION_KEY=<64位hex>"
    echo "  CALLBACK_SECRET=<64位hex>"
    echo "  ANTHROPIC_API_KEY=<你的key>"
    echo "  ANTHROPIC_BASE_URL=<中转站地址>"
    echo ""
    read -p "已配置好 .env? (y/n): " confirm
    if [ "$confirm" != "y" ]; then
        echo "请先配置 .env，然后重新运行 deploy.sh"
        exit 1
    fi
fi

# ---- 4. 构建前端 ----
if [ -d "frontend-react" ] && command -v node &> /dev/null; then
    echo "构建前端..."
    cd frontend-react
    npm ci --registry=https://registry.npmmirror.com 2>/dev/null || npm install --registry=https://registry.npmmirror.com
    npm run build
    cd ..
    echo "前端构建完成"
elif [ ! -d "frontend-react/dist" ]; then
    echo "警告: 前端未构建且无 Node.js，nginx 可能无法正常服务前端"
fi

# ---- 5. Prism Docker 端口配置 ----
# Prism 内部 nginx 监听 Docker 内部 80，映射到宿主机 HTTP_PORT
# 默认 8080，可在 .env 中改
grep -q "HTTP_PORT" .env 2>/dev/null || echo "HTTP_PORT=8080" >> .env
PRISM_PORT=$(grep "HTTP_PORT" .env | cut -d'=' -f2)
echo "Prism 将运行在端口: ${PRISM_PORT:-8080}"

# ---- 6. 启动 Prism ----
echo "启动 Docker 服务..."
docker compose up -d --build

echo ""
echo "等待服务健康检查..."
sleep 30
docker compose ps

echo ""
echo "=== 部署完成 ==="
echo "Prism 访问地址: http://$(hostname -I | awk '{print $1}'):${PRISM_PORT:-8080}"
echo "默认账号: admin@prism.dev / PrismAdmin!2026"
echo ""
echo "如需宿主机 nginx 分流，参考 deploy-nginx.conf"
