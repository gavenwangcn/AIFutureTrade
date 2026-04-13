#!/bin/bash
# ==============================================================================
# Docker registry 镜像加速（daemon.json 示例）
# ==============================================================================
# 使用：sudo bash scripts/docker-registry-setup.sh
#
# 说明：不再包含 registry.cn-hangzhou.aliyuncs.com（该地址不适合作为 Docker Hub 加速器）。
# 若需阿里云加速，请在控制台「容器镜像服务 → 镜像加速器」复制专属地址（*.mirror.aliyuncs.com）
# 再自行写入 registry-mirrors。下方 USTC/163 可能已失效，请按实际网络替换或删除。
# ==============================================================================

echo "配置 Docker registry-mirrors..."

sudo mkdir -p /etc/docker

sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
EOF

echo "✓ 已写入 /etc/docker/daemon.json"

echo "重启 Docker 服务..."
sudo systemctl daemon-reload
sudo systemctl restart docker

echo "✓ Docker 已重启"
echo ""
echo "验证："
docker info | grep -A 10 "Registry Mirrors"
