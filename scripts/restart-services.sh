#!/bin/bash
# ==============================================================================
# Docker Compose 服务重启脚本
# ==============================================================================
# 用途：每天凌晨2点自动重启所有服务
# 执行：先执行 docker compose down，再执行 docker compose up -d
# ==============================================================================

# 设置脚本所在目录为工作目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="/root/AIFutureTrade"

# 日志文件路径
LOG_FILE="${PROJECT_DIR}/logs/restart-services.log"
LOG_DIR="$(dirname "$LOG_FILE")"

# 创建日志目录（如果不存在）
mkdir -p "$LOG_DIR"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 错误处理函数
error_exit() {
    log "ERROR: $1"
    exit 1
}

# 开始执行
log "=========================================="
log "开始重启 Docker Compose 服务"
log "=========================================="

# 切换到项目目录
cd "$PROJECT_DIR" || error_exit "无法切换到项目目录: $PROJECT_DIR"

# 检查 docker compose 命令是否可用
if ! command -v docker &> /dev/null; then
    error_exit "Docker 未安装或不在 PATH 中"
fi

if ! docker compose version &> /dev/null && ! docker-compose version &> /dev/null; then
    error_exit "Docker Compose 未安装或不在 PATH 中"
fi

# 确定使用的命令（docker compose 或 docker-compose）
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi

log "使用命令: $DOCKER_COMPOSE_CMD"

# 第一步：停止并删除所有容器
log "执行: $DOCKER_COMPOSE_CMD down"
if $DOCKER_COMPOSE_CMD down >> "$LOG_FILE" 2>&1; then
    log "✓ 服务已停止并删除"
else
    error_exit "停止服务失败"
fi

# 等待几秒确保所有资源已释放
sleep 5

# 第二步：重新启动所有服务
log "执行: $DOCKER_COMPOSE_CMD up -d"
if $DOCKER_COMPOSE_CMD up -d >> "$LOG_FILE" 2>&1; then
    log "✓ 服务已重新启动"
else
    error_exit "启动服务失败"
fi

# 等待服务启动
sleep 10

# 检查服务状态
log "检查服务状态:"
$DOCKER_COMPOSE_CMD ps >> "$LOG_FILE" 2>&1

log "=========================================="
log "服务重启完成"
log "=========================================="
log ""

