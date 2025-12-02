# ==============================================================================
# 前端服务 Dockerfile
# ==============================================================================
# 用途：构建 Node.js Express 前端服务镜像
# 构建上下文：项目根目录（通过 docker-compose.yml 配置）
# ==============================================================================

FROM node:18-slim

WORKDIR /app

# ==============================================================================
# 阶段1：安装依赖
# ==============================================================================
# 复制依赖文件和构建脚本（利用Docker缓存层）
COPY frontend/package.json frontend/package-lock.json* ./
COPY frontend/scripts/ scripts/

# 安装npm依赖（postinstall会自动执行资源同步脚本）
RUN if [ -f package-lock.json ]; then \
        npm ci; \
    else \
        npm install; \
    fi

# ==============================================================================
# 阶段2：复制应用代码
# ==============================================================================
# 复制前端应用代码和静态资源
COPY frontend/public/ public/
COPY frontend/server.js ./

# ==============================================================================
# 阶段3：准备静态资源
# ==============================================================================
# 复制项目根目录的static目录到临时位置（用于资源同步）
RUN mkdir -p /tmp/static 2>/dev/null || true
RUN if [ -d static ]; then cp -r static/* /tmp/static/ 2>/dev/null || true; fi

# 同步静态资源（从static/目录复制到public/目录）
# 如果public中已有文件，此步骤会更新它们
RUN npm run sync-static 2>&1 || echo "Static assets sync skipped (files may already exist)"

# 确保KLineChart库文件已复制到public/lib
# 如果postinstall失败，这里会重新执行
RUN npm run copy-assets || echo "KLineChart files will be served from node_modules"

# ==============================================================================
# 阶段4：暴露端口和启动服务
# ==============================================================================
EXPOSE 3000

# 启动前端服务器
CMD ["npm", "start"]
