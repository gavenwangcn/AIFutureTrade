#!/bin/bash

# ============================================
# JDK 11 (OpenJDK) 和 Maven 3.8.x 安装脚本
# ============================================
# 功能：
#   1. 安装 OpenJDK 11
#   2. 安装 Maven 3.8.x (小于3.9版本)
#   3. 配置环境变量
#   4. 验证安装
# ============================================

# 确保使用 bash 执行此脚本
if [ -z "$BASH_VERSION" ]; then
    echo "错误: 此脚本需要使用 bash 执行"
    echo "请使用: bash $0"
    echo "或者: chmod +x $0 && ./$0"
    exit 1
fi

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

# 检测操作系统类型
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    elif type lsb_release >/dev/null 2>&1; then
        OS=$(lsb_release -si | tr '[:upper:]' '[:lower:]')
    elif [ -f /etc/lsb-release ]; then
        . /etc/lsb-release
        OS=$DISTRIB_ID
    elif [ -f /etc/debian_version ]; then
        OS=debian
    elif [ -f /etc/redhat-release ]; then
        OS=rhel
    else
        log_error "无法检测操作系统类型"
        exit 1
    fi
    
    log_info "检测到操作系统: $OS $OS_VERSION"
}

# 安装下载工具（wget 或 curl）
install_download_tool() {
    log_info "检查下载工具..."
    
    if command -v wget &> /dev/null; then
        DOWNLOAD_TOOL="wget"
        log_info "已找到 wget"
        return 0
    elif command -v curl &> /dev/null; then
        DOWNLOAD_TOOL="curl"
        log_info "已找到 curl"
        return 0
    else
        log_info "未找到下载工具，正在安装 wget..."
        
        # 如果 OS 变量未设置，尝试检测
        if [ -z "$OS" ]; then
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                OS=$ID
            fi
        fi
        
        case $OS in
            ubuntu|debian)
                apt-get update -qq
                apt-get install -y wget
                ;;
            centos|rhel|fedora|rocky|almalinux)
                if command -v dnf &> /dev/null; then
                    dnf install -y wget
                else
                    yum install -y wget
                fi
                ;;
            *)
                log_warn "未知的操作系统，尝试使用通用方法安装 wget..."
                # 尝试使用包管理器
                if command -v apt-get &> /dev/null; then
                    apt-get update -qq && apt-get install -y wget
                elif command -v dnf &> /dev/null; then
                    dnf install -y wget
                elif command -v yum &> /dev/null; then
                    yum install -y wget
                else
                    log_error "无法确定包管理器，请手动安装 wget 或 curl"
                    return 1
                fi
                ;;
        esac
        
        if command -v wget &> /dev/null; then
            DOWNLOAD_TOOL="wget"
            log_info "wget 安装成功"
            return 0
        else
            log_error "无法安装下载工具，请手动安装 wget 或 curl"
            return 1
        fi
    fi
}

# 下载文件函数（支持 wget 和 curl，带超时和重试）
download_file() {
    local url=$1
    local output=$2
    local max_retries=3
    local retry_count=0
    local timeout=300  # 5分钟超时
    
    while [ $retry_count -lt $max_retries ]; do
        log_info "正在下载... (尝试 $((retry_count + 1))/$max_retries)"
        log_info "URL: $url"
        
        if [ "$DOWNLOAD_TOOL" = "wget" ]; then
            # 使用 wget 下载，显示进度条
            if wget --timeout=$timeout --tries=1 --progress=bar:force \
                "$url" -O "$output" 2>&1; then
                # 检查文件是否存在且大小大于0
                if [ -f "$output" ] && [ -s "$output" ]; then
                    log_info "下载完成"
                    return 0
                else
                    log_warn "下载的文件为空或不存在"
                fi
            else
                log_warn "wget 下载命令执行失败"
            fi
        elif [ "$DOWNLOAD_TOOL" = "curl" ]; then
            # 使用 curl 下载，显示进度条
            if curl -L --connect-timeout 30 --max-time $timeout --progress-bar \
                "$url" -o "$output"; then
                if [ -f "$output" ] && [ -s "$output" ]; then
                    log_info "下载完成"
                    return 0
                else
                    log_warn "下载的文件为空或不存在"
                fi
            else
                log_warn "curl 下载命令执行失败"
            fi
        else
            log_error "未知的下载工具: $DOWNLOAD_TOOL"
            return 1
        fi
        
        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            log_warn "下载失败，3秒后重试..."
            sleep 3
            rm -f "$output"  # 删除不完整的文件
        fi
    done
    
    log_error "下载失败，已重试 $max_retries 次"
    return 1
}

# 安装 OpenJDK 11
install_openjdk11() {
    log_info "开始安装 OpenJDK 11..."
    
    if command -v java &> /dev/null; then
        JAVA_VERSION=$(java -version 2>&1 | head -n 1 | cut -d'"' -f2 | sed '/^1\./s///' | cut -d'.' -f1)
        if [ "$JAVA_VERSION" = "11" ]; then
            log_warn "OpenJDK 11 已安装，跳过安装步骤"
            return
        else
            log_warn "检测到已安装 Java 版本: $JAVA_VERSION，将安装 OpenJDK 11"
        fi
    fi
    
    case $OS in
        ubuntu|debian)
            log_info "使用 apt 安装 OpenJDK 11..."
            apt-get update -qq
            apt-get install -y openjdk-11-jdk
            ;;
        centos|rhel|fedora|rocky|almalinux)
            log_info "使用 yum/dnf 安装 OpenJDK 11..."
            if command -v dnf &> /dev/null; then
                dnf install -y java-11-openjdk java-11-openjdk-devel
            else
                yum install -y java-11-openjdk java-11-openjdk-devel
            fi
            ;;
        *)
            log_error "不支持的操作系统: $OS"
            exit 1
            ;;
    esac
    
    log_info "OpenJDK 11 安装完成"
}

# 安装 Maven 3.8.x
install_maven() {
    log_info "开始安装 Maven 3.8.8..."
    
    # 检查 Maven 是否已安装
    if command -v mvn &> /dev/null; then
        MVN_VERSION=$(mvn -version 2>&1 | head -n 1 | grep -oP 'Apache Maven \K[0-9]+\.[0-9]+\.[0-9]+' || echo "")
        if [ -n "$MVN_VERSION" ]; then
            MVN_MAJOR=$(echo $MVN_VERSION | cut -d'.' -f1)
            MVN_MINOR=$(echo $MVN_VERSION | cut -d'.' -f2)
            
            if [ "$MVN_MAJOR" = "3" ] && [ "$MVN_MINOR" -ge 8 ] && [ "$MVN_MINOR" -lt 9 ]; then
                log_warn "Maven $MVN_VERSION 已安装，版本符合要求（3.8.x），跳过安装步骤"
                return
            else
                log_warn "检测到已安装 Maven 版本: $MVN_VERSION，将安装 Maven 3.8.8"
            fi
        fi
    fi
    
    # 确保下载工具已安装
    if ! install_download_tool; then
        log_error "无法安装下载工具，Maven 安装失败"
        exit 1
    fi
    
    # Maven 版本和下载 URL
    MAVEN_VERSION="3.8.8"
    MAVEN_DOWNLOAD_URL="https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz"
    MAVEN_MIRROR_URL="https://mirrors.aliyun.com/apache/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz"
    MAVEN_INSTALL_DIR="/opt/maven"
    MAVEN_HOME_DIR="${MAVEN_INSTALL_DIR}/apache-maven-${MAVEN_VERSION}"
    DOWNLOAD_FILE="/tmp/apache-maven-${MAVEN_VERSION}-bin.tar.gz"
    
    # 创建安装目录
    mkdir -p $MAVEN_INSTALL_DIR
    
    # 检查文件是否已存在且完整
    if [ -f "$DOWNLOAD_FILE" ] && [ -s "$DOWNLOAD_FILE" ]; then
        log_info "检测到已存在的 Maven 安装包，验证完整性..."
        # 简单验证：检查文件大小（Maven 3.8.8 大约 9-10MB）
        FILE_SIZE=$(stat -f%z "$DOWNLOAD_FILE" 2>/dev/null || stat -c%s "$DOWNLOAD_FILE" 2>/dev/null || echo "0")
        if [ "$FILE_SIZE" -gt 5000000 ]; then  # 大于 5MB 认为可能是完整的
            log_warn "使用已存在的安装包"
        else
            log_warn "已存在的文件可能不完整，将重新下载"
            rm -f "$DOWNLOAD_FILE"
        fi
    fi
    
    # 下载 Maven
    if [ ! -f "$DOWNLOAD_FILE" ] || [ ! -s "$DOWNLOAD_FILE" ]; then
        log_info "从 Apache 官方镜像下载 Maven ${MAVEN_VERSION}..."
        if ! download_file "$MAVEN_DOWNLOAD_URL" "$DOWNLOAD_FILE"; then
            log_warn "Apache 官方镜像下载失败，尝试使用阿里云镜像..."
            if ! download_file "$MAVEN_MIRROR_URL" "$DOWNLOAD_FILE"; then
                log_error "Maven 下载失败，请检查网络连接或手动下载"
                log_error "下载地址: $MAVEN_DOWNLOAD_URL"
                log_error "或: $MAVEN_MIRROR_URL"
                exit 1
            fi
        fi
    fi
    
    # 验证下载的文件
    if [ ! -f "$DOWNLOAD_FILE" ] || [ ! -s "$DOWNLOAD_FILE" ]; then
        log_error "下载的文件不存在或为空"
        exit 1
    fi
    
    # 解压 Maven
    log_info "解压 Maven 到 $MAVEN_INSTALL_DIR..."
    if ! tar -xzf "$DOWNLOAD_FILE" -C $MAVEN_INSTALL_DIR; then
        log_error "Maven 解压失败，可能文件损坏"
        log_error "请删除 $DOWNLOAD_FILE 后重新运行脚本"
        exit 1
    fi
    
    # 验证解压结果
    if [ ! -d "$MAVEN_HOME_DIR" ]; then
        log_error "Maven 解压后目录不存在: $MAVEN_HOME_DIR"
        exit 1
    fi
    
    # 设置权限
    log_info "设置 Maven 目录权限..."
    chown -R root:root $MAVEN_HOME_DIR
    chmod -R 755 $MAVEN_HOME_DIR
    
    log_info "Maven ${MAVEN_VERSION} 安装完成"
}

# 配置环境变量
configure_environment() {
    log_info "配置环境变量..."
    
    # 查找 Java 安装路径
    if [ -d /usr/lib/jvm/java-11-openjdk-* ]; then
        JAVA_HOME=$(ls -d /usr/lib/jvm/java-11-openjdk-* | head -n 1)
    elif [ -d /usr/lib/jvm/java-11 ]; then
        JAVA_HOME=/usr/lib/jvm/java-11
    else
        # 尝试使用 update-alternatives 查找
        JAVA_HOME=$(update-alternatives --list java 2>/dev/null | sed 's|/bin/java||' | head -n 1)
        if [ -z "$JAVA_HOME" ]; then
            log_error "无法找到 Java 安装路径"
            exit 1
        fi
    fi
    
    # Maven 安装路径
    MAVEN_VERSION="3.8.8"
    MAVEN_HOME="/opt/maven/apache-maven-${MAVEN_VERSION}"
    
    log_info "JAVA_HOME: $JAVA_HOME"
    log_info "MAVEN_HOME: $MAVEN_HOME"
    
    # 创建环境变量配置文件
    ENV_FILE="/etc/profile.d/jdk11-maven.sh"
    
    cat > $ENV_FILE <<EOF
# JDK 11 和 Maven 3.8.8 环境变量配置
# 由 install-jdk11-maven.sh 脚本自动生成

export JAVA_HOME=${JAVA_HOME}
export MAVEN_HOME=${MAVEN_HOME}
export PATH=\$JAVA_HOME/bin:\$MAVEN_HOME/bin:\$PATH

# 可选：配置 Maven 使用阿里云镜像（加速依赖下载）
export MAVEN_OPTS="-Xms512m -Xmx1024m"
EOF
    
    # 使环境变量立即生效（当前会话）
    # 使用 . 代替 source 以兼容 sh
    . $ENV_FILE
    
    log_info "环境变量已配置到: $ENV_FILE"
    log_info "新开终端会话将自动加载环境变量"
    log_info "当前会话已加载环境变量"
}

# 配置 Maven 使用阿里云镜像（可选，但推荐）
configure_maven_mirror() {
    log_info "配置 Maven 使用阿里云镜像（加速依赖下载）..."
    
    MAVEN_VERSION="3.8.8"
    MAVEN_SETTINGS_DIR="/opt/maven/apache-maven-${MAVEN_VERSION}/conf"
    MAVEN_SETTINGS_FILE="${MAVEN_SETTINGS_DIR}/settings.xml"
    
    # 备份原始 settings.xml
    if [ -f "$MAVEN_SETTINGS_FILE" ]; then
        cp "$MAVEN_SETTINGS_FILE" "${MAVEN_SETTINGS_FILE}.backup"
    fi
    
    # 创建或更新 settings.xml
    cat > "$MAVEN_SETTINGS_FILE" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0
          http://maven.apache.org/xsd/settings-1.0.0.xsd">
  <mirrors>
    <mirror>
      <id>aliyunmaven</id>
      <mirrorOf>central</mirrorOf>
      <name>阿里云公共仓库</name>
      <url>https://maven.aliyun.com/repository/public</url>
    </mirror>
  </mirrors>
</settings>
EOF
    
    log_info "Maven 镜像配置完成"
}

# 验证安装
verify_installation() {
    log_info "验证安装..."
    
    # 验证 Java
    if command -v java &> /dev/null; then
        log_info "Java 安装验证:"
        java -version
        JAVA_VERSION=$(java -version 2>&1 | head -n 1 | cut -d'"' -f2 | sed '/^1\./s///' | cut -d'.' -f1)
        if [ "$JAVA_VERSION" = "11" ]; then
            log_info "✓ Java 11 安装成功"
        else
            log_warn "Java 版本为 $JAVA_VERSION，不是 11"
        fi
    else
        log_error "Java 未正确安装"
        exit 1
    fi
    
    # 验证 Maven
    if command -v mvn &> /dev/null; then
        log_info "Maven 安装验证:"
        mvn -version
        MVN_VERSION=$(mvn -version 2>&1 | head -n 1 | grep -oP 'Apache Maven \K[0-9]+\.[0-9]+\.[0-9]+')
        MVN_MAJOR=$(echo $MVN_VERSION | cut -d'.' -f1)
        MVN_MINOR=$(echo $MVN_VERSION | cut -d'.' -f2)
        
        if [ "$MVN_MAJOR" = "3" ] && [ "$MVN_MINOR" -ge 8 ] && [ "$MVN_MINOR" -lt 9 ]; then
            log_info "✓ Maven $MVN_VERSION 安装成功（版本符合要求：3.8.x）"
        else
            log_warn "Maven 版本为 $MVN_VERSION，不在要求的 3.8.x 范围内"
        fi
    else
        log_error "Maven 未正确安装"
        exit 1
    fi
    
    # 验证环境变量
    log_info "环境变量验证:"
    log_info "JAVA_HOME: $JAVA_HOME"
    log_info "MAVEN_HOME: $MAVEN_HOME"
    
    if [ -z "$JAVA_HOME" ] || [ -z "$MAVEN_HOME" ]; then
        log_error "环境变量未正确设置"
        exit 1
    fi
    
    log_info "✓ 所有验证通过！"
}

# 主函数
main() {
    log_info "============================================"
    log_info "JDK 11 和 Maven 3.8.x 安装脚本"
    log_info "============================================"
    
    check_root
    detect_os
    install_openjdk11
    install_maven
    configure_environment
    configure_maven_mirror
    verify_installation
    
    log_info "============================================"
    log_info "安装完成！"
    log_info "============================================"
    log_info "使用说明："
    log_info "1. 运行 'java -version' 验证 Java 安装"
    log_info "2. 运行 'mvn -version' 验证 Maven 安装"
    log_info "3. 如果环境变量未生效，请运行: . /etc/profile.d/jdk11-maven.sh 或 source /etc/profile.d/jdk11-maven.sh"
    log_info "4. 或者重新登录终端以加载环境变量"
    log_info "============================================"
}

# 执行主函数
main "$@"

