# Docker 安装脚本使用说明

## 概述

`install-docker-ubuntu22.sh` 是一个自动化脚本，用于在 Ubuntu 22.04 系统上安装 Docker Engine 和 Docker Compose。

## 功能特性

- ✅ 自动检测系统版本
- ✅ 卸载旧版本的 Docker（如果存在）
- ✅ 安装最新版本的 Docker Engine
- ✅ 安装 Docker Compose（Plugin 版本和独立版本）
- ✅ 配置 Docker daemon
- ✅ 自动将当前用户添加到 docker 组
- ✅ 验证安装是否成功
- ✅ 彩色输出，易于阅读

## 使用方法

### 1. 下载脚本

```bash
# 如果脚本已存在，跳过此步
cd /path/to/AIFutureTrade
```

### 2. 赋予执行权限

```bash
chmod +x scripts/install-docker-ubuntu22.sh
```

### 3. 运行安装脚本

```bash
sudo ./scripts/install-docker-ubuntu22.sh
```

## 安装过程

脚本会执行以下步骤：

1. **检查系统版本** - 验证是否为 Ubuntu 22.04
2. **更新系统包** - 更新 apt 包列表并升级系统
3. **卸载旧版本** - 移除可能存在的旧版本 Docker
4. **安装依赖** - 安装必要的系统依赖包
5. **添加 GPG 密钥** - 添加 Docker 官方 GPG 密钥
6. **添加仓库** - 添加 Docker 官方 apt 仓库
7. **安装 Docker Engine** - 安装 Docker CE 及相关组件
8. **安装 Docker Compose** - 安装 Docker Compose Plugin 和独立版本
9. **启动服务** - 启动 Docker 服务并设置为开机自启
10. **配置 Docker** - 创建 Docker daemon 配置文件
11. **添加用户到组** - 将当前用户添加到 docker 组
12. **验证安装** - 运行测试容器验证安装

## 安装后操作

### 重新登录或刷新组权限

安装完成后，需要重新登录或运行以下命令以使 docker 组权限生效：

```bash
newgrp docker
```

### 验证安装

```bash
# 检查 Docker 版本
docker --version

# 检查 Docker Compose 版本
docker compose version

# 或（如果使用独立版本）
docker-compose --version

# 运行测试容器
docker run hello-world

# 查看 Docker 信息
docker info
```

## 卸载 Docker

如果需要卸载 Docker，可以运行以下命令：

```bash
# 停止 Docker 服务
sudo systemctl stop docker

# 卸载 Docker 包
sudo apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 删除 Docker 数据（可选，会删除所有镜像、容器、卷等）
sudo rm -rf /var/lib/docker
sudo rm -rf /var/lib/containerd

# 删除配置文件
sudo rm -rf /etc/docker
sudo rm -rf /etc/apt/keyrings/docker.gpg
sudo rm -f /etc/apt/sources.list.d/docker.list
```

## 故障排除

### 问题1: 权限 denied

**错误信息**: `permission denied while trying to connect to the Docker daemon socket`

**解决方法**:
```bash
# 将用户添加到 docker 组
sudo usermod -aG docker $USER

# 重新登录或运行
newgrp docker
```

### 问题2: Docker 服务无法启动

**解决方法**:
```bash
# 检查 Docker 服务状态
sudo systemctl status docker

# 查看 Docker 日志
sudo journalctl -u docker

# 重启 Docker 服务
sudo systemctl restart docker
```

### 问题3: 无法连接到 Docker Hub / `pull access denied` / `insufficient_scope`

典型日志：`failed to resolve source metadata for docker.io/library/...`、`authorization failed`、`insufficient_scope`。常见原因：**匿名拉取被限流**、**访问 docker.io 不稳定（含国内机房）**、**镜像加速源失效或未配置**。

**优先尝试（任选其一或组合）**：

1. **登录 Docker Hub（提高匿名拉取额度）**
   ```bash
   docker login docker.io
   # 无账号可注册 https://hub.docker.com/ 后使用 Personal Access Token 作为密码
   ```

2. **配置 registry 镜像（中国大陆服务器强烈建议）**  
   公开镜像地址会变更，请以当前可用源为准（如云厂商「容器镜像服务」文档）。示例结构：
   ```bash
   sudo mkdir -p /etc/docker
   sudo tee /etc/docker/daemon.json <<-'EOF'
   {
     "registry-mirrors": [
       "https://<你的加速器地址>"
     ]
   }
   EOF
   sudo systemctl daemon-reload
   sudo systemctl restart docker
   ```
   配置后执行：`docker pull hello-world` 验证。

3. **用环境变量换基础镜像（不改 Dockerfile）**  
   仓库根目录 `.env` 或 shell 中设置（示例域名需换成你环境可用的镜像站）：
   ```bash
   export NODE_IMAGE=docker.m.daocloud.io/library/node:22-bookworm-slim
   export NGINX_IMAGE=docker.m.daocloud.io/library/nginx:alpine
   export PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.11-slim
   docker compose build frontend trade
   ```
   `docker-compose.yml` 已将 **`NODE_IMAGE` / `NGINX_IMAGE`** 传给 `frontend`，**`PYTHON_IMAGE`** 传给 **`trade`**（默认 `python:3.11-slim`）。其余服务仍依赖 `maven:`、`eclipse-temurin:` 等，需 **daemon 级镜像加速** 或 **能访问 docker.io**。

4. **BuildKit 拉取 `docker/dockerfile:1` 失败**（如 `trade-monitor` 构建）  
   与拉取普通基础镜像相同：配置镜像加速或 `docker login` 后重试；或确保 `DOCKER_BUILDKIT=1` 且网络可访问 docker.io。

**网络自检**：
```bash
ping -c 2 registry-1.docker.io
curl -sI https://registry-1.docker.io/v2/
```

### 问题4: 系统版本不匹配

**解决方法**:
脚本会检测系统版本，如果不是 Ubuntu 22.04，会提示是否继续。如果确定要继续，输入 `y` 即可。

## 系统要求

- Ubuntu 22.04 LTS (推荐)
- 64 位系统
- 至少 2GB RAM
- 至少 20GB 可用磁盘空间
- 具有 sudo 权限的用户

## 注意事项

1. ⚠️ 此脚本需要 root 权限，请使用 `sudo` 运行
2. ⚠️ 安装过程会卸载旧版本的 Docker（如果存在）
3. ⚠️ 安装完成后需要重新登录或运行 `newgrp docker` 才能无需 sudo 使用 docker 命令
4. ⚠️ 如果系统不是 Ubuntu 22.04，脚本会提示确认，请谨慎操作

## 相关资源

- [Docker 官方文档](https://docs.docker.com/)
- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Ubuntu 安装 Docker 指南](https://docs.docker.com/engine/install/ubuntu/)

