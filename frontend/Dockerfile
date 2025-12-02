# ============ 前端Dockerfile ============
# Node.js Express前端服务

FROM node:18-slim

WORKDIR /app

# 复制package文件并安装依赖
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then \
        npm ci; \
    else \
        npm install; \
    fi

# 复制应用代码
COPY . .

# 复制KLineChart库文件到public/lib（postinstall会自动执行，但确保执行）
RUN npm run copy-assets || echo "KLineChart files will be served from node_modules"

EXPOSE 3000

# 启动前端服务器
CMD ["npm", "start"]
