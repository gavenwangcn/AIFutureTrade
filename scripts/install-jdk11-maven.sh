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
        MVN_VERSION=$(mvn -version 2>&1 | head -n 1 | grep -oP 'Apache Maven \K[0-9]+\.[0-9]+\.[0-9]+')
        MVN_MAJOR=$(echo $MVN_VERSION | cut -d'.' -f1)
        MVN_MINOR=$(echo $MVN_VERSION | cut -d'.' -f2)
        
        if [ "$MVN_MAJOR" = "3" ] && [ "$MVN_MINOR" -ge 8 ] && [ "$MVN_MINOR" -lt 9 ]; then
            log_warn "Maven $MVN_VERSION 已安装，版本符合要求（3.8.x），跳过安装步骤"
            return
        else
            log_warn "检测到已安装 Maven 版本: $MVN_VERSION，将安装 Maven 3.8.8"
        fi
    fi
    
    # Maven 版本和下载 URL
    MAVEN_VERSION="3.8.8"
    MAVEN_DOWNLOAD_URL="https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz"
    MAVEN_INSTALL_DIR="/opt/maven"
    MAVEN_HOME_DIR="${MAVEN_INSTALL_DIR}/apache-maven-${MAVEN_VERSION}"
    
    # 创建安装目录
    mkdir -p $MAVEN_INSTALL_DIR
    
    # 下载 Maven
    log_info "下载 Maven ${MAVEN_VERSION}..."
    cd /tmp
    if [ -f "apache-maven-${MAVEN_VERSION}-bin.tar.gz" ]; then
        log_warn "Maven 安装包已存在，跳过下载"
    else
        wget -q $MAVEN_DOWNLOAD_URL -O apache-maven-${MAVEN_VERSION}-bin.tar.gz || {
            log_error "Maven 下载失败，尝试使用备用镜像..."
            # 尝试使用阿里云镜像
            MAVEN_DOWNLOAD_URL="https://mirrors.aliyun.com/apache/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz"
            wget -q $MAVEN_DOWNLOAD_URL -O apache-maven-${MAVEN_VERSION}-bin.tar.gz || {
                log_error "Maven 下载失败，请检查网络连接"
                exit 1
            }
        }
    fi
    
    # 解压 Maven
    log_info "解压 Maven..."
    tar -xzf apache-maven-${MAVEN_VERSION}-bin.tar.gz -C $MAVEN_INSTALL_DIR
    
    # 设置权限
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
    source $ENV_FILE
    
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
    log_info "3. 如果环境变量未生效，请运行: source /etc/profile.d/jdk11-maven.sh"
    log_info "4. 或者重新登录终端以加载环境变量"
    log_info "============================================"
}

# 执行主函数
main "$@"

