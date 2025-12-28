#!/bin/bash

# ============================================
# Async Service 构建和启动脚本
# ============================================
# 功能：
#   1. 检查并安装JDK 11和Maven（如果需要）
#   2. 使用mvn clean package构建JAR包
#   3. 使用java -jar方式启动服务
#
# 使用方法：
#   bash build-and-start.sh           # 交互模式，会询问是否启动
#   bash build-and-start.sh --auto-start  # 自动启动模式
#   bash build-and-start.sh -y        # 自动启动模式（简写）
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
PROJECT_ROOT="$(cd "$ASYNC_SERVICE_DIR/.." && pwd)"

log_info "Async Service目录: $ASYNC_SERVICE_DIR"
log_info "项目根目录: $PROJECT_ROOT"

# 检查Java是否已安装
check_java() {
    if command -v java &> /dev/null; then
        JAVA_VERSION=$(java -version 2>&1 | head -n 1 | cut -d'"' -f2 | sed '/^1\./s///' | cut -d'.' -f1)
        if [ "$JAVA_VERSION" -ge 11 ]; then
            log_info "Java已安装，版本: $(java -version 2>&1 | head -n 1)"
            return 0
        else
            log_warn "Java版本过低（需要11+），当前版本: $JAVA_VERSION"
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
    log_info "开始安装JDK 11和Maven..."
    
    INSTALL_SCRIPT="$PROJECT_ROOT/scripts/install-jdk11-maven.sh"
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
    log_info "开始构建Async Service JAR包..." >&2
    cd "$ASYNC_SERVICE_DIR"
    
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
    JAR_FILE="$ASYNC_SERVICE_DIR/target/async-service-1.0.0.jar"
    if [ ! -f "$JAR_FILE" ]; then
        log_error "JAR文件未找到: $JAR_FILE" >&2
        log_info "可用的文件:" >&2
        ls -lh "$ASYNC_SERVICE_DIR/target/" || true >&2
        exit 1
    fi
    
    # 显示JAR文件信息（输出到stderr，避免被捕获）
    JAR_SIZE=$(ls -lh "$JAR_FILE" | awk '{print $5}')
    log_info "JAR包构建成功: $JAR_FILE (大小: $JAR_SIZE)" >&2
    
    # 只输出文件路径到stdout，供调用者捕获
    echo "$JAR_FILE"
}

# 启动服务
start_service() {
    JAR_FILE="$1"
    
    if [ ! -f "$JAR_FILE" ]; then
        log_error "JAR文件不存在: $JAR_FILE"
        exit 1
    fi
    
    log_info "启动Async Service..."
    log_info "JAR文件: $JAR_FILE"
    log_info "所有配置从application.yml读取（可通过环境变量覆盖）"
    
    # 创建logs目录
    mkdir -p "$ASYNC_SERVICE_DIR/logs"
    
    # 设置JVM参数（高性能优化）
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
    log_info "Async Service 构建和启动脚本"
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
    TEMP_OUTPUT=$(mktemp)
    if build_jar > "$TEMP_OUTPUT" 2>&1; then
        cat "$TEMP_OUTPUT"
        JAR_FILE=$(tail -n 1 "$TEMP_OUTPUT")
        rm -f "$TEMP_OUTPUT"
    else
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
    
    # 检查是否在非交互模式或自动启动模式
    AUTO_START=${AUTO_START:-""}
    if [ "$1" = "--auto-start" ] || [ "$1" = "-y" ] || [ "$AUTO_START" = "true" ]; then
        # 自动启动模式
        log_info "自动启动模式：正在启动服务..."
        start_service "$JAR_FILE"
        
        log_info "============================================"
        log_info "构建和启动完成！"
        log_info "============================================"
        log_info "服务信息:"
        log_info "  - PID文件: $ASYNC_SERVICE_DIR/async-service.pid"
        log_info "  - 启动日志: $ASYNC_SERVICE_DIR/logs/startup.log"
        log_info "  - 应用日志: $ASYNC_SERVICE_DIR/logs/async-service.log"
        log_info ""
        log_info "常用命令:"
        log_info "  查看实时日志: tail -f $ASYNC_SERVICE_DIR/logs/async-service.log"
        log_info "  查看启动日志: tail -f $ASYNC_SERVICE_DIR/logs/startup.log"
        log_info "  停止服务: kill \$(cat $ASYNC_SERVICE_DIR/async-service.pid)"
        log_info "  检查服务状态: ps -p \$(cat $ASYNC_SERVICE_DIR/async-service.pid)"
    elif [ -t 0 ]; then
        # 交互模式：有终端输入
        echo
        read -p "是否立即启动服务? (y/n，默认y): " -n 1 -r
        echo
        if [[ -z "$REPLY" ]] || [[ $REPLY =~ ^[Yy]$ ]]; then
            start_service "$JAR_FILE"
            
            log_info "============================================"
            log_info "构建和启动完成！"
            log_info "============================================"
            log_info "服务信息:"
            log_info "  - PID文件: $ASYNC_SERVICE_DIR/async-service.pid"
            log_info "  - 启动日志: $ASYNC_SERVICE_DIR/logs/startup.log"
            log_info "  - 应用日志: $ASYNC_SERVICE_DIR/logs/async-service.log"
            log_info ""
            log_info "常用命令:"
            log_info "  查看实时日志: tail -f $ASYNC_SERVICE_DIR/logs/async-service.log"
            log_info "  查看启动日志: tail -f $ASYNC_SERVICE_DIR/logs/startup.log"
            log_info "  停止服务: kill \$(cat $ASYNC_SERVICE_DIR/async-service.pid)"
            log_info "  检查服务状态: ps -p \$(cat $ASYNC_SERVICE_DIR/async-service.pid)"
        else
            log_info "============================================"
            log_info "JAR包已构建完成"
            log_info "============================================"
            log_info "JAR文件: $JAR_FILE"
            log_info "手动启动命令:"
            log_info "  cd $ASYNC_SERVICE_DIR"
            log_info "  java -Xms1g -Xmx2g -XX:+UseG1GC -jar $JAR_FILE"
            log_info "  注意: 所有配置从application.yml读取，可通过环境变量覆盖"
        fi
    else
        log_info "============================================"
        log_info "JAR包已构建完成"
        log_info "============================================"
        log_info "JAR文件: $JAR_FILE"
        log_info "手动启动命令:"
        log_info "  cd $ASYNC_SERVICE_DIR"
        log_info "  java -Xms1g -Xmx2g -XX:+UseG1GC -jar $JAR_FILE"
        log_info "  注意: 所有配置从application.yml读取，可通过环境变量覆盖"
    fi
}

# 执行主函数
main "$@"

