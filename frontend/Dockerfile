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
# 阶段1：安装依赖
# ==============================================================================
# 复制依赖文件和构建脚本（利用Docker缓存层）
COPY frontend/package.json frontend/package-lock.json* ./
COPY frontend/scripts/ scripts/

# 安装npm依赖（包括 @klinecharts/pro）
# 按官网要求：npm install @klinecharts/pro
# 注意：@klinecharts/pro 将通过 npm 安装，然后在 Vue 组件中通过 ES6 import 使用
# 添加重试机制以提高网络不稳定时的成功率
RUN if [ -f package-lock.json ]; then \
        npm ci --legacy-peer-deps || \
        (echo "[Dockerfile] npm ci failed, retrying with npm install..." && \
         rm -f package-lock.json && \
         npm install --legacy-peer-deps); \
    else \
        npm install --legacy-peer-deps; \
    fi

# 验证 @klinecharts/pro 是否已正确安装
RUN if [ -d node_modules/@klinecharts/pro ]; then \
        echo "[Dockerfile] ✓ @klinecharts/pro package installed via npm"; \
        echo "[Dockerfile] Package version:"; \
        cat node_modules/@klinecharts/pro/package.json | grep '"version"' || echo "Version not found"; \
        echo "[Dockerfile] Package structure:"; \
        ls -la node_modules/@klinecharts/pro/ | head -10; \
    else \
        echo "[Dockerfile] ✗ @klinecharts/pro package not found in node_modules"; \
        echo "[Dockerfile] Please ensure '@klinecharts/pro' is listed in package.json dependencies"; \
        exit 1; \
    fi

# ==============================================================================
# 阶段2：复制应用代码和构建
# ==============================================================================
# 复制前端应用源代码
COPY frontend/src/ src/
COPY frontend/index.html ./
COPY frontend/vite.config.js ./

# 复制静态资源（用于开发环境回退）
COPY frontend/public/ public/

# 复制项目根目录的static目录到临时位置（用于资源同步）
RUN mkdir -p /tmp/static 2>/dev/null || true
RUN if [ -d static ]; then cp -r static/* /tmp/static/ 2>/dev/null || true; fi

# 同步静态资源（从static/目录复制到public/目录）
RUN npm run sync-static 2>&1 || echo "Static assets sync skipped"

# 注意：@klinecharts/pro 不再需要复制到 public/lib/
# @klinecharts/pro 将通过 npm 安装，在 Vue 组件中通过 ES6 import 使用
# Vite 构建时会自动处理 @klinecharts/pro 的打包

# 构建Vue应用（生产环境）
# 注意：构建时 Vite 会将 public/ 目录中的文件复制到 dist/ 目录
RUN npm run build

# 验证构建结果（@klinecharts/pro 已通过 Vite 打包到 dist/ 中）
RUN echo "[Dockerfile] Build completed. @klinecharts/pro is bundled by Vite."

# 验证构建结果
RUN if [ -d dist ]; then \
        echo "[Dockerfile] ✓ Build successful, dist directory exists"; \
        ls -la dist/ | head -10; \
    else \
        echo "[Dockerfile] ✗ Build failed, dist directory not found"; \
        exit 1; \
    fi

# ==============================================================================
# 阶段4：暴露端口和启动服务
# ==============================================================================
EXPOSE 3000

# 启动 Vite 预览服务器（用于开发/测试）
# 注意：生产环境建议使用 nginx 或其他静态文件服务器来提供 dist/ 目录
# 如果需要代理 API，请在 nginx 中配置反向代理
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "3000"]
