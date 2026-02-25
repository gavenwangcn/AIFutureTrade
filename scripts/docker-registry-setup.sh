#!/bin/bash
# ==============================================================================
# Docker 阿里云镜像加速器配置脚本
# ==============================================================================
# 使用方法：sudo bash docker-registry-setup.sh
# ==============================================================================

echo "配置 Docker 阿里云镜像加速器..."

# 创建 Docker 配置目录
sudo mkdir -p /etc/docker

# 配置阿里云镜像加速器
sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
  "registry-mirrors": [
    "https://registry.cn-hangzhou.aliyuncs.com",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
EOF

echo "✓ Docker 镜像加速器配置完成"

# 重启 Docker 服务
echo "重启 Docker 服务..."
sudo systemctl daemon-reload
sudo systemctl restart docker

echo "✓ Docker 服务已重启"
echo ""
echo "验证配置："
docker info | grep -A 10 "Registry Mirrors"

