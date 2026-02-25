#!/bin/bash

# ============================================
# Binance Service 停止脚本
# ============================================
# 功能：
#   1. 读取PID文件并停止服务进程
#   2. 支持强制杀死进程
#   3. 清理PID文件
#   4. 显示停止状态
#
# 使用方法：
#   bash stop.sh           # 正常停止（发送SIGTERM）
#   bash stop.sh -f        # 强制停止（发送SIGKILL）
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
BINANCE_SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$BINANCE_SERVICE_DIR/binance-service.pid"

log_info "Binance Service目录: $BINANCE_SERVICE_DIR"

# 停止模式：false=正常停止，true=强制停止
FORCE_STOP=false

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--force)
            FORCE_STOP=true
            shift
            ;;
        *)
            log_error "未知参数: $1"
            echo "使用方法: $0 [-f|--force]"
            echo "  无参数: 正常停止（发送SIGTERM）"
            echo "  -f/--force: 强制停止（发送SIGKILL）"
            exit 1
            ;;
    esac
done

# 检查PID文件是否存在
if [ ! -f "$PID_FILE" ]; then
    log_warn "PID文件不存在: $PID_FILE"
    log_warn "尝试查找正在运行的进程..."
    
    # 尝试通过进程名查找
    PID=$(pgrep -f "binance-service.*\.jar" 2>/dev/null || true)
    
    if [ -z "$PID" ]; then
        log_error "未找到正在运行的Binance Service进程"
        exit 0
    fi
    
    log_info "找到进程PID: $PID"
else
    # 读取PID文件
    PID=$(cat "$PID_FILE" 2>/dev/null || true)
    
    if [ -z "$PID" ]; then
        log_error "PID文件为空: $PID_FILE"
        log_warn "尝试查找正在运行的进程..."
        PID=$(pgrep -f "binance-service.*\.jar" 2>/dev/null || true)
        
        if [ -z "$PID" ]; then
            log_error "未找到正在运行的Binance Service进程"
            exit 0
        fi
    fi
fi

# 检查进程是否存在
check_process() {
    if [ -n "$PID" ] && ps -p $PID > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 停止进程
stop_process() {
    local signal=$1
    local signal_name=$2
    
    log_info "发送${signal_name}信号到进程 $PID..."
    kill -$signal $PID 2>/dev/null || true
    
    # 等待进程停止
    local timeout=30
    local count=0
    
    while check_process; do
        sleep 1
        count=$((count + 1))
        
        if [ $count -ge $timeout ]; then
            return 1
        fi
        
        if [ $((count % 5)) -eq 0 ]; then
            log_info "等待进程停止... ($count/$timeout 秒)"
        fi
    done
    
    return 0
}

# 主逻辑
log_info "============================================"
log_info "Binance Service 停止脚本"
log_info "============================================"

if ! check_process; then
    log_warn "Binance Service进程未运行或已停止"
    
    # 清理PID文件
    if [ -f "$PID_FILE" ]; then
        log_info "清理PID文件..."
        rm -f "$PID_FILE"
    fi
    
    exit 0
fi

log_info "找到进程 PID: $PID"
log_info "进程状态: $(ps -p $PID -o pid,ppid,cmd --no-headers 2>/dev/null || echo '未知')"

# 停止进程
if [ "$FORCE_STOP" = true ]; then
    log_warn "强制停止模式：发送SIGKILL信号..."
    
    if ! stop_process 9 "SIGKILL"; then
        log_error "强制停止失败，进程仍在运行"
        log_error "请手动检查: ps -p $PID"
        exit 1
    fi
    
    log_info "进程已被强制停止"
else
    log_info "正常停止模式：发送SIGTERM信号..."
    log_info "等待进程优雅停止（最多30秒）..."
    
    if ! stop_process 15 "SIGTERM"; then
        log_warn "进程未能在30秒内优雅停止"
        log_warn "尝试强制停止..."
        
        if ! stop_process 9 "SIGKILL"; then
            log_error "停止失败，进程仍在运行"
            log_error "请手动检查: ps -p $PID"
            exit 1
        fi
        
        log_info "进程已被强制停止"
    else
        log_info "进程已正常停止"
    fi
fi

# 清理PID文件
if [ -f "$PID_FILE" ]; then
    log_info "清理PID文件..."
    rm -f "$PID_FILE"
fi

# 验证进程已停止
if check_process; then
    log_error "进程仍然在运行，请手动处理"
    exit 1
fi

log_info "============================================"
log_info "Binance Service 已停止"
log_info "============================================"
log_info "日志文件位置:"
log_info "  - 启动日志: $BINANCE_SERVICE_DIR/logs/startup.log"
log_info "  - 应用日志: $BINANCE_SERVICE_DIR/logs/binance-service.log"

exit 0
