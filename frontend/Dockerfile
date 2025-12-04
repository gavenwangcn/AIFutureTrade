# ==============================================================================
# 前端服务 Dockerfile
# ==============================================================================
# 用途：构建 Vue + Vite 前端应用镜像
# 构建上下文：项目根目录（通过 docker-compose.yml 配置）
# 注意：使用 Vite 构建，生产环境建议使用 nginx 提供静态文件服务
# ==============================================================================

FROM node:18-slim

WORKDIR /app

# 配置 npm 镜像源（使用淘宝镜像以提高下载速度和稳定性）
# 可以通过构建参数 NPM_REGISTRY 覆盖默认镜像源
# 例如：docker build --build-arg NPM_REGISTRY=https://registry.npmjs.org
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN npm config set registry ${NPM_REGISTRY} && \
    npm config set fetch-retries 5 && \
    npm config set fetch-retry-mintimeout 20000 && \
    npm config set fetch-retry-maxtimeout 120000 && \
    npm config set fetch-timeout 300000 && \
    echo "[Dockerfile] npm registry configured to: ${NPM_REGISTRY}"

# ==============================================================================
# 阶段1：构建 klinecharts-pro 基础库
# ==============================================================================
# 注意：为了确保代码变更时重新构建，源代码复制放在依赖安装之后
# 这样当源代码文件变化时，Docker 会重新执行构建步骤

# 复制 klinecharts-pro 的 package.json 和 package-lock.json
COPY frontend/klinecharts-pro/package.json frontend/klinecharts-pro/package-lock.json* ./klinecharts-pro/

# 切换到 klinecharts-pro 目录并安装依赖
WORKDIR /app/klinecharts-pro

# 安装 klinecharts-pro 依赖
# 注意：klinecharts 是 peerDependency，npm install 默认不会安装 peer dependencies
# 需要使用 --install-peer-deps 或显式安装 klinecharts
RUN if [ -f package-lock.json ]; then \
        npm ci --legacy-peer-deps || \
        (echo "[Dockerfile] npm ci failed, retrying with npm install..." && \
         rm -f package-lock.json && \
         npm install --legacy-peer-deps); \
    else \
        npm install --legacy-peer-deps; \
    fi

# 显式安装 peer dependency klinecharts（TypeScript 编译需要）
# 使用 --save-peer 确保安装到 node_modules，但不修改 package.json
RUN echo "[Dockerfile] Installing peer dependency klinecharts for TypeScript compilation..." && \
    npm install klinecharts@^9.8.12 --legacy-peer-deps --no-save || \
    npm install klinecharts@latest --legacy-peer-deps --no-save || \
    (echo "[Dockerfile] ⚠️  Failed to install klinecharts, TypeScript compilation may fail" && exit 1)

# 验证 klinecharts 是否已安装
RUN if [ -d node_modules/klinecharts ]; then \
        echo "[Dockerfile] ✓ klinecharts installed successfully"; \
        echo "[Dockerfile] klinecharts version:"; \
        cat node_modules/klinecharts/package.json | grep '"version"' || echo "Version not found"; \
        echo "[Dockerfile] klinecharts type definitions:"; \
        ls -la node_modules/klinecharts/dist/*.d.ts 2>/dev/null | head -3 || echo "Type definitions not found"; \
    else \
        echo "[Dockerfile] ✗ klinecharts not found in node_modules"; \
        echo "[Dockerfile] Available packages:"; \
        ls -la node_modules/ | grep -E "^d" | head -10; \
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

# 安装前端npm依赖
RUN if [ -f package-lock.json ]; then \
        npm ci --legacy-peer-deps || \
        (echo "[Dockerfile] npm ci failed, retrying with npm install..." && \
         rm -f package-lock.json && \
         npm install --legacy-peer-deps); \
    else \
        npm install --legacy-peer-deps; \
    fi

# 验证 klinecharts 是否已正确安装（klinecharts-pro 需要它作为 peer dependency）
RUN if [ -d node_modules/klinecharts ]; then \
        echo "[Dockerfile] ✓ klinecharts package installed via npm"; \
        echo "[Dockerfile] klinecharts version:"; \
        cat node_modules/klinecharts/package.json | grep '"version"' || echo "Version not found"; \
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
