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
# 注意：必须确保 klinecharts 正确安装，Vue 应用才能正常构建和运行
RUN if [ -f package-lock.json ]; then \
        npm ci; \
    else \
        npm install; \
    fi

# 验证 klinecharts 是否已安装
RUN if [ -d node_modules/klinecharts ]; then \
        echo "[Dockerfile] ✓ klinecharts package installed"; \
        ls -la node_modules/klinecharts/dist/ 2>/dev/null || echo "[Dockerfile] ⚠ klinecharts dist directory not found"; \
    else \
        echo "[Dockerfile] ✗ klinecharts package not found in node_modules"; \
        echo "[Dockerfile] Please check package.json dependencies"; \
        exit 1; \
    fi

# 验证 klinecharts.min.js 文件是否存在
RUN if [ -f node_modules/klinecharts/dist/klinecharts.min.js ]; then \
        echo "[Dockerfile] ✓ klinecharts.min.js found in node_modules"; \
        ls -lh node_modules/klinecharts/dist/klinecharts.min.js; \
    else \
        echo "[Dockerfile] ✗ klinecharts.min.js not found"; \
        echo "[Dockerfile] Available files in dist:"; \
        ls -la node_modules/klinecharts/dist/ 2>/dev/null || echo "Directory not found"; \
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

# 确保KLineChart库文件已复制到 public/lib/
# 这一步必须在构建 Vue 应用之前执行，确保构建后的 dist/ 目录中包含 klinecharts 文件
RUN npm run copy-assets

# 验证 klinecharts 文件是否已复制到 public/lib/
RUN if [ -f public/lib/klinecharts.min.js ]; then \
        echo "[Dockerfile] ✓ klinecharts.min.js copied to public/lib/"; \
        ls -lh public/lib/klinecharts.min.js; \
    else \
        echo "[Dockerfile] ✗ klinecharts.min.js not found in public/lib/"; \
        echo "[Dockerfile] Attempting manual copy..."; \
        mkdir -p public/lib && \
        cp node_modules/klinecharts/dist/* public/lib/ 2>/dev/null && \
        if [ -f public/lib/klinecharts.min.js ]; then \
            echo "[Dockerfile] ✓ Manual copy successful"; \
        else \
            echo "[Dockerfile] ✗ Manual copy failed"; \
            exit 1; \
        fi; \
    fi

# 构建Vue应用（生产环境）
# 注意：构建时 Vite 会将 public/ 目录中的文件复制到 dist/ 目录
RUN npm run build

# 验证构建后的 dist/ 目录中是否包含 klinecharts 文件
RUN if [ -f dist/lib/klinecharts.min.js ]; then \
        echo "[Dockerfile] ✓ klinecharts.min.js found in dist/lib/ after build"; \
        ls -lh dist/lib/klinecharts.min.js; \
    else \
        echo "[Dockerfile] ⚠ klinecharts.min.js not found in dist/lib/"; \
        echo "[Dockerfile] Checking dist directory structure:"; \
        ls -la dist/ 2>/dev/null | head -20; \
        echo "[Dockerfile] Attempting to copy klinecharts to dist/lib/..."; \
        mkdir -p dist/lib && \
        cp public/lib/klinecharts.min.js dist/lib/ 2>/dev/null && \
        if [ -f dist/lib/klinecharts.min.js ]; then \
            echo "[Dockerfile] ✓ Manual copy to dist/lib/ successful"; \
        else \
            echo "[Dockerfile] ⚠ Manual copy failed, but continuing (server.js will serve from node_modules)"; \
        fi; \
    fi

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
