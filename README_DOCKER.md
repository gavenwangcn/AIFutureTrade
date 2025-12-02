# Docker 部署说明

## 快速开始

### 方式一：使用CDN（推荐，无需Node.js）

直接运行，KLineChart库会从CDN加载：

```bash
docker-compose up -d
```

### 方式二：使用本地构建的前端资源（需要Node.js）

如果需要使用本地构建的KLineChart库（更好的版本控制和离线支持）：

1. **构建前端资源**：
```bash
# 使用docker-compose构建前端
docker-compose --profile build-frontend run --rm frontend-builder

# 或者本地使用npm构建
npm install
npm run copy-assets
```

2. **启动服务**：
```bash
docker-compose up -d
```

## Dockerfile 说明

Dockerfile采用多阶段构建：

1. **前端构建阶段** (`frontend-builder`)：
   - 使用 `node:18-slim` 镜像
   - 安装前端依赖（KLineChart）
   - 将构建好的资源复制到 `static/lib/` 目录

2. **Python应用阶段**：
   - 使用 `python:3.10-slim` 镜像
   - 安装Python依赖
   - 从前端构建阶段复制前端资源
   - 运行Flask应用

## docker-compose 说明

### 服务说明

- **web**: 主Web服务（Flask应用）
- **async-agent**: 后台数据同步服务
- **frontend-builder**: 前端构建服务（可选，使用profile控制）

### 使用Profile构建前端

```bash
# 构建前端资源
docker-compose --profile build-frontend run --rm frontend-builder

# 然后启动所有服务
docker-compose up -d
```

### 开发模式

在开发模式下，可以挂载static目录以便热更新：

```yaml
volumes:
  - ./static:/app/static
```

## 前端资源加载策略

应用会自动检测本地构建的KLineChart库：

1. 优先尝试加载 `/static/lib/klinecharts.min.js`
2. 如果本地文件不存在，自动回退到CDN：`https://unpkg.com/klinecharts@latest/dist/klinecharts.min.js`

这样可以确保：
- 生产环境可以使用本地构建的版本（更好的性能和版本控制）
- 开发环境可以直接使用CDN（无需构建）
- 即使构建失败，也能正常工作（CDN回退）

## 注意事项

1. **Node.js依赖**：只有在需要本地构建前端资源时才需要Node.js
2. **CDN方式**：默认使用CDN，无需Node.js，适合快速部署
3. **本地构建**：适合需要版本控制或离线使用的场景
4. **性能**：本地构建的版本通常加载更快，但需要额外的构建步骤

