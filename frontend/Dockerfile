# ==============================================================================
# Frontend Dockerfile
# ==============================================================================
# Build KLineChart 10.0.0 and the Vite app in one image.
# Context: repository root.
#
# If pulls from docker.io fail (e.g. insufficient_scope / China network), set base
# images via build args or in docker-compose.yml / .env — see scripts/README-docker-install.md
# ==============================================================================

ARG NODE_IMAGE=node:22-bookworm-slim
ARG NGINX_IMAGE=nginx:alpine

# ==============================================================================
# Stage 1: build KLineChart 10.0.0
# ==============================================================================

FROM ${NODE_IMAGE} AS klinecharts-builder
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 pnpm（KLineChart 使用 pnpm 作为包管理器）
RUN npm install -g pnpm@10.4.1

# 复制 KLineChart 的依赖文件和源代码
COPY frontend/KLineChart/package.json frontend/KLineChart/pnpm-lock.yaml* ./KLineChart/
COPY frontend/KLineChart/tsconfig.json ./KLineChart/
COPY frontend/KLineChart/eslint.config.js ./KLineChart/
COPY frontend/KLineChart/scripts/ ./KLineChart/scripts/
COPY frontend/KLineChart/src/ ./KLineChart/src/
COPY frontend/KLineChart/indicators/ ./KLineChart/indicators/

WORKDIR /app/KLineChart

# 安装 KLineChart 依赖（优先使用 pnpm，如果失败则使用 npm）
# 注意：跳过 prepare 脚本（husky 在 Docker 构建中不需要）
RUN if [ -f pnpm-lock.yaml ]; then \
        pnpm install --no-frozen-lockfile --ignore-scripts || npm install --no-fund --no-audit --ignore-scripts; \
    else \
        npm install --no-fund --no-audit --ignore-scripts; \
    fi

# 验证indicators目录存在且包含ATR指标
RUN if [ ! -f indicators/atr.ts ] || [ ! -f indicators/index.ts ]; then \
        echo "ERROR: Custom indicators directory is missing or incomplete" && \
        echo "Checking indicators directory:" && \
        ls -la indicators/ 2>/dev/null || echo "indicators directory not found" && \
        exit 1; \
    else \
        echo "✓ Custom indicators directory verified:" && \
        ls -lh indicators/ && \
        echo ""; \
    fi

# 构建 KLineChart（构建 UMD 版本用于浏览器）
# 注意：构建时会自动包含indicators目录中的自定义指标
RUN if command -v pnpm > /dev/null && [ -f pnpm-lock.yaml ]; then \
        pnpm run build-umd:prod; \
    else \
        npm run build-umd:prod; \
    fi

# 验证构建结果
RUN if [ ! -d dist ] || [ ! -f dist/umd/klinecharts.min.js ]; then \
        echo "ERROR: KLineChart build failed" && \
        ls -la dist/ 2>/dev/null || echo "dist directory not found" && \
        exit 1; \
    else \
        echo "✓ KLineChart UMD build successful" && \
        ls -lh dist/umd/klinecharts.min.js && \
        echo ""; \
    fi

# ==============================================================================
# 阶段2：构建前端应用
# ==============================================================================

FROM ${NODE_IMAGE} AS frontend-builder
WORKDIR /app/frontend

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制frontend的依赖文件和源代码
COPY frontend/package.json frontend/package-lock.json* ./
COPY frontend/src/ ./src/
COPY frontend/index.html ./
COPY frontend/vite.config.js ./
COPY frontend/public/ ./public/

# 创建 klinecharts 资源目录
RUN mkdir -p public/klinecharts

# 从 klinecharts-builder 阶段复制构建好的产物
COPY --from=klinecharts-builder /app/KLineChart/dist/umd/klinecharts.min.js ./public/klinecharts/klinecharts.min.js

# 安装frontend依赖（使用package.json安装，适应跨平台构建）
RUN npm install --no-fund --no-audit

# 验证所有必需文件是否存在
RUN if [ ! -f public/klinecharts/klinecharts.min.js ]; then \
        echo "ERROR: Required klinecharts files missing" && \
        echo "Checking public/klinecharts/ directory:" && \
        ls -la public/klinecharts/ && \
        exit 1; \
    else \
        echo "✓ All klinecharts files are present:" && \
        ls -lh public/klinecharts/ && \
        echo ""; \
    fi

# 构建前端应用
RUN npm run build

# 验证构建结果
RUN if [ ! -d dist ]; then \
        echo "ERROR: Frontend build failed" && \
        exit 1; \
    fi

# ==============================================================================
# 阶段3：准备运行环境（使用 Nginx 高性能服务器）
# ==============================================================================

FROM ${NGINX_IMAGE} AS runtime

# 从frontend-builder阶段复制构建产物
COPY --from=frontend-builder /app/frontend/dist/ /app/dist/

# 复制 Nginx 配置文件
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# 暴露端口
EXPOSE 3000

# 启动 Nginx
CMD ["nginx", "-g", "daemon off;"]