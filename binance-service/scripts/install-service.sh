#!/bin/bash

# ============================================
# Binance Service Systemd服务安装脚本
# ============================================
# 功能：
#   1. 检查并安装JDK 17和Maven（如果需要）
#   2. 构建JAR包
#   3. 安装systemd服务
#   4. 启用并启动服务
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

# 检查是否为 root 用户
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        log_error "请使用 root 用户或 sudo 权限运行此脚本"
        exit 1
    fi
}

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BINANCE_SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$BINANCE_SERVICE_DIR/.." && pwd)"
SERVICE_NAME="binance-service"
SERVICE_FILE="$SCRIPT_DIR/binance-service.service"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

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
    
    bash "$INSTALL_SCRIPT"
    
    # 重新加载环境变量
    if [ -f /etc/profile ]; then
        source /etc/profile
    fi
}

# 构建JAR包
build_jar() {
    log_info "开始构建Binance Service JAR包..."
    cd "$BINANCE_SERVICE_DIR"
    
    # 清理并构建
    mvn clean package -DskipTests
    
    # 检查JAR文件是否存在
    JAR_FILE="$BINANCE_SERVICE_DIR/target/binance-service-1.0.0.jar"
    if [ ! -f "$JAR_FILE" ]; then
        log_error "JAR文件未找到: $JAR_FILE"
        log_info "可用的文件:"
        ls -lh "$BINANCE_SERVICE_DIR/target/" || true
        exit 1
    fi
    
    log_info "JAR包构建成功: $JAR_FILE"
    echo "$JAR_FILE"
}

# 读取端口配置（从application.yml或环境变量）
read_server_port() {
    # 优先使用环境变量
    if [ -n "$SERVER_PORT" ]; then
        # 去除可能的注释和空格，只保留数字
        echo "$SERVER_PORT" | sed 's/#.*$//' | sed 's/[^0-9]//g'
        return
    fi
    
    # 从application.yml读取
    # 匹配格式：port: ${SERVER_PORT:5004} 或 port: 5004
    # 去除注释，只提取数字部分
    local port=$(grep -E "^\s*port:" "$BINANCE_SERVICE_DIR/src/main/resources/application.yml" 2>/dev/null | \
        sed 's/.*port:\s*\(.*\)/\1/' | \
        sed 's/#.*$//' | \
        sed 's/\${SERVER_PORT:\([^}]*\)}/\1/' | \
        sed 's/[^0-9]//g' | \
        head -n 1)
    
    if [ -z "$port" ] || [ "$port" = "" ]; then
        echo ""
    else
        echo "$port"
    fi
}

# 创建systemd服务文件
create_service_file() {
    log_info "创建systemd服务文件..."
    
    # 读取端口配置
    SERVER_PORT=$(read_server_port)
    if [ -z "$SERVER_PORT" ] || [ "$SERVER_PORT" = "" ]; then
        log_error "无法从配置文件或环境变量读取端口配置，请检查application.yml或设置SERVER_PORT环境变量"
        exit 1
    fi
    # 确保端口号是纯数字（去除任何可能的非数字字符）
    SERVER_PORT=$(echo "$SERVER_PORT" | sed 's/[^0-9]//g')
    # 检查端口来源
    CONFIG_PORT=$(grep -E "^\s*port:" "$BINANCE_SERVICE_DIR/src/main/resources/application.yml" 2>/dev/null | \
        sed 's/.*port:\s*\(.*\)/\1/' | \
        sed 's/#.*$//' | \
        sed 's/\${SERVER_PORT:\([^}]*\)}/\1/' | \
        sed 's/[^0-9]//g' | \
        head -n 1)
    if [ -n "${SERVER_PORT}" ] && [ "$SERVER_PORT" != "$CONFIG_PORT" ]; then
        PORT_SOURCE="环境变量"
    else
        PORT_SOURCE="配置文件(application.yml)"
    fi
    log_info "检测到服务端口: $SERVER_PORT (来源: $PORT_SOURCE)"
    
    # 获取Java路径
    JAVA_PATH=$(which java)
    if [ -z "$JAVA_PATH" ]; then
        log_error "无法找到Java可执行文件"
        exit 1
    fi
    
    # 检查模板文件是否存在
    SERVICE_TEMPLATE="$SCRIPT_DIR/binance-service.service"
    if [ ! -f "$SERVICE_TEMPLATE" ]; then
        log_error "服务模板文件不存在: $SERVICE_TEMPLATE"
        exit 1
    fi
    
    # 从模板文件创建服务文件，替换占位符
    sed -e "s|%BINANCE_SERVICE_DIR%|$BINANCE_SERVICE_DIR|g" \
        -e "s|%JAVA_PATH%|$JAVA_PATH|g" \
        -e "s|%SERVER_PORT%|$SERVER_PORT|g" \
        "$SERVICE_TEMPLATE" > "$SERVICE_FILE"
    
    log_info "服务文件已创建: $SERVICE_FILE"
}

# 安装systemd服务
install_service() {
    log_info "安装systemd服务..."
    
    # 创建logs目录
    mkdir -p "$BINANCE_SERVICE_DIR/logs"
    
    # 复制服务文件到systemd目录
    cp "$SERVICE_FILE" "$SYSTEMD_SERVICE_FILE"
    log_info "服务文件已复制到: $SYSTEMD_SERVICE_FILE"
    
    # 重新加载systemd
    systemctl daemon-reload
    log_info "systemd已重新加载"
    
    # 启用服务（开机自启）
    systemctl enable "$SERVICE_NAME"
    log_info "服务已设置为开机自启"
    
    # 启动服务
    systemctl start "$SERVICE_NAME"
    log_info "服务已启动"
    
    # 等待几秒检查服务状态
    sleep 3
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "服务运行正常"
        systemctl status "$SERVICE_NAME" --no-pager
    else
        log_error "服务启动失败，请查看日志:"
        log_error "  journalctl -u $SERVICE_NAME -n 50"
        log_error "  $BINANCE_SERVICE_DIR/logs/service-error.log"
        exit 1
    fi
}

# 主函数
main() {
    log_info "============================================"
    log_info "Binance Service Systemd服务安装脚本"
    log_info "============================================"
    
    # 检查root权限
    check_root
    
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
    
    # 创建服务文件
    create_service_file
    
    # 安装服务
    install_service
    
    log_info "============================================"
    log_info "服务安装完成！"
    log_info "============================================"
    log_info "服务名称: $SERVICE_NAME"
    log_info "查看状态: systemctl status $SERVICE_NAME"
    log_info "查看日志: journalctl -u $SERVICE_NAME -f"
    log_info "停止服务: systemctl stop $SERVICE_NAME"
    log_info "启动服务: systemctl start $SERVICE_NAME"
    log_info "重启服务: systemctl restart $SERVICE_NAME"
    log_info "禁用自启: systemctl disable $SERVICE_NAME"
}

# 执行主函数
main "$@"

