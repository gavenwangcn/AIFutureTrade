# 前端服务说明

## 目录结构

```
frontend/
├── Dockerfile              # Docker构建文件
├── package.json            # Node.js依赖配置
├── server.js               # Express服务器入口文件
├── README.md               # 本文件
├── scripts/                # 构建脚本目录
│   ├── copy-klinecharts.js      # 复制KLineChart库脚本
│   └── sync-static-assets.js    # 同步静态资源脚本
└── public/                 # 静态文件目录（对外提供服务）
    ├── index.html          # 前端页面入口
    ├── app.js              # 前端JavaScript代码
    ├── style.css           # 样式文件
    ├── favicon.svg         # 网站图标
    └── lib/                # 第三方库目录（KLineChart等）
        └── klinecharts.min.js
```

## 功能说明

### 1. Express服务器 (`server.js`)
- 提供静态文件服务（CSS、JS、图片等）
- 代理API请求到后端服务（`/api/*` → `http://backend:5002/api/*`）
- 代理WebSocket请求（`/socket.io/*` → `http://backend:5002/socket.io/*`）
- 提供KLineChart库文件服务（`/lib/*`）

### 2. 构建脚本 (`scripts/`)

#### `sync-static-assets.js`
- 从项目根目录的 `static/` 目录同步静态资源到 `public/`
- 同步的文件：`style.css`、`favicon.svg`
- 支持多个路径查找（本地开发、Docker构建）

#### `copy-klinecharts.js`
- 从 `node_modules/klinecharts/dist/` 复制KLineChart库文件到 `public/lib/`
- 确保KLineChart库文件可用于前端服务

### 3. 静态资源 (`public/`)
- `index.html`: 前端页面入口，包含所有HTML结构
- `app.js`: 前端JavaScript逻辑，包括K线图管理、WebSocket通信等
- `style.css`: 页面样式文件
- `favicon.svg`: 网站图标

## 开发指南

### 本地开发

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 启动开发服务器（端口3000）
npm run dev
# 或
npm start
```

### 构建静态资源

```bash
# 同步静态资源
npm run sync-static

# 复制KLineChart库
npm run copy-assets

# 或执行完整构建
npm run build
```

### 环境变量

- `FRONTEND_PORT`: 前端服务端口（默认3000）
- `BACKEND_URL`: 后端API地址（默认http://localhost:5002）

## Docker构建

### 构建镜像

```bash
# 从项目根目录构建
docker build -f frontend/Dockerfile -t aifuturetrade-frontend .

# 或使用docker-compose
docker-compose build frontend
```

### 运行容器

```bash
# 使用docker-compose（推荐）
docker-compose up -d frontend

# 或直接运行
docker run -p 3000:3000 \
  -e BACKEND_URL=http://backend:5002 \
  -e FRONTEND_PORT=3000 \
  aifuturetrade-frontend
```

## 注意事项

1. **构建上下文**: Docker构建时使用项目根目录作为构建上下文，以便访问 `static/` 目录
2. **静态资源同步**: 构建时会自动同步 `static/` 目录的文件到 `public/`
3. **KLineChart库**: 优先使用 `public/lib/` 中的文件，如果不存在则从 `node_modules` 提供
4. **路由处理**: 所有非静态资源的请求都会返回 `index.html`（用于前端路由）

## 故障排查

### 样式丢失
- 检查 `public/style.css` 文件是否存在
- 运行 `npm run sync-static` 同步静态资源

### KLineChart加载失败
- 检查 `public/lib/klinecharts.min.js` 文件是否存在
- 运行 `npm run copy-assets` 复制KLineChart库
- 检查服务器日志中的文件检查结果

### API请求失败
- 检查 `BACKEND_URL` 环境变量是否正确
- 确认后端服务是否运行
- 查看浏览器控制台的网络请求

