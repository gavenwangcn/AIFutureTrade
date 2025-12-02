# ============ 前端Dockerfile ============
# Node.js Express前端服务

FROM node:18-slim

WORKDIR /app

# 复制package文件和scripts目录（postinstall脚本需要）
COPY package.json package-lock.json* ./
COPY scripts/ scripts/

# 安装依赖（postinstall会自动执行copy-assets脚本）
RUN if [ -f package-lock.json ]; then \
        npm ci; \
    else \
        npm install; \
    fi

# 复制应用代码
COPY . .

# 确保KLineChart库文件已复制到public/lib（如果postinstall失败则手动执行）
RUN npm run copy-assets || echo "KLineChart files will be served from node_modules"

EXPOSE 3000

# 启动前端服务器
CMD ["npm", "start"]
