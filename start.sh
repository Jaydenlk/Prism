#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# Prism v2 一键启动脚本
#
# 用法：
#   ./start.sh           # 启动（自动 build 缺失镜像）
#   ./start.sh rebuild   # 强制重 build backend 镜像（改了代码后用）
#   ./start.sh down      # 停止所有容器（保留数据卷）
#   ./start.sh nuke      # 停止并删除数据卷（开发期重置）
#   ./start.sh logs      # 跟随 backend 日志
#   ./start.sh status    # 显示容器 + 内置 MCP 状态
# ----------------------------------------------------------------------------
set -euo pipefail

PROJECT="prismv3"
COMPOSE_FILE="docker-compose.yml"
HTTP_PORT="${HTTP_PORT:-8080}"
HEALTH_URL="http://localhost:${HTTP_PORT}/health/ready"
WAIT_SECONDS=60

cd "$(dirname "$0")"

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
blue()   { printf '\033[34m%s\033[0m\n' "$*"; }

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    red "✗ Docker 未安装。请安装 Docker Desktop 或 Docker Engine 后重试。"
    exit 1
  fi
  if ! docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
    red "✗ Docker daemon 不可达。请启动 Docker Desktop（Windows）或 systemctl start docker（Linux）后重试。"
    exit 1
  fi
}

require_env() {
  if [[ ! -f .env ]]; then
    yellow "⚠ .env 不存在，从 .env.example 复制一份默认值。"
    cp .env.example .env
    yellow "  请编辑 .env 设置实际密钥（JWT_SECRET / ENCRYPTION_KEY / CALLBACK_SECRET 等），然后重新运行 ./start.sh。"
    exit 2
  fi

  # Three-secret independence (CLAUDE.md 铁律 7 / ADR-050)
  for k in JWT_SECRET ENCRYPTION_KEY CALLBACK_SECRET; do
    if ! grep -qE "^${k}=.+" .env; then
      red "✗ .env 缺少 ${k}。生产部署必填，三密钥必须独立。"
      exit 3
    fi
  done

  blue "✓ .env 必填密钥已设置。"

  # SearXNG self-hosted — auto-generate secret if missing (zero user friction)
  if ! grep -qE "^SEARXNG_SECRET_KEY=.+" .env; then
    if command -v python >/dev/null 2>&1; then
      key=$(python -c "import secrets; print(secrets.token_hex(32))")
    elif command -v openssl >/dev/null 2>&1; then
      key=$(openssl rand -hex 32)
    else
      key="changeme-$(date +%s%N)-$(whoami 2>/dev/null || echo dev)"
      yellow "  ⚠ python/openssl 都没有，SEARXNG_SECRET_KEY 用降级随机值（生产请手填）"
    fi
    # Strip any pre-existing empty SEARXNG_SECRET_KEY= line, then append fresh
    sed -i.bak '/^SEARXNG_SECRET_KEY=$/d' .env && rm -f .env.bak
    printf '\nSEARXNG_SECRET_KEY=%s\n' "$key" >> .env
    green "  ✓ SEARXNG_SECRET_KEY 自动生成（self-hosted SearXNG，免费无限）"
  else
    green "  ✓ SEARXNG_SECRET_KEY 已配置 → searxng MCP 启动期会注册"
  fi

  # Search MCP keys — informational only
  if grep -qE "^EXA_API_KEY=.+" .env; then
    green "  ✓ EXA_API_KEY 已配置 → exa MCP 启动期会自动注册（语义搜索备用）"
  else
    yellow "  ⚠ EXA_API_KEY 未设 → exa 备用不可用（可选；searxng 已能覆盖大部分搜索）"
  fi
  if grep -qE "^TAVILY_API_KEY=.+" .env; then
    green "  ✓ TAVILY_API_KEY 已配置 → tavily MCP 启动期会注册（AI 友好搜索备用）"
  fi
}

wait_healthy() {
  local i=0
  while (( i < WAIT_SECONDS )); do
    if curl -fsS -o /dev/null "$HEALTH_URL" 2>/dev/null; then
      green "✓ Backend healthy（${i}s）"
      return 0
    fi
    sleep 1
    i=$(( i + 1 ))
  done
  red "✗ Backend 在 ${WAIT_SECONDS}s 内未变为 healthy。查日志：./start.sh logs"
  return 1
}

print_summary() {
  echo
  green "============================================="
  green "  Prism v2 启动完成"
  green "============================================="
  echo
  blue "  访问入口"
  echo "    用户端    http://localhost:${HTTP_PORT}/Prism.html"
  echo "    管理端    http://localhost:${HTTP_PORT}/admin.html"
  echo "    Health    http://localhost:${HTTP_PORT}/health/ready"
  echo
  blue "  默认管理员账号（首次启动从 .env 注入）"
  echo "    Email     ${ADMIN_EMAIL:-admin@prism.dev}"
  echo "    Password  ${ADMIN_PASSWORD:-PrismAdmin!2026}"
  echo
  blue "  内置 MCP 状态"
  docker exec ${PROJECT}-postgres-1 psql -U prism -d prism -t -c \
    "select '    ' || rpad(name, 16) || rpad(transport, 8) || coalesce(url, command) from mcp_servers where scope='system' order by name;" 2>/dev/null \
    | sed '/^[[:space:]]*$/d'
  echo
  blue "  常用命令"
  echo "    ./start.sh logs       跟随 backend 日志"
  echo "    ./start.sh status     看容器 + MCP 状态"
  echo "    ./start.sh down       停止（保留数据）"
  echo "    ./start.sh rebuild    改代码后强制重 build"
  echo
}

cmd_up() {
  require_docker
  require_env
  blue "→ docker compose -p ${PROJECT} up -d ..."
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d "$@"
  wait_healthy || exit 4
  print_summary
}

cmd_rebuild() {
  require_docker
  require_env
  blue "→ docker compose -p ${PROJECT} build backend"
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" build backend
  blue "→ 启动 searxng（首次拉镜像 ~80MB）"
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d searxng
  blue "→ 重启 backend（保留 postgres/redis 数据）"
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d --force-recreate --no-deps backend
  blue "→ 重启 nginx（同步 frontend 静态文件）"
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d --force-recreate --no-deps nginx
  wait_healthy || exit 4
  print_summary
}

cmd_down() {
  blue "→ docker compose -p ${PROJECT} down"
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down
  green "✓ 已停止（数据卷保留）"
}

cmd_nuke() {
  yellow "⚠ 这会删除所有数据（postgres + redis 卷）。确认？(y/N)"
  read -r reply
  if [[ "$reply" != "y" && "$reply" != "Y" ]]; then
    echo "取消"
    exit 0
  fi
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down -v
  green "✓ 已停止并清空数据卷。下次 ./start.sh 会重新 alembic upgrade + bootstrap admin/marketplace/MCP。"
}

cmd_logs() {
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" logs -f --tail 50 backend
}

cmd_status() {
  blue "→ 容器状态"
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" ps
  echo
  blue "→ 系统级 MCP servers"
  docker exec ${PROJECT}-postgres-1 psql -U prism -d prism -c \
    "select name, transport, scope, coalesce(url, command) as endpoint from mcp_servers where scope='system' order by name;" 2>/dev/null
  echo
  blue "→ 默认 marketplace"
  docker exec ${PROJECT}-postgres-1 psql -U prism -d prism -c \
    "select name, url from marketplace_registry order by created_at limit 5;" 2>/dev/null
}

case "${1:-up}" in
  up|"")     cmd_up "${@:2}" ;;
  rebuild)   cmd_rebuild ;;
  down|stop) cmd_down ;;
  nuke|reset) cmd_nuke ;;
  logs)      cmd_logs ;;
  status|ps) cmd_status ;;
  restart)   cmd_down && cmd_up ;;
  *)
    cat <<USAGE
用法：./start.sh [command]

命令：
  up        启动（默认；自动 build 缺失镜像）
  rebuild   改代码后强制重 build backend + 重启 backend & nginx（保留数据）
  down      停止所有容器（保留数据卷）
  nuke      停止并删除数据卷（开发重置；会丢失账号、会话、安装记录）
  logs      跟随 backend 日志
  status    显示容器 + 系统 MCP + 默认 marketplace
  restart   = down && up
USAGE
    exit 1
    ;;
esac
