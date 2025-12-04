# ==============================================================================
# 前端服务 Dockerfile
# ==============================================================================
# 用途：构建 Vue + Vite 前端应用镜像，包含自定义 klinecharts-pro 组件
# 构建上下文：项目根目录（通过 docker-compose.yml 配置）
# 要求：必须存在 frontend/klinecharts-pro/node_modules（依赖都在这个目录下）
#
# 注意：如果网络较慢，请先配置 Docker 镜像加速器
# 运行：sudo bash docker-registry-setup.sh
# ==============================================================================

FROM node:18-slim AS base
WORKDIR /app

# ==============================================================================
# 阶段1：构建 klinecharts-pro 基础库
# ==============================================================================
FROM base AS klinecharts-pro-builder
WORKDIR /app/klinecharts-pro

# 复制依赖文件和 node_modules
COPY frontend/klinecharts-pro/package.json frontend/klinecharts-pro/package-lock.json* ./
COPY frontend/klinecharts-pro/node_modules ./node_modules

# 验证 node_modules
RUN if [ ! -d node_modules ]; then \
        echo "ERROR: node_modules not found!" && \
        exit 1; \
    fi

# 复制源代码和配置文件
COPY frontend/klinecharts-pro/tsconfig.json frontend/klinecharts-pro/tsconfig.node.json ./
COPY frontend/klinecharts-pro/vite.config.ts ./
COPY frontend/klinecharts-pro/.babelrc.json ./
COPY frontend/klinecharts-pro/.eslintrc.cjs ./
COPY frontend/klinecharts-pro/src/ ./src/
COPY frontend/klinecharts-pro/indicators/ ./indicators/

# 修复可执行文件权限
RUN find node_modules/.bin -type f -exec chmod +x {} \; 2>/dev/null || true

# 修复平台特定的原生模块（esbuild 等）
# 从 Windows 复制的 node_modules 包含 Windows/macOS 版本，需要重新安装 Linux 版本
RUN rm -rf node_modules/@esbuild && \
    npm install --no-save --platform=linux --arch=x64 esbuild || \
    npm rebuild esbuild --platform=linux --arch=x64 || true

# 构建 klinecharts-pro
# 在 Docker 容器中，直接使用 node 执行构建工具，避免符号链接问题
RUN node node_modules/typescript/bin/tsc && \
    node node_modules/vite/bin/vite.js build

# 生成类型定义文件
# dts-bundle-generator 在 node_modules/.bin 中，但符号链接可能有问题，使用 node 直接执行
RUN if [ -f node_modules/dts-bundle-generator/dist/index.js ]; then \
        node node_modules/dts-bundle-generator/dist/index.js --no-banner true --umd-module-name klinechartspro -o dist/index.d.ts src/index.ts; \
    elif [ -f node_modules/dts-bundle-generator/lib/index.js ]; then \
        node node_modules/dts-bundle-generator/lib/index.js --no-banner true --umd-module-name klinechartspro -o dist/index.d.ts src/index.ts; \
    else \
        echo "WARNING: dts-bundle-generator not found, skipping type definition generation"; \
    fi

# 验证构建结果
RUN if [ ! -d dist ] || [ ! -f dist/klinecharts-pro.umd.js ] || [ ! -f dist/klinecharts-pro.css ]; then \
        echo "ERROR: klinecharts-pro build failed" && \
        exit 1; \
    fi

# ==============================================================================
# 阶段2：构建前端应用
# ==============================================================================
FROM base AS frontend-builder
WORKDIR /app

# 复制依赖文件
COPY frontend/package.json frontend/package-lock.json* ./
COPY frontend/klinecharts-pro/node_modules ./node_modules

# 验证 node_modules
RUN if [ ! -d node_modules ]; then \
        echo "ERROR: node_modules not found!" && \
        exit 1; \
    fi

# 修复可执行文件权限
RUN find node_modules/.bin -type f -exec chmod +x {} \; 2>/dev/null || true

# 复制源代码和配置文件
COPY frontend/src/ ./src/
COPY frontend/index.html ./
COPY frontend/vite.config.js ./
COPY frontend/public/ ./public/

# 创建 klinecharts-pro 目录
RUN mkdir -p public/klinecharts-pro

# 从 klinecharts-pro-builder 复制构建产物
# 前端需要：/klinecharts-pro/klinecharts-pro.css 和 /klinecharts-pro/klinecharts-pro.umd.js
COPY --from=klinecharts-pro-builder /app/klinecharts-pro/dist/klinecharts-pro.umd.js ./public/klinecharts-pro/
COPY --from=klinecharts-pro-builder /app/klinecharts-pro/dist/klinecharts-pro.css ./public/klinecharts-pro/

# 复制 klinecharts 基础库
# 前端需要：/klinecharts-pro/klinecharts.js
RUN if [ -f node_modules/klinecharts/dist/klinecharts.umd.js ]; then \
        cp node_modules/klinecharts/dist/klinecharts.umd.js public/klinecharts-pro/klinecharts.js; \
    elif [ -f node_modules/klinecharts/dist/umd/klinecharts.js ]; then \
        cp node_modules/klinecharts/dist/umd/klinecharts.js public/klinecharts-pro/klinecharts.js; \
    elif [ -f node_modules/klinecharts/dist/klinecharts.js ]; then \
        cp node_modules/klinecharts/dist/klinecharts.js public/klinecharts-pro/klinecharts.js; \
    else \
        echo "ERROR: klinecharts.js not found" && \
        exit 1; \
    fi

# 验证所有必需文件是否存在
RUN if [ ! -f public/klinecharts-pro/klinecharts-pro.umd.js ] || \
        [ ! -f public/klinecharts-pro/klinecharts-pro.css ] || \
        [ ! -f public/klinecharts-pro/klinecharts.js ]; then \
        echo "ERROR: Required klinecharts-pro files missing" && \
        ls -la public/klinecharts-pro/ && \
        exit 1; \
    fi

# 构建前端应用
# 直接使用 node 执行 vite，避免权限问题
RUN node node_modules/vite/bin/vite.js build

# 验证构建结果
RUN if [ ! -d dist ]; then \
        echo "ERROR: Frontend build failed" && \
        exit 1; \
    fi

# ==============================================================================
# 阶段3：运行环境
# ==============================================================================
FROM node:18-slim AS runtime
WORKDIR /app

# 复制依赖文件
COPY frontend/package.json frontend/package-lock.json* ./
COPY frontend/klinecharts-pro/node_modules ./node_modules

# 验证 node_modules
RUN if [ ! -d node_modules ]; then \
        echo "ERROR: node_modules not found!" && \
        exit 1; \
    fi

# 从构建阶段复制构建产物
COPY --from=frontend-builder /app/dist ./dist

# 暴露端口
EXPOSE 3000

# 启动服务
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "3000"]
