# 生产环境部署说明

## 概述

生产环境使用高性能静态文件服务器，不再使用 `vite preview`（预览模式，不适合生产环境）。

## 方案对比

### 方案1：Nginx（推荐）⭐

**优势**：
- ✅ 性能最佳，专门为静态文件服务优化
- ✅ 内存占用小（~10MB）
- ✅ 支持 gzip 压缩
- ✅ 支持缓存策略
- ✅ 生产环境标准选择
- ✅ 支持反向代理（如需要）

**使用方式**：
```bash
# 使用默认 Dockerfile（已配置 nginx）
docker compose build frontend
docker compose up -d frontend
```

### 方案2：Node.js + serve（已移除）

**注意**：此方案已移除，生产环境统一使用 Nginx 方案。

## 性能对比

| 指标 | vite preview | serve | nginx |
|------|-------------|-------|-------|
| 内存占用 | ~150MB | ~50MB | ~10MB |
| 并发处理 | 中等 | 良好 | 优秀 |
| 静态文件性能 | 中等 | 良好 | 优秀 |
| 压缩支持 | ❌ | ✅ | ✅ |
| 缓存策略 | 基础 | 良好 | 优秀 |
| 生产环境适用性 | ❌ | ✅ | ✅✅ |

## Nginx 配置说明

### 主要特性

1. **Gzip 压缩**：自动压缩文本文件，减少传输大小
2. **缓存策略**：
   - 静态资源（JS/CSS/图片）：缓存1年
   - HTML 文件：不缓存
3. **SPA 路由支持**：所有路由返回 `index.html`
4. **健康检查**：`/health` 端点用于容器健康检查

### 自定义配置

如需修改配置，编辑 `frontend/nginx.conf`：

```nginx
# 修改端口
listen 3000;

# 修改缓存时间
expires 1y;  # 1年
expires 7d;  # 7天
```

## 环境变量

### Nginx 版本

Nginx 配置是静态的，如需动态配置，可以使用环境变量替换：

```dockerfile
# 在 Dockerfile 中使用 envsubst
RUN envsubst < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf
```

### Node.js + serve 版本（已移除）

**注意**：此方案已移除，生产环境统一使用 Nginx 方案。

## 监控和日志

### Nginx

```bash
# 查看 Nginx 日志
docker logs frontend

# 查看访问日志（如果启用）
docker exec frontend cat /var/log/nginx/access.log
```


## 健康检查

### Docker Compose 配置

```yaml
services:
  frontend:
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

## 性能优化建议

1. **使用 Nginx**：性能最佳
2. **启用 Gzip**：已默认启用
3. **配置 CDN**：将静态资源放到 CDN
4. **HTTP/2**：Nginx 支持 HTTP/2（需要 SSL）
5. **缓存策略**：已配置合理的缓存策略

## 故障排除

### Nginx 启动失败

```bash
# 检查配置文件语法
docker exec frontend nginx -t

# 查看错误日志
docker logs frontend
```


## 迁移说明

### 从 vite preview 迁移

1. **使用 Nginx（推荐）**：
   - 无需修改，直接使用新的 Dockerfile
   - 构建和运行方式不变


### 验证部署

```bash
# 1. 构建镜像
docker compose build frontend

# 2. 启动服务
docker compose up -d frontend

# 3. 检查健康状态
curl http://localhost:3000/health

# 4. 访问应用
curl http://localhost:3000
```

## 推荐配置

**生产环境**：使用 Nginx（默认 Dockerfile，推荐）

**开发环境**：使用 `npm run dev` 启动 Vite 开发服务器

