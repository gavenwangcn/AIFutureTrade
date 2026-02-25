# AIFutureTrade 前端服务

## 概述

前端服务使用 Vue 3 + Vite 构建。开发环境使用 Vite 开发服务器（支持代理），生产环境使用 Vite 预览服务器或 nginx。

## 🏝️ 环境要求

### 浏览器支持

图表基于 html5 canvas 构建，需要运行在支持 canvas 的浏览器上，如果需要运行在移动端，请用 webview 加载。

### 兼容处理

#### [core.js](https://github.com/zloirock/core-js)

图表内部集合使用 `Map` ，用于兼容不支持的老版浏览器。

```javascript
import 'core.js';
import { init } from 'klinecharts';
```

#### [Intl.js](https://github.com/andyearnshaw/Intl.js)

图表依赖 `Intl` ，某些浏览器无此 API。

```javascript
import 'intl';
import 'intl/local-data/jsonp/en';
import { init } from 'klinecharts';
```

> 参考：[KLineChart 官方环境要求文档](https://klinecharts.com/guide/environment)

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

3. **KLineChart 库**：
   - KLineChart 通过 npm 安装，在 Vue 组件中通过 ES6 import 使用
   - Vite 构建时会自动打包，无需手动复制文件

4. **启动开发服务器**：
   ```bash
   # 开发环境（支持代理）
   npm run dev
   
   # 生产构建 + 预览
   npm run build
   npm run preview
   # 或
   npm start
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
- **使用方式**：通过 npm 安装，在 Vue 组件中通过 ES6 import 使用，Vite 构建时会自动打包

### KLineChart 使用方式

KLineChart 通过 npm 安装后，在 Vue 组件中直接导入使用：
```javascript
import { init, dispose } from 'klinecharts'
```
Vite 构建时会自动打包 klinecharts，无需手动复制文件。

### 故障排除

如果 `klinecharts.min.js` 文件无法加载：

1. **检查依赖是否安装**：
   ```bash
   cd frontend
   npm install
   ```

2. **检查 klinecharts 是否正确安装**：
   ```bash
   # 检查 node_modules 中是否有 klinecharts
   ls node_modules/klinecharts/
   
   # 检查 package.json 中是否包含 klinecharts
   grep klinecharts package.json
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
├── src/                # Vue 组件源代码
│   ├── components/     # Vue 组件
│   ├── composables/    # Vue Composables
│   └── main.js         # 入口文件
├── scripts/            # 构建脚本
│   └── sync-static-assets.js   # 同步静态资源（从 static/ 到 public/）
├── index.html          # HTML 模板
├── vite.config.js      # Vite 配置
├── package.json        # npm配置
└── Dockerfile          # Docker构建文件
```

## 环境变量

### 开发环境
开发环境不需要配置环境变量，Vite 会自动使用代理配置。

### 生产环境
前端和后端默认在同一台机器上运行，使用当前域名+端口5002。

如果需要自定义配置，创建 `.env` 文件（或设置环境变量）：

**方式1：配置完整后端URL**
```env
VITE_BACKEND_URL=http://localhost:5002
# 或
VITE_BACKEND_URL=http://192.168.1.100:5002
```

**方式2：仅配置后端端口（推荐，前端后端同机时）**
```env
VITE_BACKEND_PORT=5002
```

**配置说明**：
- 环境变量必须以 `VITE_` 开头才能在客户端代码中使用
- `VITE_BACKEND_URL`：完整后端地址（优先级最高）
- `VITE_BACKEND_PORT`：仅后端端口，使用当前域名+端口（默认：5002）
- 如果都不设置，生产环境默认使用：`当前域名:5002`
- 修改环境变量后需要重新构建：`npm run build`

## 脚本说明

- `npm run dev`: 启动 Vite 开发服务器（支持代理）
- `npm run build`: 构建生产版本
- `npm run preview`: 预览生产构建（不支持代理）
- `npm start`: 构建并预览生产版本
- `npm run sync-static`: 同步静态资源（从 static/ 到 public/）

## 注意事项

1. **必须运行 `npm install`**：KLineChart 需要通过 npm 安装，不能直接从 CDN 使用（根据项目要求）
2. **postinstall 脚本**：安装依赖后会自动执行文件复制
3. **开发环境**：使用 `npm run dev`，Vite 开发服务器支持代理配置
4. **生产环境**：使用 `npm run build` 构建，然后使用 `npm run preview` 预览，或使用 nginx 提供静态文件服务和反向代理
5. **Docker 构建**：Dockerfile 会确保依赖安装和文件复制正确执行
6. **代理配置**：开发环境的代理配置在 `vite.config.js` 中，生产环境建议使用 nginx 配置反向代理
