# Docker Socket 配置说明

## 问题描述

当 backend 服务在 Docker 容器中运行时，需要访问宿主机的 Docker socket 来查询其他容器的日志。错误信息：
```
unix://localhost:2375
No such file or directory
```

## 解决方案

### 1. 在 docker-compose.yml 中挂载 Docker Socket

已在 `docker-compose.yml` 中添加 volumes 挂载：

```yaml
backend:
  volumes:
    # 挂载Docker socket，允许backend容器访问宿主机Docker来查询其他容器日志
    - /var/run/docker.sock:/var/run/docker.sock:ro
```

### 2. 权限配置

确保 backend 容器有权限访问 Docker socket：

**方法1：使用 docker 用户组（推荐）**

在 Dockerfile 中添加用户组配置：

```dockerfile
# 安装必要的工具
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 创建 docker 用户组（GID 通常为 999，但可能因系统而异）
# 注意：这里不创建用户，只是确保容器可以访问socket
# 实际权限由挂载的socket文件决定
```

**方法2：在 docker-compose.yml 中设置用户**

```yaml
backend:
  user: "0:999"  # root用户，docker组（GID可能不同，需要根据实际情况调整）
```

**方法3：确保宿主机 socket 权限**

在宿主机上检查并设置权限：

```bash
# 检查 socket 权限
ls -l /var/run/docker.sock

# 如果需要，添加 docker 组
sudo groupadd docker
sudo usermod -aG docker $USER

# 检查 docker 组 GID
getent group docker
```

### 3. 验证配置

**步骤1：重启 backend 容器**

```bash
# 停止并重新启动 backend 容器
docker-compose stop backend
docker-compose up -d backend

# 或重建容器
docker-compose up -d --build backend
```

**步骤2：检查 socket 挂载**

```bash
# 进入 backend 容器
docker exec -it aifuturetrade-backend sh

# 在容器内检查 socket 文件
ls -l /var/run/docker.sock

# 测试 Docker 命令（如果容器内有 docker 客户端）
docker ps
```

**步骤3：检查应用日志**

查看 backend 启动日志，确认 Docker 连接成功：

```bash
docker logs aifuturetrade-backend | grep -i docker
```

应该看到：
```
Docker客户端配置 - Host: unix:///var/run/docker.sock
Docker连接测试成功
Docker日志服务初始化成功
```

### 4. 常见问题

**问题1：权限被拒绝**

错误：`Permission denied` 或 `Access denied`

解决：
```bash
# 检查宿主机 socket 权限
ls -l /var/run/docker.sock
# 应该显示：srw-rw---- 1 root docker

# 如果权限不对，调整权限（谨慎操作）
sudo chmod 666 /var/run/docker.sock
# 或
sudo chown root:docker /var/run/docker.sock
```

**问题2：Socket 文件不存在**

错误：`No such file or directory`

解决：
```bash
# 检查 Docker 服务是否运行
sudo systemctl status docker

# 检查 socket 文件
ls -l /var/run/docker.sock

# 如果不存在，重启 Docker 服务
sudo systemctl restart docker
```

**问题3：容器内无法访问 socket**

解决：
1. 确认 docker-compose.yml 中已添加 volumes 挂载
2. 确认挂载路径正确：`/var/run/docker.sock:/var/run/docker.sock:ro`
3. 重启容器使配置生效

### 5. 安全注意事项

⚠️ **重要安全提示**：

挂载 Docker socket 到容器内会授予容器访问宿主机 Docker 的完整权限，这是一个安全风险。建议：

1. **使用只读挂载**：已使用 `:ro` 标志，限制为只读访问
2. **限制容器网络**：确保容器在隔离的网络中
3. **定期更新**：保持 Docker 和容器镜像更新
4. **监控访问**：监控容器对 Docker socket 的访问

### 6. 配置验证清单

- [ ] docker-compose.yml 中已添加 volumes 挂载
- [ ] 挂载路径为 `/var/run/docker.sock:/var/run/docker.sock:ro`
- [ ] 宿主机 Docker socket 文件存在且权限正确
- [ ] backend 容器已重启并应用新配置
- [ ] 应用日志显示 Docker 连接成功
- [ ] 可以成功查询目标容器（aifuturetrade-trade）

### 7. 测试命令

```bash
# 1. 检查容器内 socket
docker exec aifuturetrade-backend ls -l /var/run/docker.sock

# 2. 检查应用日志
docker logs aifuturetrade-backend --tail 50 | grep -i docker

# 3. 测试容器查询（如果容器内有 docker 客户端）
docker exec aifuturetrade-backend docker ps --filter "name=aifuturetrade-trade"

# 4. 检查目标容器
docker ps --filter "name=aifuturetrade-trade"
```

