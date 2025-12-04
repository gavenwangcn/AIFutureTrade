# ==============================================================================
# 前端服务 Dockerfile
# ==============================================================================
# 用途：构建 Vue + Vite 前端应用镜像
# 构建上下文：项目根目录（通过 docker-compose.yml 配置）
# 注意：使用 Vite 构建，生产环境建议使用 nginx 提供静态文件服务
# ==============================================================================

FROM node:18-slim

WORKDIR /app

# 配置 npm 镜像源（使用阿里云镜像以提高下载速度和稳定性）
# 阿里云 npm 镜像地址：https://registry.npmmirror.com（原淘宝镜像新地址）
# 可以通过构建参数 NPM_REGISTRY 覆盖默认镜像源
# 例如：docker build --build-arg NPM_REGISTRY=https://registry.npmjs.org
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN echo "[Dockerfile] =========================================" && \
    echo "[Dockerfile] Configuring npm registry (Aliyun Mirror)" && \
    echo "[Dockerfile] =========================================" && \
    npm config set registry ${NPM_REGISTRY} && \
    npm config set fetch-retries 3 && \
    npm config set fetch-retry-mintimeout 10000 && \
    npm config set fetch-retry-maxtimeout 60000 && \
    npm config set fetch-timeout 120000 && \
    npm config set prefer-online true && \
    npm config set progress false && \
    npm config set loglevel warn && \
    echo "[Dockerfile] ✓ npm registry: ${NPM_REGISTRY}" && \
    echo "[Dockerfile] ✓ npm configuration optimized for speed" && \
    echo "[Dockerfile] Verifying registry..." && \
    npm config get registry && \
    echo "[Dockerfile] Testing registry connectivity..." && \
    npm ping --registry ${NPM_REGISTRY} 2>&1 | head -3 || echo "[Dockerfile] Registry ping test skipped"

# ==============================================================================
# 阶段1：构建 klinecharts-pro 基础库
# ==============================================================================
# 注意：使用本地 node_modules 目录进行构建，不依赖 npm registry

# 复制 klinecharts-pro 的 package.json 和 package-lock.json
COPY frontend/klinecharts-pro/package.json frontend/klinecharts-pro/package-lock.json* ./klinecharts-pro/

# 切换到 klinecharts-pro 目录
WORKDIR /app/klinecharts-pro

# 复制 klinecharts-pro 的 node_modules 目录（如果存在）
# 注意：使用 RUN 命令检查并复制，因为 COPY 无法处理不存在的目录
RUN if [ -d ../frontend/klinecharts-pro/node_modules ]; then \
        echo "[Dockerfile] ✓ frontend/klinecharts-pro/node_modules found, copying..." && \
        cp -r ../frontend/klinecharts-pro/node_modules ./node_modules && \
        echo "[Dockerfile] ✓ node_modules copied successfully"; \
    else \
        echo "[Dockerfile] ⚠️  frontend/klinecharts-pro/node_modules not found, will install from registry"; \
    fi

# 如果 node_modules 不存在，从 registry 安装依赖
RUN if [ ! -d node_modules ]; then \
        echo "[Dockerfile] =========================================" && \
        echo "[Dockerfile] Installing klinecharts-pro dependencies from registry" && \
        echo "[Dockerfile] =========================================" && \
        npm install --legacy-peer-deps 2>&1 | head -50 && \
        echo "[Dockerfile] Installing peer dependency klinecharts..." && \
        npm install klinecharts@latest --legacy-peer-deps --no-save 2>&1 | head -30 || \
        (echo "[Dockerfile] ⚠️  Failed to install klinecharts, continuing..." && true) && \
        echo "[Dockerfile] ✓ klinecharts-pro dependencies installed"; \
    else \
        echo "[Dockerfile] ✓ Using existing node_modules, skipping npm install"; \
    fi

# 验证 node_modules 是否存在
RUN echo "[Dockerfile] =========================================" && \
    echo "[Dockerfile] Verifying klinecharts-pro node_modules" && \
    echo "[Dockerfile] =========================================" && \
    if [ -d node_modules ]; then \
        echo "[Dockerfile] ✓ node_modules directory found"; \
        echo "[Dockerfile] node_modules size: $(du -sh node_modules 2>/dev/null | cut -f1 || echo 'unknown')"; \
        echo "[Dockerfile] Checking for key dependencies..." && \
        ([ -d node_modules/typescript ] && echo "[Dockerfile] ✓ typescript found") || echo "[Dockerfile] ✗ typescript not found"; \
        ([ -d node_modules/vite ] && echo "[Dockerfile] ✓ vite found") || echo "[Dockerfile] ✗ vite not found"; \
        ([ -d node_modules/klinecharts ] && echo "[Dockerfile] ✓ klinecharts found") || echo "[Dockerfile] ✗ klinecharts not found"; \
        ([ -d node_modules/dts-bundle-generator ] && echo "[Dockerfile] ✓ dts-bundle-generator found") || echo "[Dockerfile] ✗ dts-bundle-generator not found"; \
    else \
        echo "[Dockerfile] ✗ node_modules directory not found after installation"; \
        exit 1; \
    fi

# 验证 klinecharts 是否已安装（TypeScript 编译需要）
RUN echo "[Dockerfile] Verifying klinecharts installation..." && \
    if [ -d node_modules/klinecharts ]; then \
        echo "[Dockerfile] ✓ klinecharts found in node_modules/klinecharts"; \
        echo "[Dockerfile] klinecharts version:"; \
        cat node_modules/klinecharts/package.json | grep '"version"' 2>/dev/null || echo "Version not found"; \
        echo "[Dockerfile] klinecharts type definitions:"; \
        ls -la node_modules/klinecharts/dist/*.d.ts 2>/dev/null | head -5 || echo "Type definitions not found in dist/"; \
        find node_modules/klinecharts -name "*.d.ts" 2>/dev/null | head -5 || echo "No .d.ts files found"; \
    elif [ -d node_modules/@klinecharts/klinecharts ]; then \
        echo "[Dockerfile] ✓ klinecharts found in node_modules/@klinecharts/klinecharts"; \
        echo "[Dockerfile] Creating symlink for compatibility..." && \
        ln -s @klinecharts/klinecharts node_modules/klinecharts 2>/dev/null || true; \
    else \
        echo "[Dockerfile] ✗ klinecharts not found in node_modules"; \
        echo "[Dockerfile] Available packages:"; \
        ls -la node_modules/ | grep -E "^d" | head -20; \
        exit 1; \
    fi

# 修复 node_modules/.bin 中的可执行文件权限
RUN find node_modules/.bin -type f -exec chmod +x {} \; 2>/dev/null || true

# 复制 klinecharts-pro 源代码（放在依赖安装之后，确保代码变更时重新构建）
# 注意：如果源代码文件发生变化，Docker 会重新执行此步骤及后续的构建步骤
COPY frontend/klinecharts-pro/ ./

# 再次修复权限
RUN find node_modules/.bin -type f -exec chmod +x {} \; 2>/dev/null || true && \
    find node_modules -name "tsc" -type f -exec chmod +x {} \; 2>/dev/null || true

# 构建 klinecharts-pro
# 注意：此步骤会在源代码文件变化时自动重新执行
RUN echo "[Dockerfile] Building klinecharts-pro..." && \
    echo "[Dockerfile] Source files timestamp:" && \
    ls -la src/KLineChartPro.tsx 2>/dev/null | head -1 || echo "Source file not found" && \
    node node_modules/typescript/bin/tsc && \
    node node_modules/vite/bin/vite.js build && \
    (chmod +x node_modules/.bin/dts-bundle-generator 2>/dev/null || true) && \
    (node_modules/.bin/dts-bundle-generator --no-banner true --umd-module-name klinechartspro -o dist/index.d.ts src/index.ts 2>/dev/null || \
     echo "[Dockerfile] dts-bundle-generator skipped, TypeScript types already generated") && \
    echo "[Dockerfile] ✓ klinecharts-pro build completed" && \
    ls -la dist/ | head -10

# 验证 klinecharts-pro 构建结果
RUN if [ -d dist ] && [ -f dist/klinecharts-pro.umd.js ] && [ -f dist/klinecharts-pro.css ]; then \
        echo "[Dockerfile] ✓ klinecharts-pro build successful"; \
    else \
        echo "[Dockerfile] ✗ klinecharts-pro build failed"; \
        exit 1; \
    fi

# ==============================================================================
# 阶段2：安装前端依赖
# ==============================================================================
# 切换回主工作目录
WORKDIR /app

# 复制前端依赖文件
COPY frontend/package.json frontend/package-lock.json* ./

# 复制前端的 node_modules 目录（如果存在）
# 注意：使用 COPY 命令复制整个 node_modules 目录，但需要先检查是否存在
# 如果 node_modules 不存在，则从 npm registry 安装依赖
RUN if [ -d frontend/node_modules ]; then \
        echo "[Dockerfile] ✓ frontend/node_modules found, copying..." && \
        cp -r frontend/node_modules ./node_modules && \
        echo "[Dockerfile] ✓ node_modules copied successfully"; \
    else \
        echo "[Dockerfile] ⚠️  frontend/node_modules not found, will install from registry"; \
    fi

# 如果 node_modules 不存在，从 registry 安装依赖
RUN if [ ! -d node_modules ]; then \
        echo "[Dockerfile] =========================================" && \
        echo "[Dockerfile] Installing frontend dependencies from registry" && \
        echo "[Dockerfile] =========================================" && \
        npm install --legacy-peer-deps 2>&1 | head -50 && \
        echo "[Dockerfile] ✓ Frontend dependencies installed"; \
    else \
        echo "[Dockerfile] ✓ Using existing node_modules, skipping npm install"; \
    fi

# 验证 node_modules 是否存在
RUN echo "[Dockerfile] =========================================" && \
    echo "[Dockerfile] Verifying frontend node_modules" && \
    echo "[Dockerfile] =========================================" && \
    if [ -d node_modules ]; then \
        echo "[Dockerfile] ✓ node_modules directory found"; \
        echo "[Dockerfile] node_modules size: $(du -sh node_modules 2>/dev/null | cut -f1 || echo 'unknown')"; \
        echo "[Dockerfile] Checking for key dependencies..." && \
        ([ -d node_modules/vue ] && echo "[Dockerfile] ✓ vue found") || echo "[Dockerfile] ✗ vue not found"; \
        ([ -d node_modules/vite ] && echo "[Dockerfile] ✓ vite found") || echo "[Dockerfile] ✗ vite not found"; \
        ([ -d node_modules/klinecharts ] && echo "[Dockerfile] ✓ klinecharts found") || echo "[Dockerfile] ✗ klinecharts not found"; \
    else \
        echo "[Dockerfile] ✗ node_modules directory not found after installation"; \
        exit 1; \
    fi

# 验证 klinecharts 是否已正确安装（klinecharts-pro 需要它作为 peer dependency）
RUN if [ -d node_modules/klinecharts ]; then \
        echo "[Dockerfile] ✓ klinecharts package found in node_modules"; \
        echo "[Dockerfile] klinecharts version:"; \
        cat node_modules/klinecharts/package.json | grep '"version"' 2>/dev/null || echo "Version not found"; \
    else \
        echo "[Dockerfile] ✗ klinecharts package not found in node_modules"; \
        echo "[Dockerfile] klinecharts is required as a peer dependency"; \
        exit 1; \
    fi

# ==============================================================================
# 阶段3：复制应用代码和准备静态资源
# ==============================================================================
# 复制前端应用源代码
COPY frontend/src/ src/
COPY frontend/index.html ./
COPY frontend/vite.config.js ./

# 复制静态资源（用于开发环境回退）
COPY frontend/public/ public/

# 将构建好的 klinecharts-pro 复制到 public/klinecharts-pro/ 目录
# 这样前端可以通过 /klinecharts-pro/ 路径访问这些文件
RUN mkdir -p public/klinecharts-pro && \
    cp -r klinecharts-pro/dist/* public/klinecharts-pro/ && \
    echo "[Dockerfile] ✓ Copied klinecharts-pro build artifacts to public/klinecharts-pro/" && \
    ls -la public/klinecharts-pro/ | head -10

# 复制 klinecharts 基础库到 public/klinecharts-pro/（如果需要）
# klinecharts 应该已经通过 npm 安装，但我们需要将其 UMD 版本复制到 public
RUN if [ -f node_modules/klinecharts/dist/klinecharts.umd.js ]; then \
        cp node_modules/klinecharts/dist/klinecharts.umd.js public/klinecharts-pro/klinecharts.js && \
        echo "[Dockerfile] ✓ Copied klinecharts base library"; \
    elif [ -f node_modules/klinecharts/dist/umd/klinecharts.js ]; then \
        cp node_modules/klinecharts/dist/umd/klinecharts.js public/klinecharts-pro/klinecharts.js && \
        echo "[Dockerfile] ✓ Copied klinecharts base library"; \
    else \
        echo "[Dockerfile] Warning: klinecharts UMD file not found, checking available files..." && \
        find node_modules/klinecharts/dist -name "*.js" -type f | head -5 || echo "No JS files found"; \
    fi

# ==============================================================================
# 阶段4：构建前端应用
# ==============================================================================
# 构建Vue应用（生产环境）
# 注意：构建时 Vite 会将 public/ 目录中的文件复制到 dist/ 目录
# klinecharts-pro 的文件已经在 public/klinecharts-pro/ 中，会被自动复制到 dist/klinecharts-pro/
RUN npm run build

# 验证构建结果
RUN echo "[Dockerfile] Frontend build completed. klinecharts-pro files are available in dist/klinecharts-pro/." && \
    if [ -d dist ]; then \
        echo "[Dockerfile] ✓ Build successful, dist directory exists"; \
        ls -la dist/ | head -10; \
        ls -la dist/klinecharts-pro/ 2>/dev/null || echo "klinecharts-pro directory not found in dist"; \
    else \
        echo "[Dockerfile] ✗ Build failed, dist directory not found"; \
        exit 1; \
    fi

# ==============================================================================
# 阶段5：暴露端口和启动服务
# ==============================================================================
EXPOSE 3000

# 启动 Vite 预览服务器（用于开发/测试）
# 注意：生产环境建议使用 nginx 或其他静态文件服务器来提供 dist/ 目录
# 如果需要代理 API，请在 nginx 中配置反向代理
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "3000"]
