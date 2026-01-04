#!/bin/bash
# Docker Compose 启动脚本
# 自动构建所有镜像，但 model-buy 和 model-sell 容器不启动（只构建镜像）

# 构建并启动所有服务，但 model-buy 和 model-sell 使用 scale=0 不启动容器
docker-compose up --build -d --scale model-buy=0 --scale model-sell=0 "$@"

