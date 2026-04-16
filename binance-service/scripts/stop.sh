#!/bin/bash

# ============================================
# Binance Service 停止脚本
# ============================================
# 功能：
#   1. 停止 Java 服务（binance-service-*.jar）
#   2. 停止守护进程（watchdog.sh），并清理 PID 文件
#   3. 支持强制杀死进程
#
# 说明：先写入 binance-service.shutdown 通知 watchdog 勿再拉起 Java，
#       再结束 Java，最后结束 watchdog（含 pid 文件缺失时的进程探测）。
#
# 使用方法：
#   bash stop.sh           # 正常停止（SIGTERM）
#   bash stop.sh -f        # 强制停止（SIGKILL）
# ============================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BINANCE_SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$BINANCE_SERVICE_DIR/binance-service.pid"
SHUTDOWN_FLAG="$BINANCE_SERVICE_DIR/binance-service.shutdown"
WATCHDOG_PID_FILE="$BINANCE_SERVICE_DIR/binance-service.watchdog.pid"
WATCHDOG_SCRIPT="$SCRIPT_DIR/watchdog.sh"

log_info "Binance Service目录: $BINANCE_SERVICE_DIR"

FORCE_STOP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--force)
            FORCE_STOP=true
            shift
            ;;
        *)
            log_error "未知参数: $1"
            echo "使用方法: $0 [-f|--force]"
            exit 1
            ;;
    esac
done

# 解析 Java PID：优先 pid 文件，其次按 jar 进程名
resolve_java_pid() {
    PID=""
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE" 2>/dev/null || true)
    fi
    if [ -z "$PID" ] || ! ps -p "$PID" > /dev/null 2>&1; then
        PID=$(pgrep -f "binance-service-1\.0\.0\.jar" 2>/dev/null | head -n 1 || true)
    fi
    if [ -z "$PID" ]; then
        PID=$(pgrep -f "binance-service.*\.jar" 2>/dev/null | head -n 1 || true)
    fi
}

check_java_running() {
    [ -n "$PID" ] && ps -p "$PID" > /dev/null 2>&1
}

stop_java_process() {
    local signal=$1
    local signal_name=$2
    log_info "向 Java 进程发送 ${signal_name} (PID $PID)..."
    kill -"$signal" "$PID" 2>/dev/null || true
    local timeout=30
    local count=0
    while check_java_running; do
        sleep 1
        count=$((count + 1))
        if [ "$count" -ge "$timeout" ]; then
            return 1
        fi
        if [ $((count % 5)) -eq 0 ]; then
            log_info "等待 Java 结束... ($count/${timeout} 秒)"
        fi
    done
    return 0
}

# 结束所有与本项目相关的 watchdog（pid 文件 + pgrep 兜底）
stop_watchdog_all() {
    log_info "----------------------------------------"
    log_info "停止守护进程 (watchdog)..."

    local sig=15
    [ "$FORCE_STOP" = true ] && sig=9

    # 1) pid 文件中的 watchdog
    local wd=""
    if [ -f "$WATCHDOG_PID_FILE" ]; then
        wd=$(cat "$WATCHDOG_PID_FILE" 2>/dev/null || true)
    fi
    if [ -n "$wd" ] && ps -p "$wd" > /dev/null 2>&1; then
        log_info "结束守护进程 PID $wd (信号 $sig)..."
        kill -"$sig" "$wd" 2>/dev/null || true
        if [ "$FORCE_STOP" != true ]; then
            local i=0
            while [ "$i" -lt 20 ] && ps -p "$wd" > /dev/null 2>&1; do
                sleep 1
                i=$((i + 1))
            done
            if ps -p "$wd" > /dev/null 2>&1; then
                log_warn "守护进程未退出，发送 SIGKILL..."
                kill -9 "$wd" 2>/dev/null || true
            fi
        fi
    fi

    rm -f "$WATCHDOG_PID_FILE"

    # 2) 未登记到 pid 文件、仍匹配的 watchdog.sh（同路径）
    if [ -f "$WATCHDOG_SCRIPT" ]; then
        local stray
        stray=$(pgrep -f "$WATCHDOG_SCRIPT" 2>/dev/null || true)
        if [ -n "$stray" ]; then
            log_warn "发现残留守护进程: $stray ，正在结束..."
            echo "$stray" | while read -r p; do
                [ -n "$p" ] || continue
                kill -"$sig" "$p" 2>/dev/null || true
            done
            sleep 2
            stray=$(pgrep -f "$WATCHDOG_SCRIPT" 2>/dev/null || true)
            if [ -n "$stray" ]; then
                echo "$stray" | while read -r p; do
                    [ -n "$p" ] || continue
                    kill -9 "$p" 2>/dev/null || true
                done
            fi
        fi
    fi

    log_info "守护进程已处理完毕"
}

log_info "============================================"
log_info "Binance Service 停止（Java + 守护进程）"
log_info "============================================"

resolve_java_pid

# 通知 watchdog：不要再拉起 Java（与 watchdog.sh 约定）
touch "$SHUTDOWN_FLAG"

if check_java_running; then
    log_info "当前 Java PID: $PID"
    log_info "进程: $(ps -p "$PID" -o pid,ppid,cmd --no-headers 2>/dev/null || echo '未知')"

    if [ "$FORCE_STOP" = true ]; then
        if ! stop_java_process 9 "SIGKILL"; then
            log_error "无法结束 Java 进程"
            rm -f "$SHUTDOWN_FLAG"
            exit 1
        fi
        log_info "Java 已强制结束"
    else
        if ! stop_java_process 15 "SIGTERM"; then
            log_warn "SIGTERM 超时，尝试 SIGKILL..."
            if ! stop_java_process 9 "SIGKILL"; then
                log_error "无法结束 Java 进程"
                rm -f "$SHUTDOWN_FLAG"
                exit 1
            fi
        else
            log_info "Java 已正常结束"
        fi
    fi
else
    log_warn "未发现运行中的 Java 服务（可能已退出）"
fi

rm -f "$PID_FILE"

if check_java_running; then
    log_error "Java 进程仍在运行: $PID"
    rm -f "$SHUTDOWN_FLAG"
    exit 1
fi

stop_watchdog_all

rm -f "$SHUTDOWN_FLAG"

log_info "============================================"
log_info "Binance Service 与守护进程均已停止"
log_info "============================================"
log_info "日志: $BINANCE_SERVICE_DIR/logs/startup.log"
log_info "      $BINANCE_SERVICE_DIR/logs/binance-service.log"
log_info "      $BINANCE_SERVICE_DIR/logs/watchdog.log"

exit 0
