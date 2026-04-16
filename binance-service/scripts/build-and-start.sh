#!/bin/bash

# ============================================
# Binance Service 构建和启动脚本
# ============================================
# 功能：
#   1. 检查并安装JDK 17和Maven（如果需要）
#   2. 使用mvn clean package构建JAR包
#   3. 使用java -jar方式启动服务
#
# 使用方法：
#   bash build-and-start.sh              # 交互模式，会询问是否启动
#   bash build-and-start.sh --auto-start # 自动启动（单次 nohup java）
#   bash build-and-start.sh -y
#   bash build-and-start.sh --watchdog   # 构建后由守护进程托管，Java 退出则自动重启
#   bash build-and-start.sh -w -y        # 同上并跳过询问
#   WATCHDOG=true bash build-and-start.sh
#   BINANCE_RESTART_DELAY=30 ...        # 重启间隔秒数（默认 10）
#   AUTO_START=true bash build-and-start.sh
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

log_info "Binance Service目录: $BINANCE_SERVICE_DIR"
log_info "项目根目录: $PROJECT_ROOT"

# 检查Java是否已安装
check_java() {
    if command -v java &> /dev/null; then
        JAVA_VERSION=$(java -version 2>&1 | head -n 1 | cut -d'"' -f2 | sed '/^1\./s///' | cut -d'.' -f1)
        if [ "$JAVA_VERSION" -ge 17 ]; then
            log_info "Java已安装，版本: $(java -version 2>&1 | head -n 1)"
            return 0
        else
            log_warn "Java版本过低（需要17+），当前版本: $JAVA_VERSION"
            return 1
        fi
    else
        log_warn "Java未安装"
        return 1
    fi
}

# 检查Maven是否已安装
check_maven() {
    if command -v mvn &> /dev/null; then
        log_info "Maven已安装，版本: $(mvn -version | head -n 1)"
        return 0
    else
        log_warn "Maven未安装"
        return 1
    fi
}

# 安装JDK和Maven
install_jdk_maven() {
    log_info "开始安装JDK 17和Maven..."
    
    INSTALL_SCRIPT="$PROJECT_ROOT/scripts/install-jdk17-maven.sh"
    if [ ! -f "$INSTALL_SCRIPT" ]; then
        log_error "安装脚本不存在: $INSTALL_SCRIPT"
        exit 1
    fi
    
    # 检查是否有sudo权限
    if [ "$EUID" -ne 0 ]; then
        log_info "需要sudo权限来安装JDK和Maven，请输入密码..."
        sudo bash "$INSTALL_SCRIPT"
    else
        bash "$INSTALL_SCRIPT"
    fi
    
    # 重新加载环境变量
    if [ -f /etc/profile ]; then
        source /etc/profile
    fi
    if [ -f ~/.bashrc ]; then
        source ~/.bashrc
    fi
}

# 构建JAR包
build_jar() {
    log_info "开始构建Binance Service JAR包..." >&2
    cd "$BINANCE_SERVICE_DIR"
    
    log_info "执行Maven构建命令: mvn clean package -DskipTests" >&2
    log_info "============================================" >&2
    
    # 清理并构建，显示输出
    if mvn clean package -DskipTests; then
        log_info "============================================" >&2
        log_info "Maven构建完成" >&2
    else
        log_error "============================================" >&2
        log_error "Maven构建失败" >&2
        exit 1
    fi
    
    # 检查JAR文件是否存在
    JAR_FILE="$BINANCE_SERVICE_DIR/target/binance-service-1.0.0.jar"
    if [ ! -f "$JAR_FILE" ]; then
        log_error "JAR文件未找到: $JAR_FILE" >&2
        log_info "可用的文件:" >&2
        ls -lh "$BINANCE_SERVICE_DIR/target/" || true >&2
        exit 1
    fi
    
    # 显示JAR文件信息（输出到stderr，避免被捕获）
    JAR_SIZE=$(ls -lh "$JAR_FILE" | awk '{print $5}')
    log_info "JAR包构建成功: $JAR_FILE (大小: $JAR_SIZE)" >&2
    
    # 只输出文件路径到stdout，供调用者捕获
    echo "$JAR_FILE"
}


# shellcheck source=common-env.sh
source "$SCRIPT_DIR/common-env.sh"

# 启动服务（直接 java，无守护；进程退出不会自动拉起）
start_service() {
    JAR_FILE="$1"
    
    if [ ! -f "$JAR_FILE" ]; then
        log_error "JAR文件不存在: $JAR_FILE"
        exit 1
    fi
    
    log_info "启动Binance Service..."
    log_info "JAR文件: $JAR_FILE"
    
    # 创建logs目录
    mkdir -p "$BINANCE_SERVICE_DIR/logs"
    
    log_info "所有配置从application.yml读取（可通过环境变量覆盖）"
    rm -f "$BINANCE_SERVICE_DIR/binance-service.shutdown"
    
    # 启动服务（后台运行）；JVM 参数见 common-env.sh
    log_info "执行启动命令: java <opts> -jar $JAR_FILE"
    nohup java $BINANCE_JAVA_OPTS -jar "$JAR_FILE" > "$BINANCE_SERVICE_DIR/logs/startup.log" 2>&1 &
    PID=$!
    
    log_info "Binance Service已启动，PID: $PID"
    log_info "启动日志文件: $BINANCE_SERVICE_DIR/logs/startup.log"
    log_info "应用日志文件: $BINANCE_SERVICE_DIR/logs/binance-service.log"
    
    # 等待几秒检查服务是否启动成功
    log_info "等待服务启动..."
    sleep 5
    
    if ps -p $PID > /dev/null 2>&1; then
        log_info "服务进程运行正常 (PID: $PID)"
        echo "$PID" > "$BINANCE_SERVICE_DIR/binance-service.pid"
        
        # 显示启动日志的最后几行
        log_info "============================================"
        log_info "启动日志（最后20行）:"
        log_info "============================================"
        if [ -f "$BINANCE_SERVICE_DIR/logs/startup.log" ]; then
            tail -n 20 "$BINANCE_SERVICE_DIR/logs/startup.log" | while IFS= read -r line; do
                echo "  $line"
            done
        else
            log_warn "启动日志文件尚未创建"
        fi
        log_info "============================================"
    else
        log_error "服务启动失败，进程已退出"
        log_error "请查看启动日志: $BINANCE_SERVICE_DIR/logs/startup.log"
        if [ -f "$BINANCE_SERVICE_DIR/logs/startup.log" ]; then
            log_error "启动日志内容:"
            cat "$BINANCE_SERVICE_DIR/logs/startup.log"
        fi
        exit 1
    fi
}

# 守护进程模式：watchdog.sh 负责在 Java 崩溃退出后自动重启（见 logs/watchdog.log）
start_under_watchdog() {
    JAR_FILE="$1"
    if [ ! -f "$JAR_FILE" ]; then
        log_error "JAR文件不存在: $JAR_FILE"
        exit 1
    fi
    if [ "$JAR_FILE" != "$BINANCE_JAR_FILE" ]; then
        log_warn "守护脚本固定读取 JAR: $BINANCE_JAR_FILE（请与构建产物路径一致）"
    fi
    mkdir -p "$BINANCE_SERVICE_DIR/logs"
    rm -f "$BINANCE_SERVICE_DIR/binance-service.shutdown"
    log_info "以守护进程模式启动（进程异常退出将自动重启，间隔 ${BINANCE_RESTART_DELAY:-10}s）..."
    log_info "守护日志: $BINANCE_SERVICE_DIR/logs/watchdog.log"
    # 勿在此处写入 binance-service.watchdog.pid，否则子进程启动后会读到自身 PID 误判为「已有实例」；仅由 watchdog.sh 写入
    nohup bash "$SCRIPT_DIR/watchdog.sh" >> "$BINANCE_SERVICE_DIR/logs/watchdog.log" 2>&1 &
    WD_PID=$!
    log_info "守护进程 PID: $WD_PID（PID 文件由 watchdog.sh 写入）"
    sleep 3
    if ! ps -p "$WD_PID" > /dev/null 2>&1; then
        log_error "守护进程已退出，请查看: $BINANCE_SERVICE_DIR/logs/watchdog.log"
        exit 1
    fi
    log_info "等待 Java 子进程写入 PID..."
    sleep 4
    if [ -f "$BINANCE_SERVICE_DIR/binance-service.pid" ]; then
        JP=$(cat "$BINANCE_SERVICE_DIR/binance-service.pid" 2>/dev/null || true)
        if [ -n "$JP" ] && ps -p "$JP" > /dev/null 2>&1; then
            log_info "Java 进程运行中 (PID: $JP)"
        else
            log_warn "PID 文件存在但进程未就绪，请查看 startup.log / watchdog.log"
        fi
    else
        log_warn "尚未写入 binance-service.pid，请稍候查看 startup.log"
    fi
}

# 主函数
main() {
    log_info "============================================"
    log_info "Binance Service 构建和启动脚本"
    log_info "============================================"
    
    # 检查Java
    if ! check_java; then
        log_warn "Java未安装或版本过低，尝试安装..."
        install_jdk_maven
        if ! check_java; then
            log_error "Java安装失败或版本仍然不符合要求"
            exit 1
        fi
    fi
    
    # 检查Maven
    if ! check_maven; then
        log_warn "Maven未安装，尝试安装..."
        install_jdk_maven
        if ! check_maven; then
            log_error "Maven安装失败"
            exit 1
        fi
    fi
    
    # 构建JAR包
    # build_jar函数会将日志输出到stderr，只将文件路径输出到stdout
    # 使用临时文件来分离日志输出和返回值
    TEMP_OUTPUT=$(mktemp)
    if build_jar > "$TEMP_OUTPUT" 2>&1; then
        # 显示所有输出（包括日志）
        cat "$TEMP_OUTPUT"
        # 提取最后一行（JAR文件路径）
        JAR_FILE=$(tail -n 1 "$TEMP_OUTPUT")
        rm -f "$TEMP_OUTPUT"
    else
        # 显示错误输出
        cat "$TEMP_OUTPUT" >&2
        rm -f "$TEMP_OUTPUT"
        exit 1
    fi
    
    # 验证JAR文件路径是否有效
    if [ -z "$JAR_FILE" ] || [ ! -f "$JAR_FILE" ]; then
        log_error "JAR文件路径无效或文件不存在: $JAR_FILE"
        log_error "请检查构建日志以获取更多信息"
        exit 1
    fi
    log_info "确认JAR文件: $JAR_FILE"
    
    USE_WATCHDOG=false
    AUTO_START_ARG=false
    for arg in "$@"; do
        case "$arg" in
            --auto-start|-y) AUTO_START_ARG=true ;;
            --watchdog|-w) USE_WATCHDOG=true ;;
        esac
    done
    AUTO_START=${AUTO_START:-""}
    WATCHDOG=${WATCHDOG:-""}
    if [ "$WATCHDOG" = "true" ]; then
        USE_WATCHDOG=true
    fi
    if [ "$USE_WATCHDOG" = true ]; then
        AUTO_START_ARG=true
    fi
    
    # 检查是否在非交互模式或自动启动模式
    if [ "$AUTO_START_ARG" = true ] || [ "$AUTO_START" = "true" ]; then
        if [ "$USE_WATCHDOG" = true ]; then
            log_info "自动启动模式（守护进程）：Java 异常退出将自动重启"
            start_under_watchdog "$JAR_FILE"
        else
            log_info "自动启动模式：正在启动服务..."
            start_service "$JAR_FILE"
        fi
        
        log_info "============================================"
        log_info "构建和启动完成！"
        log_info "============================================"
        log_info "服务信息:"
        log_info "  - Java PID 文件: $BINANCE_SERVICE_DIR/binance-service.pid"
        if [ "$USE_WATCHDOG" = true ]; then
            log_info "  - 守护进程 PID 文件: $BINANCE_SERVICE_DIR/binance-service.watchdog.pid"
            log_info "  - 守护日志: $BINANCE_SERVICE_DIR/logs/watchdog.log"
        fi
        log_info "  - 启动日志: $BINANCE_SERVICE_DIR/logs/startup.log"
        log_info "  - 应用日志: $BINANCE_SERVICE_DIR/logs/binance-service.log"
        log_info ""
        log_info "常用命令:"
        log_info "  查看实时日志: tail -f $BINANCE_SERVICE_DIR/logs/binance-service.log"
        log_info "  查看启动日志: tail -f $BINANCE_SERVICE_DIR/logs/startup.log"
        if [ "$USE_WATCHDOG" = true ]; then
            log_info "  守护日志: tail -f $BINANCE_SERVICE_DIR/logs/watchdog.log"
        fi
        log_info "  停止服务: bash $SCRIPT_DIR/stop.sh"
        log_info "  检查 Java: ps -p \$(cat $BINANCE_SERVICE_DIR/binance-service.pid 2>/dev/null)"
    elif [ -t 0 ]; then
        # 交互模式：有终端输入
        echo
        read -p "是否立即启动服务? (y/n，默认y): " -n 1 -r
        echo
        # 如果用户直接按回车，默认启动
        if [[ -z "$REPLY" ]] || [[ $REPLY =~ ^[Yy]$ ]]; then
            read -p "是否在 Java 崩溃退出时自动重启（守护进程）? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                start_under_watchdog "$JAR_FILE"
            else
                start_service "$JAR_FILE"
            fi
            
            log_info "============================================"
            log_info "构建和启动完成！"
            log_info "============================================"
            log_info "服务信息:"
            log_info "  - Java PID 文件: $BINANCE_SERVICE_DIR/binance-service.pid"
            if [ -f "$BINANCE_SERVICE_DIR/binance-service.watchdog.pid" ]; then
                log_info "  - 守护进程 PID 文件: $BINANCE_SERVICE_DIR/binance-service.watchdog.pid"
                log_info "  - 守护日志: $BINANCE_SERVICE_DIR/logs/watchdog.log"
            fi
            log_info "  - 启动日志: $BINANCE_SERVICE_DIR/logs/startup.log"
            log_info "  - 应用日志: $BINANCE_SERVICE_DIR/logs/binance-service.log"
            log_info ""
            log_info "常用命令:"
            log_info "  查看实时日志: tail -f $BINANCE_SERVICE_DIR/logs/binance-service.log"
            log_info "  查看启动日志: tail -f $BINANCE_SERVICE_DIR/logs/startup.log"
            log_info "  停止服务: bash $SCRIPT_DIR/stop.sh"
            log_info "  检查 Java: ps -p \$(cat $BINANCE_SERVICE_DIR/binance-service.pid 2>/dev/null)"
            log_info ""
            
            # 询问是否查看实时日志
            read -p "是否查看实时应用日志? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                log_info "按 Ctrl+C 退出日志查看"
                tail -f "$BINANCE_SERVICE_DIR/logs/binance-service.log"
            fi
        else
            log_info "============================================"
            log_info "JAR包已构建完成"
            log_info "============================================"
            log_info "JAR文件: $JAR_FILE"
            log_info "手动启动命令:"
            log_info "  cd $BINANCE_SERVICE_DIR"
            log_info "  bash scripts/build-and-start.sh --watchdog -y   # 推荐：带自动重启"
            log_info "  或: java ... -jar $JAR_FILE"
            log_info "  注意: 所有配置从application.yml读取，可通过环境变量覆盖（如SERVER_PORT）"
        fi
    else
        log_info "============================================"
        log_info "JAR包已构建完成"
        log_info "============================================"
        log_info "JAR文件: $JAR_FILE"
        log_info "手动启动命令:"
        log_info "  bash $SCRIPT_DIR/build-and-start.sh --watchdog -y"
        log_info "  或: cd $BINANCE_SERVICE_DIR && java ... -jar $JAR_FILE"
        log_info "  注意: 所有配置从application.yml读取，可通过环境变量覆盖（如SERVER_PORT）"
    fi
}

# 执行主函数
main "$@"

