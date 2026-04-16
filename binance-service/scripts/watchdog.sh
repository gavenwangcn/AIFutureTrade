#!/bin/bash
# ============================================
# Binance Service 守护进程：Java 退出后自动重启
# ============================================
# 由 build-and-start.sh --watchdog 以 nohup 拉起；请勿直接 java -jar 与 watchdog 混用同一套 PID。
#
# 环境变量：
#   BINANCE_RESTART_DELAY  重启前等待秒数（默认 10）
#
# 停止：bash scripts/stop.sh（会置 shutdown 标志并结束本进程）
# ============================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BINANCE_SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=common-env.sh
source "$SCRIPT_DIR/common-env.sh"

SHUTDOWN_FLAG="$BINANCE_SERVICE_DIR/binance-service.shutdown"
PID_FILE="$BINANCE_SERVICE_DIR/binance-service.pid"
WATCHDOG_PID_FILE="$BINANCE_SERVICE_DIR/binance-service.watchdog.pid"
LOG_DIR="$BINANCE_SERVICE_DIR/logs"
RESTART_DELAY="${BINANCE_RESTART_DELAY:-10}"

mkdir -p "$LOG_DIR"
WD_LOG="$LOG_DIR/watchdog.log"

log_wd() {
    echo "[$(date -Iseconds)] [watchdog] $1" | tee -a "$WD_LOG"
}

# 单实例：已有 watchdog 在跑则退出
if [ -f "$WATCHDOG_PID_FILE" ]; then
    OW=$(cat "$WATCHDOG_PID_FILE" 2>/dev/null || true)
    if [ -n "$OW" ] && ps -p "$OW" > /dev/null 2>&1; then
        log_wd "refuse start: watchdog already running (PID $OW)"
        exit 1
    fi
fi

echo $$ > "$WATCHDOG_PID_FILE"
trap 'rm -f "$WATCHDOG_PID_FILE"; log_wd "received signal, exiting"; exit 0' INT TERM

rm -f "$SHUTDOWN_FLAG"

log_wd "started (PID $$), jar=$BINANCE_JAR_FILE, restart_delay=${RESTART_DELAY}s"

while true; do
    if [ -f "$SHUTDOWN_FLAG" ]; then
        log_wd "shutdown flag found before start, exiting"
        rm -f "$SHUTDOWN_FLAG" "$PID_FILE" "$WATCHDOG_PID_FILE"
        exit 0
    fi

    if [ ! -f "$BINANCE_JAR_FILE" ]; then
        log_wd "JAR not found: $BINANCE_JAR_FILE, retry in ${RESTART_DELAY}s"
        sleep "$RESTART_DELAY"
        continue
    fi

    log_wd "starting java"
    # 追加写入，保留多次启动记录
    {
        echo ""
        echo "======== $(date -Iseconds) watchdog spawn java ========"
    } >> "$LOG_DIR/startup.log"

    java $BINANCE_JAVA_OPTS -jar "$BINANCE_JAR_FILE" >> "$LOG_DIR/startup.log" 2>&1 &
    JAVA_PID=$!
    echo "$JAVA_PID" > "$PID_FILE"
    log_wd "java PID $JAVA_PID"

    # wait 不因子进程非零退出而失败整个脚本
    set +e
    wait "$JAVA_PID"
    EC=$?
    set -e

    if [ -f "$SHUTDOWN_FLAG" ]; then
        log_wd "java exited (code=$EC), shutdown requested — stop watchdog"
        rm -f "$SHUTDOWN_FLAG" "$PID_FILE" "$WATCHDOG_PID_FILE"
        exit 0
    fi

    log_wd "java exited unexpectedly (code=$EC), restarting in ${RESTART_DELAY}s"
    rm -f "$PID_FILE"
    sleep "$RESTART_DELAY"
done
