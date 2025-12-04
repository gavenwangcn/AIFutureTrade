# ==============================================================================
# klinecharts-pro 构建 Dockerfile
# ==============================================================================
# 用途：构建自定义的 klinecharts-pro 库
# ==============================================================================

FROM node:18-slim

WORKDIR /app

# 配置 npm 镜像源
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN npm config set registry ${NPM_REGISTRY} && \
    npm config set fetch-retries 5 && \
    npm config set fetch-retry-mintimeout 20000 && \
    npm config set fetch-retry-maxtimeout 120000 && \
    npm config set fetch-timeout 300000

# 复制 package.json 和 package-lock.json
COPY package.json package-lock.json* ./

# 安装依赖
RUN if [ -f package-lock.json ]; then \
        npm ci --legacy-peer-deps || \
        (echo "[Dockerfile] npm ci failed, retrying with npm install..." && \
         rm -f package-lock.json && \
         npm install --legacy-peer-deps); \
    else \
        npm install --legacy-peer-deps; \
    fi

# 修复 node_modules/.bin 中的可执行文件权限（解决 Permission denied 问题）
RUN find node_modules/.bin -type f -exec chmod +x {} \; || true

# 复制源代码
COPY . .

# 构建 klinecharts-pro
RUN npm run build

# 验证构建结果
RUN if [ -d dist ]; then \
        echo "[Dockerfile] ✓ Build successful, dist directory exists"; \
        ls -la dist/; \
    else \
        echo "[Dockerfile] ✗ Build failed, dist directory not found"; \
        exit 1; \
    fi

# 暴露 dist 目录（通过 volume 挂载）
VOLUME ["/app/dist"]

