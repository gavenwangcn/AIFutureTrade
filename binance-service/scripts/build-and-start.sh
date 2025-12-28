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
#   bash build-and-start.sh           # 交互模式，会询问是否启动
#   bash build-and-start.sh --auto-start  # 自动启动模式
#   bash build-and-start.sh -y        # 自动启动模式（简写）
#   AUTO_START=true bash build-and-start.sh  # 通过环境变量控制
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
    log_info "开始构建Binance Service JAR包..."
    cd "$BINANCE_SERVICE_DIR"
    
    log_info "执行Maven构建命令: mvn clean package -DskipTests"
    log_info "============================================"
    
    # 清理并构建，显示输出
    if mvn clean package -DskipTests; then
        log_info "============================================"
        log_info "Maven构建完成"
    else
        log_error "============================================"
        log_error "Maven构建失败"
        exit 1
    fi
    
    # 检查JAR文件是否存在
    JAR_FILE="$BINANCE_SERVICE_DIR/target/binance-service-1.0.0.jar"
    if [ ! -f "$JAR_FILE" ]; then
        log_error "JAR文件未找到: $JAR_FILE"
        log_info "可用的文件:"
        ls -lh "$BINANCE_SERVICE_DIR/target/" || true
        exit 1
    fi
    
    # 显示JAR文件信息
    JAR_SIZE=$(ls -lh "$JAR_FILE" | awk '{print $5}')
    log_info "JAR包构建成功: $JAR_FILE (大小: $JAR_SIZE)"
    echo "$JAR_FILE"
}

# 读取端口配置（从application.yml或环境变量）
read_server_port() {
    # 优先使用环境变量
    if [ -n "$SERVER_PORT" ]; then
        echo "$SERVER_PORT"
        return
    fi
    
    # 从application.yml读取
    # 匹配格式：port: ${SERVER_PORT:5004} 或 port: 5004
    local port=$(grep -E "^\s*port:" "$BINANCE_SERVICE_DIR/src/main/resources/application.yml" 2>/dev/null | sed 's/.*port:\s*\(.*\)/\1/' | sed 's/\${SERVER_PORT:\([^}]*\)}/\1/' | sed 's/://g' | tr -d ' ' | head -n 1)
    
    if [ -z "$port" ] || [ "$port" = "" ]; then
        # 如果都读取不到，返回空字符串，让调用者决定默认值
        echo ""
    else
        echo "$port"
    fi
}

# 启动服务
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
    
    # 读取端口配置
    SERVER_PORT=$(read_server_port)
    if [ -z "$SERVER_PORT" ] || [ "$SERVER_PORT" = "" ]; then
        log_warn "无法从配置文件或环境变量读取端口配置，请检查application.yml或设置SERVER_PORT环境变量"
        exit 1
    fi
    # 检查端口来源
    CONFIG_PORT=$(grep -E "^\s*port:" "$BINANCE_SERVICE_DIR/src/main/resources/application.yml" 2>/dev/null | sed 's/.*port:\s*\(.*\)/\1/' | sed 's/\${SERVER_PORT:\([^}]*\)}/\1/' | sed 's/://g' | tr -d ' ' | head -n 1)
    if [ -n "${SERVER_PORT}" ] && [ "$SERVER_PORT" != "$CONFIG_PORT" ]; then
        PORT_SOURCE="环境变量"
    else
        PORT_SOURCE="配置文件(application.yml)"
    fi
    log_info "使用服务端口: $SERVER_PORT (来源: $PORT_SOURCE)"
    
    # 设置JVM参数（高性能优化）
    # -Xms: 初始堆内存1G，-Xmx: 最大堆内存2G（允许动态调整以适应负载）
    # -XX:+UseG1GC: 使用G1垃圾收集器，适合大内存和低延迟场景
    # -XX:MaxGCPauseMillis: 最大GC暂停时间目标（毫秒）
    # -XX:+UseStringDeduplication: 字符串去重，减少内存占用
    # -XX:+OptimizeStringConcat: 优化字符串拼接
    # -XX:+UseCompressedOops: 使用压缩指针，节省内存
    # -XX:+UseCompressedClassPointers: 使用压缩类指针
    # -Djava.awt.headless=true: 无头模式，不需要图形界面
    # -Dfile.encoding=UTF-8: 文件编码
    JAVA_OPTS="-Xms1g -Xmx2g \
                -XX:+UseG1GC \
                -XX:MaxGCPauseMillis=200 \
                -XX:+UseStringDeduplication \
                -XX:+OptimizeStringConcat \
                -XX:+UseCompressedOops \
                -XX:+UseCompressedClassPointers \
                -Djava.awt.headless=true \
                -Dfile.encoding=UTF-8 \
                -Dserver.port=$SERVER_PORT"
    
    # 启动服务（后台运行）
    log_info "执行启动命令: java $JAVA_OPTS -jar $JAR_FILE"
    nohup java $JAVA_OPTS -jar "$JAR_FILE" > "$BINANCE_SERVICE_DIR/logs/startup.log" 2>&1 &
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
    JAR_FILE=$(build_jar)
    
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
        log_info "  - PID文件: $BINANCE_SERVICE_DIR/binance-service.pid"
        log_info "  - 启动日志: $BINANCE_SERVICE_DIR/logs/startup.log"
        log_info "  - 应用日志: $BINANCE_SERVICE_DIR/logs/binance-service.log"
        log_info ""
        log_info "常用命令:"
        log_info "  查看实时日志: tail -f $BINANCE_SERVICE_DIR/logs/binance-service.log"
        log_info "  查看启动日志: tail -f $BINANCE_SERVICE_DIR/logs/startup.log"
        log_info "  停止服务: kill \$(cat $BINANCE_SERVICE_DIR/binance-service.pid)"
        log_info "  检查服务状态: ps -p \$(cat $BINANCE_SERVICE_DIR/binance-service.pid)"
    elif [ -t 0 ]; then
        # 交互模式：有终端输入
        echo
        read -p "是否立即启动服务? (y/n，默认y): " -n 1 -r
        echo
        # 如果用户直接按回车，默认启动
        if [[ -z "$REPLY" ]] || [[ $REPLY =~ ^[Yy]$ ]]; then
            start_service "$JAR_FILE"
        
        log_info "============================================"
        log_info "构建和启动完成！"
        log_info "============================================"
        log_info "服务信息:"
        log_info "  - PID文件: $BINANCE_SERVICE_DIR/binance-service.pid"
        log_info "  - 启动日志: $BINANCE_SERVICE_DIR/logs/startup.log"
        log_info "  - 应用日志: $BINANCE_SERVICE_DIR/logs/binance-service.log"
        log_info ""
        log_info "常用命令:"
        log_info "  查看实时日志: tail -f $BINANCE_SERVICE_DIR/logs/binance-service.log"
        log_info "  查看启动日志: tail -f $BINANCE_SERVICE_DIR/logs/startup.log"
        log_info "  停止服务: kill \$(cat $BINANCE_SERVICE_DIR/binance-service.pid)"
        log_info "  检查服务状态: ps -p \$(cat $BINANCE_SERVICE_DIR/binance-service.pid)"
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
        # 读取端口配置用于显示
        MANUAL_SERVER_PORT=$(read_server_port)
        if [ -z "$MANUAL_SERVER_PORT" ] || [ "$MANUAL_SERVER_PORT" = "" ]; then
            log_warn "无法读取端口配置，请设置SERVER_PORT环境变量或检查application.yml"
            log_info "  示例: SERVER_PORT=<端口> java -Xms1g -Xmx2g -XX:+UseG1GC -jar $JAR_FILE"
        else
            log_info "  java -Xms1g -Xmx2g -XX:+UseG1GC -Dserver.port=$MANUAL_SERVER_PORT -jar $JAR_FILE"
        fi
    fi
}

# 执行主函数
main "$@"

