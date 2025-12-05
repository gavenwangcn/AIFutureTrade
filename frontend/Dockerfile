# ==============================================================================
# 前端服务 Dockerfile
# ==============================================================================
# 用途：在同一个Docker容器中构建 klinecharts-pro 基础库和前端应用
# 构建上下文：项目根目录
# 要求：使用各自的依赖管理，不使用已有的node_modules
# ==============================================================================

# ==============================================================================
# 阶段1：构建 klinecharts-pro 基础库
# ==============================================================================

FROM node:20-slim AS klinecharts-pro-builder
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制klinecharts-pro的依赖文件和源代码
COPY frontend/klinecharts-pro/package.json frontend/klinecharts-pro/package-lock.json* ./klinecharts-pro/
COPY frontend/klinecharts-pro/tsconfig.json frontend/klinecharts-pro/tsconfig.node.json ./klinecharts-pro/
COPY frontend/klinecharts-pro/vite.config.ts ./klinecharts-pro/
COPY frontend/klinecharts-pro/.babelrc.json ./klinecharts-pro/
COPY frontend/klinecharts-pro/.eslintrc.cjs ./klinecharts-pro/
COPY frontend/klinecharts-pro/src/ ./klinecharts-pro/src/
COPY frontend/klinecharts-pro/indicators/ ./klinecharts-pro/indicators/

WORKDIR /app/klinecharts-pro

# 安装klinecharts-pro依赖（根据package.json安装，适应跨平台构建）
    RUN npm install --no-fund --no-audit

# 构建klinecharts-pro
RUN npm run build

# 验证构建结果
RUN if [ ! -d dist ] || [ ! -f dist/klinecharts-pro.umd.js ] || [ ! -f dist/klinecharts-pro.css ]; then \
        echo "ERROR: klinecharts-pro build failed" && \
        exit 1; \
    fi

# 将构建好的klinecharts-pro包链接到全局，方便frontend使用
RUN npm link

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

# 创建klinecharts-pro资源目录
RUN mkdir -p public/klinecharts-pro

# 从klinecharts-pro-builder阶段复制构建好的产物和package.json
    COPY --from=klinecharts-pro-builder /app/klinecharts-pro/dist/ ./klinecharts-pro-build/
    COPY --from=klinecharts-pro-builder /app/klinecharts-pro/package.json ./klinecharts-pro-build/

    # 安装frontend依赖（使用package.json安装，适应跨平台构建）
    RUN npm install --no-fund --no-audit

    # 创建node_modules/@klinecharts/pro目录并复制自构建的包
    RUN mkdir -p node_modules/@klinecharts/pro
    RUN cp -r ./klinecharts-pro-build/* node_modules/@klinecharts/pro/

# 复制klinecharts基础库（如果需要的话）
RUN if [ -f node_modules/klinecharts/dist/klinecharts.umd.js ]; then \
        cp node_modules/klinecharts/dist/klinecharts.umd.js public/klinecharts-pro/klinecharts.js && \
        echo "Using klinecharts from node_modules"; \
    elif [ -f node_modules/klinecharts/dist/umd/klinecharts.js ]; then \
        cp node_modules/klinecharts/dist/umd/klinecharts.js public/klinecharts-pro/klinecharts.js && \
        echo "Using klinecharts from node_modules"; \
    elif [ -f node_modules/klinecharts/dist/klinecharts.js ]; then \
        cp node_modules/klinecharts/dist/klinecharts.js public/klinecharts-pro/klinecharts.js && \
        echo "Using klinecharts from node_modules"; \
    else \
        echo "WARNING: klinecharts.js not found in node_modules"; \
    fi

# 复制自构建的klinecharts-pro产物到public目录，供动态加载使用
RUN cp ./klinecharts-pro-build/klinecharts-pro.umd.js public/klinecharts-pro/ && \
    cp ./klinecharts-pro-build/klinecharts-pro.css public/klinecharts-pro/

# 验证所有必需文件是否存在
RUN if [ ! -f public/klinecharts-pro/klinecharts-pro.umd.js ] || \
        [ ! -f public/klinecharts-pro/klinecharts-pro.css ] || \
        [ ! -f public/klinecharts-pro/klinecharts.js ]; then \
        echo "ERROR: Required klinecharts-pro files missing" && \
        echo "Checking public/klinecharts-pro/ directory:" && \
        ls -la public/klinecharts-pro/ && \
        exit 1; \
    else \
        echo "✓ All klinecharts-pro files are present:" && \
        ls -lh public/klinecharts-pro/ && \
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
# 阶段3：准备运行环境
# ==============================================================================

FROM node:20-slim AS runtime
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从frontend-builder阶段复制构建产物
COPY --from=frontend-builder /app/frontend/dist/ ./dist/

# 暴露端口
EXPOSE 3000

# 启动服务
CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "3000", "--outDir", "/app/dist"]