# ==============================================================================
# 前端服务 Dockerfile
# ==============================================================================
# 用途：构建 Vue + Vite 前端应用镜像，包含自定义 klinecharts-pro 组件
# 构建上下文：项目根目录（通过 docker-compose.yml 配置）
# 注意：使用 Vite 构建，生产环境建议使用 nginx 提供静态文件服务
# 要求：必须存在 frontend/klinecharts-pro/node_modules（依赖都在这个目录下）
#
# 构建优化：
# - 使用多阶段构建减少最终镜像大小
# - 优化层缓存顺序（不常变化的文件先复制）
# - 使用系统 npm 避免 node_modules 符号链接问题
# ==============================================================================

FROM node:18-slim AS base

# 设置工作目录
WORKDIR /app

# 设置环境变量（优化构建性能）
ENV NODE_ENV=production \
    NPM_CONFIG_LOGLEVEL=warn \
    NPM_CONFIG_PROGRESS=false \
    NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FUND=false

# ==============================================================================
# 阶段1：构建 klinecharts-pro 基础库
# ==============================================================================
FROM base AS klinecharts-pro-builder

WORKDIR /app/klinecharts-pro

# 优化：先复制依赖文件（不常变化，利用缓存）
# 注意：构建上下文是项目根目录，所以路径是 frontend/klinecharts-pro/node_modules
COPY frontend/klinecharts-pro/package.json frontend/klinecharts-pro/package-lock.json* ./

# 复制 node_modules（必须存在）
# 注意：node_modules 很大，放在单独的层以便缓存
COPY frontend/klinecharts-pro/node_modules ./node_modules

# 验证 node_modules 是否存在
RUN echo "[Dockerfile] =========================================" && \
    echo "[Dockerfile] Verifying klinecharts-pro node_modules" && \
    echo "[Dockerfile] =========================================" && \
    if [ ! -d node_modules ]; then \
        echo "[Dockerfile] ✗ ERROR: node_modules directory not found!" && \
        echo "[Dockerfile] Please ensure frontend/klinecharts-pro/node_modules exists" && \
        exit 1; \
    fi && \
    echo "[Dockerfile] ✓ node_modules directory found" && \
    echo "[Dockerfile] node_modules size: $(du -sh node_modules 2>/dev/null | cut -f1 || echo 'unknown')"

# 验证关键依赖
RUN echo "[Dockerfile] Verifying klinecharts-pro dependencies..." && \
    ([ -d node_modules/typescript ] && echo "[Dockerfile] ✓ typescript found") || (echo "[Dockerfile] ✗ typescript not found" && exit 1) && \
    ([ -d node_modules/vite ] && echo "[Dockerfile] ✓ vite found") || (echo "[Dockerfile] ✗ vite not found" && exit 1) && \
    ([ -d node_modules/klinecharts ] && echo "[Dockerfile] ✓ klinecharts found") || (echo "[Dockerfile] ✗ klinecharts not found" && exit 1) && \
    ([ -d node_modules/dts-bundle-generator ] && echo "[Dockerfile] ✓ dts-bundle-generator found") || echo "[Dockerfile] ⚠️  dts-bundle-generator not found (optional)"

# 修复可执行文件权限
# 注意：从 Windows 复制的 node_modules 可能有符号链接问题
# 我们使用系统自带的 npm，所以不需要修复 node_modules/.bin/npm
RUN find node_modules/.bin -type f -exec chmod +x {} \; 2>/dev/null || true

# 优化：先复制配置文件（不常变化），再复制源代码（经常变化）
# 这样可以最大化利用 Docker 层缓存
COPY frontend/klinecharts-pro/tsconfig.json frontend/klinecharts-pro/tsconfig.node.json ./
COPY frontend/klinecharts-pro/vite.config.ts ./
COPY frontend/klinecharts-pro/.babelrc.json ./
COPY frontend/klinecharts-pro/.eslintrc.cjs ./

# 复制源代码（这些文件变化最频繁，放在最后）
COPY frontend/klinecharts-pro/src/ ./src/
COPY frontend/klinecharts-pro/indicators/ ./indicators/

# 修复 npm 可执行文件（如果损坏）
# 使用系统自带的 npm，而不是 node_modules 中的 npm
RUN echo "[Dockerfile] Checking npm availability..." && \
    which npm && \
    npm --version && \
    echo "[Dockerfile] ✓ Using system npm"

# 构建 klinecharts-pro（使用系统 npm）
RUN echo "[Dockerfile] =========================================" && \
    echo "[Dockerfile] Building klinecharts-pro..." && \
    echo "[Dockerfile] =========================================" && \
    /usr/bin/npm run build && \
    echo "[Dockerfile] ✓ klinecharts-pro build completed" && \
    ls -la dist/ | head -10

# 验证构建结果
RUN if [ -d dist ] && [ -f dist/klinecharts-pro.umd.js ] && [ -f dist/klinecharts-pro.css ]; then \
        echo "[Dockerfile] ✓ klinecharts-pro build successful"; \
        echo "[Dockerfile] Build artifacts:"; \
        ls -lh dist/; \
    else \
        echo "[Dockerfile] ✗ klinecharts-pro build failed - missing required files"; \
        echo "[Dockerfile] dist directory contents:"; \
        ls -la dist/ 2>/dev/null || echo "dist directory does not exist"; \
        exit 1; \
    fi

# ==============================================================================
# 阶段2：构建前端应用
# ==============================================================================
FROM base AS frontend-builder

WORKDIR /app

# 优化：先复制依赖文件（不常变化）
COPY frontend/package.json frontend/package-lock.json* ./

# 复制 node_modules（从 klinecharts-pro 目录，因为依赖都在那里）
# 注意：依赖目录在 frontend/klinecharts-pro/node_modules
# 优化：node_modules 很大，单独一层以便缓存
COPY frontend/klinecharts-pro/node_modules ./node_modules

# 验证 node_modules 是否存在
RUN echo "[Dockerfile] =========================================" && \
    echo "[Dockerfile] Verifying frontend node_modules" && \
    echo "[Dockerfile] =========================================" && \
    if [ ! -d node_modules ]; then \
        echo "[Dockerfile] ✗ ERROR: node_modules directory not found!" && \
        echo "[Dockerfile] Please ensure frontend/klinecharts-pro/node_modules exists" && \
        exit 1; \
    fi && \
    echo "[Dockerfile] ✓ node_modules directory found" && \
    echo "[Dockerfile] node_modules size: $(du -sh node_modules 2>/dev/null | cut -f1 || echo 'unknown')"

# 验证关键依赖
RUN echo "[Dockerfile] Verifying frontend dependencies..." && \
    ([ -d node_modules/vue ] && echo "[Dockerfile] ✓ vue found") || (echo "[Dockerfile] ✗ vue not found" && exit 1) && \
    ([ -d node_modules/vite ] && echo "[Dockerfile] ✓ vite found") || (echo "[Dockerfile] ✗ vite not found" && exit 1) && \
    ([ -d node_modules/klinecharts ] && echo "[Dockerfile] ✓ klinecharts found") || (echo "[Dockerfile] ✗ klinecharts not found" && exit 1)

# 优化：先复制配置文件（不常变化），再复制源代码（经常变化）
COPY frontend/vite.config.js ./
COPY frontend/index.html ./
COPY frontend/public/ ./public/

# 复制源代码（这些文件变化最频繁，放在最后）
COPY frontend/src/ ./src/

# 从 klinecharts-pro-builder 阶段复制构建好的 klinecharts-pro
COPY --from=klinecharts-pro-builder /app/klinecharts-pro/dist ./public/klinecharts-pro/

# 复制 klinecharts 基础库到 public/klinecharts-pro/
RUN echo "[Dockerfile] Copying klinecharts base library..." && \
    if [ -f node_modules/klinecharts/dist/klinecharts.umd.js ]; then \
        cp node_modules/klinecharts/dist/klinecharts.umd.js public/klinecharts-pro/klinecharts.js && \
        echo "[Dockerfile] ✓ Copied klinecharts.umd.js"; \
    elif [ -f node_modules/klinecharts/dist/umd/klinecharts.js ]; then \
        cp node_modules/klinecharts/dist/umd/klinecharts.js public/klinecharts-pro/klinecharts.js && \
        echo "[Dockerfile] ✓ Copied klinecharts.js from umd directory"; \
    elif [ -f node_modules/klinecharts/dist/klinecharts.js ]; then \
        cp node_modules/klinecharts/dist/klinecharts.js public/klinecharts-pro/klinecharts.js && \
        echo "[Dockerfile] ✓ Copied klinecharts.js from dist directory"; \
    else \
        echo "[Dockerfile] ⚠️  Warning: klinecharts UMD file not found, checking available files..." && \
        find node_modules/klinecharts/dist -name "*.js" -type f 2>/dev/null | head -10 || echo "No JS files found in klinecharts/dist"; \
        echo "[Dockerfile] Available klinecharts files:"; \
        find node_modules/klinecharts -maxdepth 3 -name "*.js" -type f 2>/dev/null | head -10 || echo "No JS files found"; \
    fi && \
    echo "[Dockerfile] klinecharts-pro public directory contents:" && \
    ls -lh public/klinecharts-pro/ 2>/dev/null || echo "public/klinecharts-pro directory not found"

# 构建前端应用（使用系统 npm）
RUN echo "[Dockerfile] =========================================" && \
    echo "[Dockerfile] Building frontend application..." && \
    echo "[Dockerfile] =========================================" && \
    /usr/bin/npm run build && \
    echo "[Dockerfile] ✓ Frontend build completed"

# 验证构建结果
RUN echo "[Dockerfile] =========================================" && \
    echo "[Dockerfile] Verifying build results..." && \
    echo "[Dockerfile] =========================================" && \
    if [ -d dist ]; then \
        echo "[Dockerfile] ✓ Build successful, dist directory exists"; \
        echo "[Dockerfile] dist directory contents:"; \
        ls -lh dist/ | head -15; \
        if [ -d dist/klinecharts-pro ]; then \
            echo "[Dockerfile] ✓ klinecharts-pro directory found in dist"; \
            echo "[Dockerfile] klinecharts-pro files:"; \
            ls -lh dist/klinecharts-pro/; \
        else \
            echo "[Dockerfile] ⚠️  Warning: klinecharts-pro directory not found in dist"; \
        fi; \
    else \
        echo "[Dockerfile] ✗ Build failed, dist directory not found"; \
        exit 1; \
    fi

# ==============================================================================
# 阶段3：运行环境（最小化镜像，优化构建速度）
# ==============================================================================
FROM node:18-slim AS runtime

# 设置工作目录
WORKDIR /app

# 设置环境变量（优化 npm 性能）
ENV NODE_ENV=production \
    NPM_CONFIG_LOGLEVEL=warn \
    NPM_CONFIG_PROGRESS=false

# 优化：只复制运行时需要的文件
# 复制 package.json（用于运行 npm 命令）
COPY frontend/package.json frontend/package-lock.json* ./

# 复制 node_modules（从 klinecharts-pro 目录，因为依赖都在那里）
# 注意：依赖目录在 frontend/klinecharts-pro/node_modules
COPY frontend/klinecharts-pro/node_modules ./node_modules

# 验证 node_modules 是否存在
RUN echo "[Dockerfile] Verifying runtime node_modules..." && \
    if [ ! -d node_modules ]; then \
        echo "[Dockerfile] ✗ ERROR: node_modules directory not found!" && \
        echo "[Dockerfile] Please ensure frontend/klinecharts-pro/node_modules exists" && \
        exit 1; \
    fi && \
    echo "[Dockerfile] ✓ Runtime node_modules verified"

# 从构建阶段复制构建产物（只复制 dist 目录，不包含源代码）
COPY --from=frontend-builder /app/dist ./dist

# 暴露端口
EXPOSE 3000

# 启动 Vite 预览服务器（用于开发/测试）
# 注意：生产环境建议使用 nginx 或其他静态文件服务器来提供 dist/ 目录
# 如果需要代理 API，请在 nginx 中配置反向代理
CMD ["/usr/bin/npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "3000"]
