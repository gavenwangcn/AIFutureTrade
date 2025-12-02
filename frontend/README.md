# AIFutureTrade 前端服务

## 概述

前端服务使用 Node.js Express 提供静态文件服务和 API/WebSocket 代理。

## 快速开始

### 本地开发

1. **安装依赖**（必须）：
   ```bash
   cd frontend
   npm install
   ```
   
   这会自动安装 `klinecharts` 等依赖，并执行 `postinstall` 脚本复制 KLineChart 库文件。

2. **验证 KLineChart 安装**：
   ```bash
   # 检查 node_modules 中是否有 klinecharts
   ls node_modules/klinecharts/dist/
   
   # 检查是否已复制到 public/lib
   ls public/lib/klinecharts.min.js
   ```

3. **手动复制 KLineChart 文件**（如果需要）：
   ```bash
   npm run copy-assets
   ```

4. **启动开发服务器**：
   ```bash
   npm start
   # 或
   npm run dev
   ```

### Docker 构建

Dockerfile 会自动处理依赖安装和文件复制：

```bash
# 从项目根目录构建
docker compose build frontend

# 或直接启动（会自动构建）
docker compose up -d frontend
```

## KLineChart 库文件

根据 [KLineChart 官方文档](https://klinecharts.com/guide/quick-start)，KLineChart 需要通过 npm 安装：

```bash
npm install klinecharts
```

### 文件位置

- **源文件**：`node_modules/klinecharts/dist/klinecharts.min.js`
- **复制目标**：`public/lib/klinecharts.min.js`
- **备用位置**：如果复制失败，`server.js` 会从 `node_modules` 直接提供文件

### 文件复制脚本

`scripts/copy-klinecharts.js` 脚本会：
1. 检查 `node_modules/klinecharts/dist/` 是否存在
2. 创建 `public/lib/` 目录（如果不存在）
3. 复制所有文件到 `public/lib/`

### 故障排除

如果 `klinecharts.min.js` 文件无法加载：

1. **检查依赖是否安装**：
   ```bash
   cd frontend
   npm install
   ```

2. **检查文件是否存在**：
   ```bash
   # 检查源文件
   ls node_modules/klinecharts/dist/klinecharts.min.js
   
   # 检查复制后的文件
   ls public/lib/klinecharts.min.js
   ```

3. **手动复制文件**：
   ```bash
   npm run copy-assets
   ```

4. **检查服务器日志**：
   - 启动时会显示 KLineChart 文件位置
   - 如果文件不存在，会显示警告信息

5. **Docker 环境**：
   ```bash
   # 检查容器内文件
   docker exec aifuturetrade-frontend ls -la /app/public/lib/
   docker exec aifuturetrade-frontend ls -la /app/node_modules/klinecharts/dist/
   ```

## 项目结构

```
frontend/
├── public/              # 静态文件目录
│   ├── index.html      # 主HTML文件
│   ├── app.js          # 前端应用JavaScript
│   ├── style.css       # 样式文件
│   └── lib/            # KLineChart库文件（由脚本复制）
│       └── klinecharts.min.js
├── scripts/            # 构建脚本
│   ├── copy-klinecharts.js      # 复制KLineChart文件
│   └── sync-static-assets.js   # 同步静态资源
├── server.js           # Express服务器
├── package.json        # npm配置
└── Dockerfile          # Docker构建文件
```

## 环境变量

- `FRONTEND_PORT`: 前端服务端口（默认：3000）
- `BACKEND_URL`: 后端API地址（默认：http://localhost:5002）

## 脚本说明

- `npm start`: 启动服务器
- `npm run dev`: 启动开发服务器（同 start）
- `npm run build`: 同步静态资源并复制KLineChart文件
- `npm run sync-static`: 同步静态资源（从 static/ 到 public/）
- `npm run copy-assets`: 复制KLineChart库文件
- `npm run install-deps`: 安装依赖

## 注意事项

1. **必须运行 `npm install`**：KLineChart 需要通过 npm 安装，不能直接从 CDN 使用（根据项目要求）
2. **postinstall 脚本**：安装依赖后会自动执行文件复制
3. **备用方案**：如果文件复制失败，`server.js` 会从 `node_modules` 直接提供文件
4. **Docker 构建**：Dockerfile 会确保依赖安装和文件复制正确执行
