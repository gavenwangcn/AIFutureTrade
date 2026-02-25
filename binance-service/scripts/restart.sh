#!/bin/bash

# ============================================
# Binance Service 重启脚本
# ============================================
# 功能：
#   1. 停止正在运行的服务
#   2. 可选：重新构建JAR包
#   3. 启动服务
#
# 使用方法：
#   bash restart.sh           # 仅重启服务（不重新构建）
#   bash restart.sh --build   # 重启并重新构建
#   bash restart.sh -b        # 重启并重新构建（简写）
#   bash restart.sh --force   # 强制重启（先kill再启动）
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
PROJECT_ROOT="$(cd "$BINANCE_SERVICE_DIR/.." && pwd)"
STOP_SCRIPT="$SCRIPT_DIR/stop.sh"
BUILD_SCRIPT="$SCRIPT_DIR/build-and-start.sh"

log_info "Binance Service目录: $BINANCE_SERVICE_DIR"
log_info "项目根目录: $PROJECT_ROOT"

# 默认参数
DO_BUILD=false
DO_FORCE=false
AUTO_START=true

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--build)
            DO_BUILD=true
            shift
            ;;
        -f|--force)
            DO_FORCE=true
            shift
            ;;
        -h|--help)
            echo "使用方法: $0 [OPTIONS]"
            echo ""
            echo "选项:"
            echo "  -b, --build    重新构建JAR包后再启动"
            echo "  -f, --force    强制重启（使用SIGKILL）"
            echo "  -h, --help     显示帮助信息"
            echo ""
            echo "示例:"
            echo "  $0                    # 仅重启服务"
            echo "  $0 --build            # 重新构建并重启"
            echo "  $0 -b -f              # 强制重新构建并重启"
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            exit 1
            ;;
    esac
done

# 检查依赖脚本是否存在
check_scripts() {
    if [ ! -f "$STOP_SCRIPT" ]; then
        log_error "停止脚本不存在: $STOP_SCRIPT"
        exit 1
    fi
    
    if [ "$DO_BUILD" = true ] && [ ! -f "$BUILD_SCRIPT" ]; then
        log_error "构建脚本不存在: $BUILD_SCRIPT"
        exit 1
    fi
}

# 获取当前服务状态
get_service_status() {
    local PID_FILE="$BINANCE_SERVICE_DIR/binance-service.pid"
    
    if [ ! -f "$PID_FILE" ]; then
        echo "not_running"
        return
    fi
    
    local PID=$(cat "$PID_FILE" 2>/dev/null || true)
    
    if [ -z "$PID" ]; then
        echo "not_running"
        return
    fi
    
    if ps -p $PID > /dev/null 2>&1; then
        echo "running:$PID"
    else
        echo "not_running"
    fi
}

# 停止服务
stop_service() {
    log_info "停止Binance Service..."
    
    local stop_args=""
    if [ "$DO_FORCE" = true ]; then
        stop_args="-f"
    fi
    
    bash "$STOP_SCRIPT" $stop_args
    return $?
}

# 构建服务
build_service() {
    log_info "============================================"
    log_info "开始构建Binance Service..."
    log_info "============================================"
    
    cd "$BINANCE_SERVICE_DIR"
    
    # 检查Java
    if ! command -v java &> /dev/null; then
        log_error "Java未安装，请先安装JDK 17+"
        exit 1
    fi
    
    # 检查Maven
    if ! command -v mvn &> /dev/null; then
        log_error "Maven未安装，请先安装Maven"
        exit 1
    fi
    
    log_info "执行Maven构建: mvn clean package -DskipTests"
    
    if mvn clean package -DskipTests; then
        log_info "构建完成"
        
        # 检查JAR文件
        local JAR_FILE="$BINANCE_SERVICE_DIR/target/binance-service-1.0.0.jar"
        if [ ! -f "$JAR_FILE" ]; then
            log_error "JAR文件未找到: $JAR_FILE"
            exit 1
        fi
        
        local JAR_SIZE=$(ls -lh "$JAR_FILE" | awk '{print $5}')
        log_info "JAR包: $JAR_FILE (大小: $JAR_SIZE)"
    else
        log_error "构建失败"
        exit 1
    fi
}

# 启动服务
start_service() {
    local JAR_FILE="$BINANCE_SERVICE_DIR/target/binance-service-1.0.0.jar"
    
    if [ ! -f "$JAR_FILE" ]; then
        log_error "JAR文件不存在: $JAR_FILE"
        log_error "请先运行构建: bash build-and-start.sh --build"
        exit 1
    fi
    
    log_info "============================================"
    log_info "启动Binance Service..."
    log_info "============================================"
    
    # 创建logs目录
    mkdir -p "$BINANCE_SERVICE_DIR/logs"
    
    # JVM参数（高性能优化）
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
    nohup java $JAVA_OPTS -jar "$JAR_FILE" > "$BINANCE_SERVICE_DIR/logs/startup.log" 2>&1 &
    local PID=$!
    
    log_info "Binance Service已启动，PID: $PID"
    echo "$PID" > "$BINANCE_SERVICE_DIR/binance-service.pid"
    
    # 等待几秒检查服务是否启动成功
    log_info "等待服务启动..."
    sleep 5
    
    if ps -p $PID > /dev/null 2>&1; then
        log_info "服务进程运行正常 (PID: $PID)"
        
        # 显示启动日志的最后几行
        log_info "============================================"
        log_info "启动日志（最后20行）:"
        log_info "============================================"
        if [ -f "$BINANCE_SERVICE_DIR/logs/startup.log" ]; then
            tail -n 20 "$BINANCE_SERVICE_DIR/logs/startup.log" | while IFS= read -r line; do
                echo "  $line"
            done
        fi
        log_info "============================================"
        
        return 0
    else
        log_error "服务启动失败"
        if [ -f "$BINANCE_SERVICE_DIR/logs/startup.log" ]; then
            log_error "启动日志内容:"
            cat "$BINANCE_SERVICE_DIR/logs/startup.log"
        fi
        return 1
    fi
}

# 主函数
main() {
    log_info "============================================"
    log_info "Binance Service 重启脚本"
    log_info "============================================"
    
    # 检查依赖脚本
    check_scripts
    
    # 获取当前状态
    local status=$(get_service_status)
    
    if [[ "$status" == running:* ]]; then
        local current_pid=${status#running:}
        log_info "当前服务状态: 运行中 (PID: $current_pid)"
        log_info "进程详情: $(ps -p $current_pid -o pid,ppid,cmd --no-headers 2>/dev/null || echo '未知')"
    else
        log_info "当前服务状态: 未运行"
    fi
    
    # 停止服务
    if [[ "$status" == running:* ]]; then
        stop_service
        if [ $? -ne 0 ]; then
            log_error "停止服务失败"
            exit 1
        fi
    else
        log_warn "服务未运行，无需停止"
    fi
    
    # 可选：构建服务
    if [ "$DO_BUILD" = true ]; then
        build_service
        if [ $? -ne 0 ]; then
            log_error "构建服务失败"
            exit 1
        fi
    fi
    
    # 启动服务
    if [ "$DO_BUILD" = false ]; then
        # 如果不构建，检查JAR文件是否存在
        local JAR_FILE="$BINANCE_SERVICE_DIR/target/binance-service-1.0.0.jar"
        if [ ! -f "$JAR_FILE" ]; then
            log_warn "JAR文件不存在，自动构建..."
            build_service
        fi
    fi
    
    start_service
    if [ $? -ne 0 ]; then
        log_error "启动服务失败"
        exit 1
    fi
    
    log_info "============================================"
    log_info "Binance Service 重启完成！"
    log_info "============================================"
    log_info "服务信息:"
    log_info "  - PID文件: $BINANCE_SERVICE_DIR/binance-service.pid"
    log_info "  - 启动日志: $BINANCE_SERVICE_DIR/logs/startup.log"
    log_info "  - 应用日志: $BINANCE_SERVICE_DIR/logs/binance-service.log"
    log_info ""
    log_info "常用命令:"
    log_info "  查看实时日志: tail -f $BINANCE_SERVICE_DIR/logs/binance-service.log"
    log_info "  停止服务: bash $STOP_SCRIPT"
    log_info "  检查服务状态: ps -p \$(cat $BINANCE_SERVICE_DIR/binance-service.pid)"
}

# 执行主函数
main
