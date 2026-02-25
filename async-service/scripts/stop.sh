#!/bin/bash

# ============================================
# Async Service 停止脚本
# ============================================
# 功能：
#   1. 读取PID文件获取服务进程ID
#   2. 优雅地停止服务（发送SIGTERM信号）
#   3. 等待进程退出（最多30秒）
#   4. 如果进程未退出，强制杀死（SIGKILL）
#   5. 清理PID文件
#
# 使用方法：
#   bash stop.sh           # 正常停止
#   bash stop.sh --force   # 强制停止（立即发送SIGKILL）
# ============================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASYNC_SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$ASYNC_SERVICE_DIR/async-service.pid"

log_info "Async Service目录: $ASYNC_SERVICE_DIR"
log_info "PID文件: $PID_FILE"

# 检查服务是否运行
check_service_running() {
    if [ ! -f "$PID_FILE" ]; then
        log_warn "PID文件不存在: $PID_FILE"
        return 1
    fi
    
    PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -z "$PID" ]; then
        log_warn "PID文件为空"
        return 1
    fi
    
    if ! ps -p "$PID" > /dev/null 2>&1; then
        log_warn "进程 $PID 不存在（可能已停止）"
        rm -f "$PID_FILE"
        return 1
    fi
    
    return 0
}

# 停止服务
stop_service() {
    FORCE_MODE=${1:-""}
    
    if ! check_service_running; then
        log_info "服务未运行，无需停止"
        return 0
    fi
    
    PID=$(cat "$PID_FILE")
    log_info "找到服务进程，PID: $PID"
    
    if [ "$FORCE_MODE" = "--force" ]; then
        log_warn "强制停止模式：立即发送SIGKILL信号"
        kill -9 "$PID" 2>/dev/null || true
        sleep 1
    else
        log_info "发送SIGTERM信号，优雅停止服务..."
        kill "$PID" 2>/dev/null || {
            log_error "无法发送停止信号到进程 $PID"
            rm -f "$PID_FILE"
            return 1
        }
        
        # 等待进程退出（最多30秒）
        log_info "等待服务停止（最多30秒）..."
        for i in {1..30}; do
            if ! ps -p "$PID" > /dev/null 2>&1; then
                log_info "服务已优雅停止"
                break
            fi
            sleep 1
            if [ $((i % 5)) -eq 0 ]; then
                log_info "等待中... ($i/30秒)"
            fi
        done
        
        # 如果进程仍在运行，强制杀死
        if ps -p "$PID" > /dev/null 2>&1; then
            log_warn "服务未在30秒内停止，强制杀死进程..."
            kill -9 "$PID" 2>/dev/null || true
            sleep 1
        fi
    fi
    
    # 确认进程已停止
    if ps -p "$PID" > /dev/null 2>&1; then
        log_error "无法停止进程 $PID"
        return 1
    else
        log_info "服务已成功停止"
        rm -f "$PID_FILE" 2>/dev/null || true
        return 0
    fi
}

# 主函数
main() {
    log_info "============================================"
    log_info "Async Service 停止脚本"
    log_info "============================================"
    
    FORCE_MODE=""
    if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
        FORCE_MODE="--force"
    fi
    
    if stop_service "$FORCE_MODE"; then
        log_info "============================================"
        log_info "服务停止完成"
        log_info "============================================"
    else
        log_error "============================================"
        log_error "服务停止失败"
        log_error "============================================"
        exit 1
    fi
}

# 执行主函数
main "$@"

