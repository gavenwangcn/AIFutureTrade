# Dockerfile.nodejs 使用说明

## 文件用途

`Dockerfile.nodejs` 是默认 `Dockerfile`（使用 nginx）的**备选方案**，使用 **Node.js + serve** 包来提供静态文件服务。

## 两个 Dockerfile 的区别

| 特性 | Dockerfile (默认) | Dockerfile.nodejs |
|------|------------------|-------------------|
| **运行环境** | nginx:alpine | node:20-slim |
| **静态文件服务器** | nginx | serve 包 |
| **内存占用** | ~10MB | ~50MB |
| **性能** | ⭐⭐⭐⭐⭐ 最佳 | ⭐⭐⭐⭐ 良好 |
| **适用场景** | 生产环境（推荐） | 需要 Node.js 环境时 |
| **配置复杂度** | 需要 nginx.conf | 简单，命令行参数 |

## 使用场景

### 适合使用 Dockerfile.nodejs 的情况：

1. ✅ **需要 Node.js 环境**：如果后续需要在容器中运行 Node.js 脚本
2. ✅ **开发/测试环境**：对性能要求不是特别高
3. ✅ **不想使用 nginx**：团队不熟悉 nginx 配置
4. ✅ **需要动态配置**：serve 支持环境变量配置

### 推荐使用默认 Dockerfile (nginx) 的情况：

1. ✅ **生产环境**：性能要求高
2. ✅ **资源受限**：内存占用要求低
3. ✅ **高并发**：需要处理大量并发请求
4. ✅ **标准部署**：nginx 是生产环境标准选择

## 使用方法

### 方法1：修改 docker-compose.yml（推荐）

在 `docker-compose.yml` 中指定使用 `Dockerfile.nodejs`：

```yaml
frontend:
  build:
    context: .
    dockerfile: ./frontend/Dockerfile.nodejs  # 指定使用 Node.js 版本
  container_name: aifuturetrade-frontend
  ports:
    - "3000:3000"
  # ... 其他配置
```

然后构建和启动：

```bash
docker compose build frontend
docker compose up -d frontend
```

### 方法2：直接使用 docker build

```bash
# 从项目根目录构建
docker build -f frontend/Dockerfile.nodejs -t aifuturetrade-frontend:nodejs .

# 运行容器
docker run -d \
  --name aifuturetrade-frontend \
  -p 3000:3000 \
  aifuturetrade-frontend:nodejs
```

### 方法3：临时测试

```bash
# 构建并立即运行（用于测试）
docker build -f frontend/Dockerfile.nodejs -t frontend-test .
docker run --rm -p 3000:3000 frontend-test
```

## serve 包说明

`serve` 是一个轻量级、高性能的静态文件服务器，专门为单页应用（SPA）设计。

### serve 参数说明

```bash
serve -s dist -l 3000 -n --cors --no-clipboard
```

- `-s dist`: 单页应用模式，所有路由返回 `index.html`
- `-l 3000`: 监听端口 3000
- `-n`: 不显示服务器信息（生产环境）
- `--cors`: 启用 CORS 跨域支持
- `--no-clipboard`: 不复制 URL 到剪贴板

### serve 环境变量

可以通过环境变量配置 serve：

```yaml
frontend:
  environment:
    - PORT=3000          # 监听端口
    - SERVE_SINGLE=true  # SPA 模式
```

## 性能对比

### 内存占用

```bash
# nginx 版本
docker stats aifuturetrade-frontend
# 内存: ~10-15MB

# Node.js + serve 版本
docker stats aifuturetrade-frontend
# 内存: ~50-80MB
```

### 响应时间

- **nginx**: 最快，专门优化
- **serve**: 良好，比 vite preview 快很多
- **vite preview**: 最慢，不适合生产环境

## 完整示例

### 示例1：在 docker-compose.yml 中使用

```yaml
services:
  frontend:
    build:
      context: .
      dockerfile: ./frontend/Dockerfile.nodejs
    container_name: aifuturetrade-frontend
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - PORT=3000
    restart: unless-stopped
    networks:
      - aifuturetrade-network
```

### 示例2：自定义端口

如果需要使用不同的端口，可以修改 Dockerfile.nodejs 的最后一行：

```dockerfile
# 修改端口为 8080
CMD ["serve", "-s", "dist", "-l", "8080", "-n", "--cors", "--no-clipboard"]
```

或者使用环境变量（需要修改 Dockerfile 支持环境变量）：

```dockerfile
# 在 Dockerfile.nodejs 中修改
CMD ["sh", "-c", "serve -s dist -l ${PORT:-3000} -n --cors --no-clipboard"]
```

## 验证部署

### 检查服务是否运行

```bash
# 查看容器状态
docker ps | grep frontend

# 查看日志
docker logs aifuturetrade-frontend

# 测试访问
curl http://localhost:3000
```

### 健康检查

serve 没有内置健康检查端点，但可以访问根路径：

```bash
# 检查服务是否正常
curl -I http://localhost:3000
# 应该返回 200 OK
```

## 故障排除

### 问题1：端口被占用

```bash
# 检查端口占用
netstat -tuln | grep 3000

# 或使用不同端口
docker run -p 8080:3000 aifuturetrade-frontend:nodejs
```

### 问题2：serve 命令未找到

确保 Dockerfile.nodejs 中正确安装了 serve：

```dockerfile
RUN npm install -g serve@14.2.1
```

### 问题3：SPA 路由不工作

确保使用了 `-s` 参数：

```dockerfile
CMD ["serve", "-s", "dist", ...]  # -s 参数启用 SPA 模式
```

## 总结

- **默认 Dockerfile (nginx)**：生产环境推荐，性能最佳
- **Dockerfile.nodejs (serve)**：备选方案，适合需要 Node.js 环境的场景

选择建议：
- 🏆 **生产环境**：使用默认 Dockerfile (nginx)
- 🔧 **开发/测试**：可以使用 Dockerfile.nodejs
- 🎯 **需要 Node.js 环境**：使用 Dockerfile.nodejs

