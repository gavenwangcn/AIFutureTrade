# 前后端分离架构说明

## 架构概述

本项目采用前后端分离架构：

- **前端服务**：Node.js + Express（端口3000）
  - 提供静态文件服务
  - 代理API请求到后端
  - 使用本地npm安装的KLineChart库（不使用CDN）

- **后端服务**：Python Flask（端口5002）
  - 提供RESTful API
  - WebSocket实时数据推送
  - 数据库操作

## 目录结构

```
AIFutureTrade/
├── frontend/              # 前端项目（Node.js）
│   ├── Dockerfile        # 前端Dockerfile
│   ├── package.json      # 前端依赖
│   ├── server.js         # Express服务器
│   ├── scripts/          # 构建脚本
│   │   └── copy-klinecharts.js
│   └── public/           # 静态文件目录
│       ├── index.html    # 前端页面
│       ├── app.js        # 前端JavaScript
│       ├── style.css     # 样式文件
│       ├── favicon.svg   # 图标
│       └── lib/          # KLineChart库（npm安装后复制）
├── Dockerfile            # 后端Dockerfile
├── docker-compose.yml    # Docker Compose配置
└── app.py                # Flask后端应用
```

## 快速开始

### 方式一：使用Docker Compose（推荐）

```bash
# 启动所有服务（前后端分离）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f frontend
docker-compose logs -f backend
```

访问：
- 前端：http://localhost:3000
- 后端API：http://localhost:5002

### 方式二：本地开发

#### 前端开发

```bash
cd frontend

# 安装依赖
npm install

# 启动前端开发服务器
npm run dev
```

前端服务器会自动：
- 提供静态文件服务（public目录）
- 代理 `/api/*` 请求到后端（http://localhost:5002）
- 代理 `/socket.io/*` WebSocket请求到后端
- 提供KLineChart库文件（从node_modules或public/lib）

#### 后端开发

```bash
# 安装Python依赖
pip install -r requirements.txt

# 启动后端服务
python app.py
```

## KLineChart库配置

### 安装

KLineChart库通过npm安装，不使用CDN：

```bash
cd frontend
npm install klinecharts
```

### 自动复制

安装依赖后，`postinstall`脚本会自动将KLineChart库文件复制到`public/lib/`目录：

```bash
npm run copy-assets
```

### 文件服务

前端服务器会优先从`public/lib/`提供KLineChart库文件，如果不存在则从`node_modules/klinecharts/dist/`提供。

## API代理配置

前端服务器会自动代理以下请求到后端：

- `/api/*` → `http://backend:5002/api/*`
- `/socket.io/*` → `http://backend:5002/socket.io/*`

## CORS配置

后端已配置CORS，允许以下前端地址访问：

- `http://localhost:3000`
- `http://frontend:3000`（Docker网络）
- `http://127.0.0.1:3000`

## 环境变量

### 前端环境变量

- `FRONTEND_PORT`: 前端服务端口（默认3000）
- `BACKEND_URL`: 后端API地址（默认http://localhost:5002）

### 后端环境变量

- `DATABASE_PATH`: 数据库路径
- `USE_GUNICORN`: 是否使用Gunicorn
- `FLASK_ENV`: Flask环境（production/development）

## Docker网络

所有服务在同一个Docker网络中（`aifuturetrade-network`），服务间可以通过服务名访问：

- 前端访问后端：`http://backend:5002`
- 后端访问前端：`http://frontend:3000`（如果需要）

## 开发建议

1. **前端开发**：修改`frontend/public/`目录下的文件，前端服务器会自动重载
2. **后端开发**：修改Python文件后需要重启后端服务
3. **KLineChart更新**：修改KLineChart版本后运行`npm run copy-assets`更新库文件

## 故障排查

### KLineChart库加载失败

1. 检查`frontend/public/lib/`目录是否存在文件
2. 运行`npm run copy-assets`手动复制文件
3. 检查`frontend/server.js`中的文件服务配置

### API代理失败

1. 检查后端服务是否运行：`docker-compose ps backend`
2. 检查`BACKEND_URL`环境变量是否正确
3. 查看前端日志：`docker-compose logs frontend`

### WebSocket连接失败

1. 检查后端SocketIO配置
2. 检查前端WebSocket代理配置
3. 查看浏览器控制台错误信息

