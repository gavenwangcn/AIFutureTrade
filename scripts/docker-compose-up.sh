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

# 检查是否包含 --build 参数
HAS_BUILD_FLAG=false
for arg in "$@"; do
    if [ "$arg" = "--build" ] || [ "$arg" = "-b" ]; then
        HAS_BUILD_FLAG=true
        break
    fi
done

# 检查镜像是否存在
check_image_exists() {
    local image_name=$1
    docker images --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | grep -q "^${image_name}$"
}

# 如果指定了 --build 参数，或者镜像不存在，先构建 model-buy 和 model-sell 镜像（避免拉取警告）
if [ "$HAS_BUILD_FLAG" = true ]; then
    echo "检测到 --build 参数，将重新构建所有镜像..."
    # 如果指定了 --build，让 docker-compose up --build 处理所有镜像的构建
    # 这里只构建 model-buy 和 model-sell，避免拉取警告
    echo "构建 model-buy 镜像..."
    $DOCKER_COMPOSE_CMD build model-buy 2>/dev/null || true
    echo "构建 model-sell 镜像..."
    $DOCKER_COMPOSE_CMD build model-sell 2>/dev/null || true
elif ! check_image_exists "aifuturetrade-model-buy:latest"; then
    echo "构建 model-buy 镜像（镜像不存在，避免拉取警告）..."
    $DOCKER_COMPOSE_CMD build model-buy 2>/dev/null || true
fi

if [ "$HAS_BUILD_FLAG" != true ] && ! check_image_exists "aifuturetrade-model-sell:latest"; then
    echo "构建 model-sell 镜像（镜像不存在，避免拉取警告）..."
    $DOCKER_COMPOSE_CMD build model-sell 2>/dev/null || true
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
# 执行命令，忽略 pull access denied 警告（这些只是警告，不影响功能）
$DOCKER_COMPOSE_CMD up "${ARGS[@]}" 2>&1 | sed '/pull access denied/d' | sed '/repository does not exist/d' || {
    # 如果命令失败，检查是否是真正的错误还是只是警告
    # 重新运行一次，但这次显示完整输出
    exit_code=${PIPESTATUS[0]}
    if [ $exit_code -ne 0 ]; then
        echo "启动服务时出现错误，显示完整输出："
        $DOCKER_COMPOSE_CMD up "${ARGS[@]}"
        exit $exit_code
    fi
}
