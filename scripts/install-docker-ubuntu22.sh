#!/bin/bash
# ==============================================================================
# Docker 安装脚本 - Ubuntu 22.04
# ==============================================================================
# 用途：在 Ubuntu 22.04 系统上安装 Docker Engine 和 Docker Compose
# 说明：此脚本会自动检测系统版本，安装最新版本的 Docker
# ==============================================================================

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
        log_error "请使用 sudo 运行此脚本"
        exit 1
    fi
}

# 检查系统版本
check_os_version() {
    log_info "检查系统版本..."
    
    if [ ! -f /etc/os-release ]; then
        log_error "无法检测操作系统版本"
        exit 1
    fi
    
    . /etc/os-release
    
    if [ "$ID" != "ubuntu" ]; then
        log_error "此脚本仅支持 Ubuntu 系统"
        exit 1
    fi
    
    if [ "$VERSION_ID" != "22.04" ]; then
        log_warn "检测到 Ubuntu 版本: $VERSION_ID"
        log_warn "此脚本针对 Ubuntu 22.04 优化，其他版本可能不兼容"
        read -p "是否继续安装? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    log_info "系统版本: Ubuntu $VERSION_ID"
}

# 更新系统包
update_system() {
    log_info "更新系统包列表..."
    apt-get update -qq
    
    log_info "升级系统包..."
    apt-get upgrade -y -qq
}

# 卸载旧版本的 Docker
remove_old_docker() {
    log_info "检查并卸载旧版本的 Docker..."
    
    if command -v docker &> /dev/null; then
        log_warn "检测到已安装的 Docker，将卸载旧版本..."
        apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true
    fi
}

# 安装必要的依赖
install_dependencies() {
    log_info "安装必要的依赖包..."
    apt-get install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        apt-transport-https \
        software-properties-common
}

# 添加 Docker 官方 GPG 密钥
add_docker_gpg_key() {
    log_info "添加 Docker 官方 GPG 密钥..."
    
    # 创建密钥目录
    install -m 0755 -d /etc/apt/keyrings
    
    # 下载并添加 GPG 密钥
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    # 设置正确的权限
    chmod a+r /etc/apt/keyrings/docker.gpg
}

# 添加 Docker 仓库
add_docker_repository() {
    log_info "添加 Docker 官方仓库..."
    
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" | \
        tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # 更新包列表
    apt-get update -qq
}

# 安装 Docker Engine
install_docker_engine() {
    log_info "安装 Docker Engine..."
    
    apt-get install -y \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin
    
    log_info "Docker Engine 安装完成"
}

# 安装 Docker Compose (独立版本，作为备用)
install_docker_compose_standalone() {
    log_info "安装 Docker Compose (独立版本)..."
    
    # 检查是否已安装 docker-compose-plugin (新版本)
    if docker compose version &> /dev/null; then
        log_info "Docker Compose Plugin 已安装"
        return
    fi
    
    # 下载 Docker Compose 独立版本
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d\" -f4)
    if [ -z "$DOCKER_COMPOSE_VERSION" ]; then
        DOCKER_COMPOSE_VERSION="v2.24.0"  # 备用版本
    fi
    
    log_info "下载 Docker Compose $DOCKER_COMPOSE_VERSION..."
    curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/bin/docker-compose
    
    chmod +x /usr/local/bin/docker-compose
    
    # 创建符号链接（如果需要）
    if [ ! -f /usr/bin/docker-compose ]; then
        ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
    fi
    
    log_info "Docker Compose 安装完成"
}

# 启动 Docker 服务
start_docker_service() {
    log_info "启动 Docker 服务..."
    
    systemctl enable docker
    systemctl start docker
    
    log_info "Docker 服务已启动并设置为开机自启"
}

# 配置 Docker（可选）
configure_docker() {
    log_info "配置 Docker..."
    
    # 创建 Docker 配置目录
    mkdir -p /etc/docker
    
    # 配置 Docker daemon（如果需要）
    if [ ! -f /etc/docker/daemon.json ]; then
        cat > /etc/docker/daemon.json <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
EOF
        log_info "Docker daemon 配置文件已创建"
    fi
    
    # 重启 Docker 服务以应用配置
    systemctl restart docker
}

# 将当前用户添加到 docker 组
add_user_to_docker_group() {
    if [ -n "$SUDO_USER" ]; then
        log_info "将用户 $SUDO_USER 添加到 docker 组..."
        usermod -aG docker "$SUDO_USER"
        log_info "用户 $SUDO_USER 已添加到 docker 组"
        log_warn "请重新登录或运行 'newgrp docker' 以使更改生效"
    else
        log_warn "无法确定当前用户，请手动运行: sudo usermod -aG docker \$USER"
    fi
}

# 验证安装
verify_installation() {
    log_info "验证 Docker 安装..."
    
    # 检查 Docker 版本
    if command -v docker &> /dev/null; then
        DOCKER_VERSION=$(docker --version)
        log_info "Docker 版本: $DOCKER_VERSION"
    else
        log_error "Docker 未正确安装"
        exit 1
    fi
    
    # 检查 Docker Compose 版本
    if docker compose version &> /dev/null 2>&1; then
        DOCKER_COMPOSE_VERSION=$(docker compose version)
        log_info "Docker Compose 版本: $DOCKER_COMPOSE_VERSION"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_VERSION=$(docker-compose --version)
        log_info "Docker Compose 版本: $DOCKER_COMPOSE_VERSION"
    else
        log_error "Docker Compose 未正确安装"
        exit 1
    fi
    
    # 测试 Docker 是否正常运行
    log_info "测试 Docker 是否正常运行..."
    if docker run --rm hello-world &> /dev/null; then
        log_info "Docker 测试成功！"
    else
        log_error "Docker 测试失败"
        exit 1
    fi
}

# 显示安装信息
show_installation_info() {
    echo ""
    log_info "=========================================="
    log_info "Docker 安装完成！"
    log_info "=========================================="
    echo ""
    log_info "Docker 版本信息:"
    docker --version
    echo ""
    
    if docker compose version &> /dev/null 2>&1; then
        log_info "Docker Compose 版本信息:"
        docker compose version
    elif command -v docker-compose &> /dev/null; then
        log_info "Docker Compose 版本信息:"
        docker-compose --version
    fi
    echo ""
    
    log_info "Docker 服务状态:"
    systemctl status docker --no-pager -l | head -n 5
    echo ""
    
    if [ -n "$SUDO_USER" ]; then
        log_warn "重要提示:"
        log_warn "1. 用户 $SUDO_USER 已添加到 docker 组"
        log_warn "2. 请重新登录或运行 'newgrp docker' 以使更改生效"
        log_warn "3. 之后可以无需 sudo 运行 docker 命令"
    fi
    echo ""
    
    log_info "常用命令:"
    log_info "  - 查看 Docker 版本: docker --version"
    log_info "  - 查看 Docker Compose 版本: docker compose version"
    log_info "  - 查看运行中的容器: docker ps"
    log_info "  - 查看所有容器: docker ps -a"
    log_info "  - 查看 Docker 信息: docker info"
    echo ""
}

# 主函数
main() {
    log_info "=========================================="
    log_info "开始安装 Docker (Ubuntu 22.04)"
    log_info "=========================================="
    echo ""
    
    check_root
    check_os_version
    echo ""
    
    update_system
    echo ""
    
    remove_old_docker
    echo ""
    
    install_dependencies
    echo ""
    
    add_docker_gpg_key
    echo ""
    
    add_docker_repository
    echo ""
    
    install_docker_engine
    echo ""
    
    install_docker_compose_standalone
    echo ""
    
    start_docker_service
    echo ""
    
    configure_docker
    echo ""
    
    add_user_to_docker_group
    echo ""
    
    verify_installation
    echo ""
    
    show_installation_info
}

# 执行主函数
main

