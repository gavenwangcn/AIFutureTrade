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

# 安装npm依赖（包括 klinecharts）
# 按官网要求：npm install klinecharts
# 注意：klinecharts 将通过 npm 安装，然后在 Vue 组件中通过 ES6 import 使用
RUN if [ -f package-lock.json ]; then \
        npm ci; \
    else \
        npm install; \
    fi

# 验证 klinecharts 是否已正确安装
RUN if [ -d node_modules/klinecharts ]; then \
        echo "[Dockerfile] ✓ klinecharts package installed via npm"; \
        echo "[Dockerfile] Package version:"; \
        cat node_modules/klinecharts/package.json | grep '"version"' || echo "Version not found"; \
        echo "[Dockerfile] Package structure:"; \
        ls -la node_modules/klinecharts/ | head -10; \
    else \
        echo "[Dockerfile] ✗ klinecharts package not found in node_modules"; \
        echo "[Dockerfile] Please ensure 'klinecharts' is listed in package.json dependencies"; \
        exit 1; \
    fi

# ==============================================================================
# 阶段2：复制应用代码和构建
# ==============================================================================
# 复制前端应用源代码
COPY frontend/src/ src/
COPY frontend/index.html ./
COPY frontend/vite.config.js ./
COPY frontend/server.js ./

# 复制静态资源（用于开发环境回退）
COPY frontend/public/ public/

# 复制项目根目录的static目录到临时位置（用于资源同步）
RUN mkdir -p /tmp/static 2>/dev/null || true
RUN if [ -d static ]; then cp -r static/* /tmp/static/ 2>/dev/null || true; fi

# 同步静态资源（从static/目录复制到public/目录）
RUN npm run sync-static 2>&1 || echo "Static assets sync skipped"

# 注意：klinecharts 不再需要复制到 public/lib/
# klinecharts 将通过 npm 安装，在 Vue 组件中通过 ES6 import 使用
# Vite 构建时会自动处理 klinecharts 的打包

# 构建Vue应用（生产环境）
# 注意：构建时 Vite 会将 public/ 目录中的文件复制到 dist/ 目录
RUN npm run build

# 验证构建结果（klinecharts 已通过 Vite 打包到 dist/ 中）
RUN echo "[Dockerfile] Build completed. klinecharts is bundled by Vite."

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

# 启动前端服务器
CMD ["npm", "start"]
