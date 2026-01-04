#!/bin/bash
# Docker Compose 启动脚本
# 自动构建所有镜像，但 model-buy 和 model-sell 容器不启动（只构建镜像）
#
# 用法：
#   ./docker-compose-up.sh           # 启动服务（不重新构建）
#   ./docker-compose-up.sh --build    # 启动服务并重新构建镜像
#   ./docker-compose-up.sh --build -d # 启动服务并重新构建镜像（后台运行，-d 已包含）

# 确定使用的命令（docker compose 或 docker-compose）
if docker compose version &> /dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi

# 检查是否已经包含 -d 参数
HAS_D_FLAG=false
for arg in "$@"; do
    if [ "$arg" = "-d" ] || [ "$arg" = "--detach" ]; then
        HAS_D_FLAG=true
        break
    fi
done

# 构建参数列表，确保包含 -d 和 --scale 参数
ARGS=("$@")
if [ "$HAS_D_FLAG" = false ]; then
    ARGS+=("-d")
fi
ARGS+=("--scale" "model-buy=0" "--scale" "model-sell=0")

# 构建并启动所有服务，但 model-buy 和 model-sell 使用 scale=0 不启动容器
$DOCKER_COMPOSE_CMD up "${ARGS[@]}"

