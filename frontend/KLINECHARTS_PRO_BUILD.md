# KLineCharts-Pro 自定义构建说明

## 问题分析

您遇到的问题是：在 `KLineChartPro.tsx` (44-72行) 中定义的自定义默认配置（periods, mainIndicators, subIndicators）在前端页面不生效。

**根本原因**：
1. `KLineChart.vue` 使用 ES6 模块导入 `@klinecharts/pro`，可能指向 npm 官方包，而不是本地自定义构建的版本
2. 前端服务没有使用构建的自定义 klinecharts-pro 模块

## 解决方案

已修改代码以支持 **UMD 方式**引入自定义构建的 klinecharts-pro 模块。

### Docker 构建环境（生产环境）

**重要**：真实打包环境使用 Docker 镜像（`node:20-slim` 基础镜像），所有构建流程都在 Dockerfile 中自动完成。

#### Dockerfile 构建流程

1. **阶段1：构建 klinecharts-pro 基础库**
   - 在 `klinecharts-pro-builder` 阶段构建自定义 klinecharts-pro
   - 生成 `dist/klinecharts-pro.umd.js` 和 `dist/klinecharts-pro.css`

2. **阶段2：构建前端应用**
   - 从 `klinecharts-pro-builder` 复制构建产物到 `klinecharts-pro-build/`
   - 安装前端依赖（包括 klinecharts）
   - 将自定义构建的包复制到 `node_modules/@klinecharts/pro/`
   - 将 klinecharts 基础库复制到 `public/klinecharts-pro/klinecharts.js`
   - 将自定义构建的 klinecharts-pro 复制到 `public/klinecharts-pro/`
   - 运行 `npm run build`，Vite 会自动将 `public/` 目录内容复制到 `dist/`

3. **阶段3：运行环境**
   - 从 `frontend-builder` 复制 `dist/` 目录到运行镜像
   - 使用 `vite preview` 提供静态文件服务

#### 文件路径说明

- **构建时**：文件在 `public/klinecharts-pro/` 目录
- **构建后**：Vite 将 `public/` 内容复制到 `dist/klinecharts-pro/`
- **运行时**：通过 `/klinecharts-pro/` 路径访问（相对于 dist 根目录）

### 本地开发环境（可选）

如果您想在本地开发环境中测试，需要手动构建和复制文件：

```bash
# 1. 构建 klinecharts-pro
cd frontend/klinecharts-pro
npm install
npm run build

# 2. 复制文件到 public 目录（Linux/Mac）
cd ../..
mkdir -p frontend/public/klinecharts-pro
cp frontend/klinecharts-pro/dist/klinecharts-pro.umd.js frontend/public/klinecharts-pro/
cp frontend/klinecharts-pro/dist/klinecharts-pro.css frontend/public/klinecharts-pro/
cp frontend/node_modules/klinecharts/dist/umd/klinecharts.js frontend/public/klinecharts-pro/

# 3. 验证文件存在
ls -lh frontend/public/klinecharts-pro/
```

**注意**：本地开发环境仅用于测试，生产环境必须使用 Docker 构建。

### 代码修改说明

#### index.html
已添加 script 标签引入 UMD 版本（适配 Docker 构建环境）：
```html
<!-- 引入 klinecharts 基础库 -->
<!-- 文件由 Dockerfile 构建时从 node_modules 复制到 public/klinecharts-pro/ -->
<script src="/klinecharts-pro/klinecharts.js"></script>

<!-- 引入自定义构建的 klinecharts-pro -->
<!-- 文件由 Dockerfile 构建时从 klinecharts-pro/dist/ 复制到 public/klinecharts-pro/ -->
<script src="/klinecharts-pro/klinecharts-pro.umd.js"></script>
```

**注意**：移除了 `onerror` 回退机制，因为：
- Docker 构建环境已确保文件存在
- 运行时环境（vite preview）只有 `dist/` 目录，没有 `node_modules`
- 文件路径 `/klinecharts-pro/...` 在构建后指向 `dist/klinecharts-pro/...`

#### KLineChart.vue
已修改为支持 UMD 和 ES6 模块两种方式：
- 优先使用全局变量 `window.klinechartspro.KLineChartPro`（UMD 方式，自定义构建）
- 如果不存在，则回退到 ES6 模块导入（开发环境 fallback）

### 自定义配置生效

当使用 UMD 方式引入自定义构建的 klinecharts-pro 时，`KLineChartPro.tsx` 中的默认配置会生效：

```typescript
// frontend/klinecharts-pro/src/KLineChartPro.tsx (44-72行)
periods={
  options.periods ?? [
    { multiplier: 1, timespan: 'minute', text: '1m' },
    { multiplier: 5, timespan: 'minute', text: '5m' },
    { multiplier: 15, timespan: 'minute', text: '15m' },
    { multiplier: 1, timespan: 'hour', text: '1h' },
    { multiplier: 4, timespan: 'hour', text: '4h' },
    { multiplier: 1, timespan: 'day', text: '1d' },
    { multiplier: 1, timespan: 'week', text: '1w' }
  ]
}
mainIndicators={options.mainIndicators ?? ['MA']}
subIndicators={options.subIndicators ?? ['MA', 'RSI', 'MACD', 'VOL']}
```

这些默认值会在创建 `KLineChartPro` 实例时自动应用（如果未在选项中指定）。

## 构建和部署

### Docker 构建（生产环境）

```bash
# 从项目根目录构建
docker compose build frontend

# 或直接启动（会自动构建）
docker compose up -d frontend
```

Dockerfile 会自动：
1. 构建 klinecharts-pro 模块
2. 复制所有必需文件到 `public/klinecharts-pro/`
3. 构建前端应用（Vite 会将 public 内容复制到 dist）
4. 验证所有文件存在

### 验证构建结果

在 Docker 构建日志中应看到：
```
✓ All klinecharts-pro files are present:
-rw-r--r-- ... klinecharts.js
-rw-r--r-- ... klinecharts-pro.css
-rw-r--r-- ... klinecharts-pro.umd.js
```

### 运行时验证

启动容器后，在浏览器控制台应看到：
```
[KLineChart] Using UMD version of klinecharts-pro (custom build)
```

如果看到 `[KLineChart] Using ES6 module version of klinecharts-pro`，说明 UMD 文件未正确加载，需要检查：
1. Docker 构建日志中文件是否成功复制
2. 浏览器 Network 面板中 `/klinecharts-pro/` 路径的文件是否成功加载

## 故障排除

### 问题：控制台显示 "klinecharts-pro is not available"

**解决方案**：
1. 检查 `public/klinecharts-pro/klinecharts-pro.umd.js` 是否存在
2. 检查浏览器 Network 面板，确认文件加载成功
3. 检查浏览器控制台是否有 JavaScript 错误

### 问题：自定义配置不生效

**解决方案**：
1. 确认使用的是 UMD 版本（检查控制台日志）
2. 确认构建的 klinecharts-pro 包含最新的自定义配置
3. 清除浏览器缓存并重新加载

### 问题：构建失败

**解决方案**：
1. 检查 `frontend/klinecharts-pro/package.json` 中的依赖是否已安装
2. 检查 `node_modules` 目录是否存在
3. 运行 `npm install` 重新安装依赖

## 验证自定义配置

在浏览器控制台检查：
```javascript
// 应该能看到全局变量
console.log(window.klinechartspro)

// 创建实例时，默认配置应该生效
// 检查 periods, mainIndicators, subIndicators 是否使用默认值
```

