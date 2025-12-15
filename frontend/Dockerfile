# ==============================================================================
# 前端服务 Dockerfile
# ==============================================================================
# 用途：在同一个Docker容器中构建 KLineChart 10.0.0 基础库和前端应用
# 构建上下文：项目根目录
# 要求：使用各自的依赖管理，不使用已有的node_modules
# ==============================================================================

# ==============================================================================
# 阶段1：构建 KLineChart 10.0.0 基础库
# ==============================================================================

FROM node:20-slim AS klinecharts-builder
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
COPY frontend/KLineChart/scripts/ ./KLineChart/scripts/
COPY frontend/KLineChart/src/ ./KLineChart/src/
COPY frontend/KLineChart/indicators/ ./KLineChart/indicators/

WORKDIR /app/KLineChart

# 安装 KLineChart 依赖（优先使用 pnpm，如果失败则使用 npm）
RUN if [ -f pnpm-lock.yaml ]; then \
        pnpm install --no-frozen-lockfile || npm install --no-fund --no-audit; \
    else \
        npm install --no-fund --no-audit; \
    fi

# 构建 KLineChart（构建 UMD 版本用于浏览器）
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
    fi

# ==============================================================================
# 阶段2：构建前端应用
# ==============================================================================

FROM node:20-slim AS frontend-builder
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

FROM nginx:alpine AS runtime

# 从frontend-builder阶段复制构建产物
COPY --from=frontend-builder /app/frontend/dist/ /app/dist/

# 复制 Nginx 配置文件
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# 暴露端口
EXPOSE 3000

# 启动 Nginx
CMD ["nginx", "-g", "daemon off;"]