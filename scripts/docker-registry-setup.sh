#!/bin/bash
# ==============================================================================
# Docker registry：镜像加速（daemon.json）+ 阿里云 ACR 登录
# ==============================================================================
# 使用：在仓库根目录执行
#   bash scripts/docker-registry-setup.sh
# 若需写入 /etc/docker，请：sudo bash scripts/docker-registry-setup.sh
#
# 凭据：在项目根目录 .env 中配置（已 gitignore）：
#   ALIYUN_CR_REGISTRY、DOCKER_REGISTRY_USERNAME、DOCKER_REGISTRY_PASSWORD
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DOCKER_REGISTRY_MIRROR="${DOCKER_REGISTRY_MIRROR:-https://crpi-hm3rgmmxwhz6m92m.cn-hongkong.personal.cr.aliyuncs.com}"
ALIYUN_CR_REGISTRY="${ALIYUN_CR_REGISTRY:-crpi-hm3rgmmxwhz6m92m.cn-hongkong.personal.cr.aliyuncs.com}"

if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$REPO_ROOT/.env"
  set +a
fi

echo "配置 Docker registry-mirrors..."

sudo mkdir -p /etc/docker

sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
  "registry-mirrors": [
    "${DOCKER_REGISTRY_MIRROR}"
  ]
}
EOF

echo "✓ 已写入 /etc/docker/daemon.json"

echo "重启 Docker 服务..."
sudo systemctl daemon-reload
sudo systemctl restart docker

echo "✓ Docker 已重启"
echo ""
echo "验证 Registry Mirrors："
docker info 2>/dev/null | grep -A 10 "Registry Mirrors" || true

docker_login_acr() {
  if [ -z "${DOCKER_REGISTRY_USERNAME:-}" ] || [ -z "${DOCKER_REGISTRY_PASSWORD:-}" ]; then
    echo ""
    echo "⚠ 跳过 docker login：请在 $REPO_ROOT/.env 中设置 DOCKER_REGISTRY_USERNAME / DOCKER_REGISTRY_PASSWORD"
    return 0
  fi
  echo ""
  echo "配置 ACR 登录（$ALIYUN_CR_REGISTRY）..."
  if [ -n "${SUDO_USER:-}" ]; then
    printf '%s\n' "$DOCKER_REGISTRY_PASSWORD" | sudo -u "$SUDO_USER" docker login "$ALIYUN_CR_REGISTRY" -u "$DOCKER_REGISTRY_USERNAME" --password-stdin
  else
    printf '%s\n' "$DOCKER_REGISTRY_PASSWORD" | docker login "$ALIYUN_CR_REGISTRY" -u "$DOCKER_REGISTRY_USERNAME" --password-stdin
  fi
  echo "✓ 已登录 $ALIYUN_CR_REGISTRY"
}

docker_login_acr
