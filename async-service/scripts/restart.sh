#!/bin/bash

# ============================================
# Async Service 重启脚本
# ============================================
# 功能：
#   1. 停止当前运行的服务（调用stop.sh）
#   2. 等待服务完全停止
#   3. 重新构建和启动服务（调用build-and-start.sh）
#
# 使用方法：
#   bash restart.sh                    # 交互模式，会询问是否启动
#   bash restart.sh --auto-start       # 自动启动模式
#   bash restart.sh -y                 # 自动启动模式（简写）
#   bash restart.sh --force            # 强制停止后重启
#   bash restart.sh --no-build         # 不重新构建，只重启（使用现有JAR）
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
STOP_SCRIPT="$SCRIPT_DIR/stop.sh"
BUILD_START_SCRIPT="$SCRIPT_DIR/build-and-start.sh"

log_info "Async Service目录: $ASYNC_SERVICE_DIR"
log_info "停止脚本: $STOP_SCRIPT"
log_info "构建启动脚本: $BUILD_START_SCRIPT"

# 检查脚本是否存在
if [ ! -f "$STOP_SCRIPT" ]; then
    log_error "停止脚本不存在: $STOP_SCRIPT"
    exit 1
fi

if [ ! -f "$BUILD_START_SCRIPT" ]; then
    log_error "构建启动脚本不存在: $BUILD_START_SCRIPT"
    exit 1
fi

# 停止服务
stop_service() {
    FORCE_MODE=${1:-""}
    
    log_info "============================================"
    log_info "步骤1: 停止当前服务"
    log_info "============================================"
    
    if [ "$FORCE_MODE" = "--force" ]; then
        bash "$STOP_SCRIPT" --force
    else
        bash "$STOP_SCRIPT"
    fi
    
    # 额外等待确保服务完全停止
    log_info "等待服务完全停止..."
    sleep 2
}

# 启动服务（不构建）
start_without_build() {
    JAR_FILE="$ASYNC_SERVICE_DIR/target/async-service-1.0.0.jar"
    
    if [ ! -f "$JAR_FILE" ]; then
        log_error "JAR文件不存在: $JAR_FILE"
        log_error "请先运行 build-and-start.sh 构建JAR包"
        exit 1
    fi
    
    log_info "============================================"
    log_info "步骤2: 启动服务（使用现有JAR）"
    log_info "============================================"
    
    # 调用build-and-start.sh的start_service函数逻辑
    # 由于无法直接调用函数，我们提取启动逻辑
    cd "$ASYNC_SERVICE_DIR"
    
    # 创建logs目录
    mkdir -p "$ASYNC_SERVICE_DIR/logs"
    
    # 设置JVM参数（与build-and-start.sh保持一致）
    JAVA_OPTS="-Xms1g -Xmx2g \
                -XX:+UseG1GC \
                -XX:MaxGCPauseMillis=200 \
                -XX:+UseStringDeduplication \
                -XX:+OptimizeStringConcat \
                -XX:+UseCompressedOops \
                -XX:+UseCompressedClassPointers \
                -Djava.awt.headless=true \
                -Dfile.encoding=UTF-8"
    
    # 启动服务（后台运行）
    log_info "执行启动命令: java $JAVA_OPTS -jar $JAR_FILE"
    nohup java $JAVA_OPTS -jar "$JAR_FILE" > "$ASYNC_SERVICE_DIR/logs/startup.log" 2>&1 &
    PID=$!
    
    log_info "Async Service已启动，PID: $PID"
    log_info "启动日志文件: $ASYNC_SERVICE_DIR/logs/startup.log"
    log_info "应用日志文件: $ASYNC_SERVICE_DIR/logs/async-service.log"
    
    # 等待几秒检查服务是否启动成功
    log_info "等待服务启动..."
    sleep 5
    
    if ps -p $PID > /dev/null 2>&1; then
        log_info "服务进程运行正常 (PID: $PID)"
        echo "$PID" > "$ASYNC_SERVICE_DIR/async-service.pid"
        
        # 显示启动日志的最后几行
        log_info "============================================"
        log_info "启动日志（最后20行）:"
        log_info "============================================"
        if [ -f "$ASYNC_SERVICE_DIR/logs/startup.log" ]; then
            tail -n 20 "$ASYNC_SERVICE_DIR/logs/startup.log" | while IFS= read -r line; do
                echo "  $line"
            done
        else
            log_warn "启动日志文件尚未创建"
        fi
        log_info "============================================"
    else
        log_error "服务启动失败，进程已退出"
        log_error "请查看启动日志: $ASYNC_SERVICE_DIR/logs/startup.log"
        if [ -f "$ASYNC_SERVICE_DIR/logs/startup.log" ]; then
            log_error "启动日志内容:"
            cat "$ASYNC_SERVICE_DIR/logs/startup.log"
        fi
        exit 1
    fi
}

# 主函数
main() {
    log_info "============================================"
    log_info "Async Service 重启脚本"
    log_info "============================================"
    
    FORCE_MODE=""
    NO_BUILD=""
    AUTO_START=""
    
    # 解析参数
    for arg in "$@"; do
        case "$arg" in
            --force|-f)
                FORCE_MODE="--force"
                ;;
            --no-build|-n)
                NO_BUILD="--no-build"
                ;;
            --auto-start|-y)
                AUTO_START="--auto-start"
                ;;
        esac
    done
    
    # 停止服务
    stop_service "$FORCE_MODE"
    
    # 启动服务
    if [ "$NO_BUILD" = "--no-build" ]; then
        # 不构建，直接启动
        start_without_build
    else
        # 重新构建并启动
        log_info "============================================"
        log_info "步骤2: 重新构建并启动服务"
        log_info "============================================"
        
        if [ -n "$AUTO_START" ]; then
            bash "$BUILD_START_SCRIPT" --auto-start
        else
            bash "$BUILD_START_SCRIPT"
        fi
    fi
    
    log_info "============================================"
    log_info "服务重启完成！"
    log_info "============================================"
    log_info "服务信息:"
    log_info "  - PID文件: $ASYNC_SERVICE_DIR/async-service.pid"
    log_info "  - 启动日志: $ASYNC_SERVICE_DIR/logs/startup.log"
    log_info "  - 应用日志: $ASYNC_SERVICE_DIR/logs/async-service.log"
    log_info ""
    log_info "常用命令:"
    log_info "  查看实时日志: tail -f $ASYNC_SERVICE_DIR/logs/async-service.log"
    log_info "  查看启动日志: tail -f $ASYNC_SERVICE_DIR/logs/startup.log"
    log_info "  停止服务: bash $STOP_SCRIPT"
    log_info "  检查服务状态: ps -p \$(cat $ASYNC_SERVICE_DIR/async-service.pid)"
}

# 执行主函数
main "$@"

