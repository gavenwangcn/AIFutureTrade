# Docker 配置验证指南

## 问题说明
错误信息显示：`unix://localhost:2375` 和 `No such file or directory`
这表明在 Windows 系统上尝试使用 Unix socket，但 Windows 不支持 Unix socket。

## 验证步骤

### 1. 检查 Docker 服务是否运行

**Windows:**
```powershell
# 检查 Docker Desktop 是否运行
Get-Process "Docker Desktop" -ErrorAction SilentlyContinue

# 检查 Docker 服务状态
docker version
docker ps
```

**Linux/Mac:**
```bash
# 检查 Docker 服务状态
sudo systemctl status docker
# 或
docker version
docker ps
```

### 2. 检查容器是否存在

```bash
# 查找容器
docker ps -a | grep aifuturetrade-trade

# 或使用名称过滤
docker ps -a --filter "name=aifuturetrade-trade"

# 检查容器是否运行
docker ps --filter "name=aifuturetrade-trade"
```

### 3. 验证 Docker 连接方式

**Windows 系统（使用 TCP 连接）:**
```powershell
# 检查 Docker Desktop 是否启用 TCP 端口
# 默认情况下，Docker Desktop 可能不启用 TCP 端口
# 需要在 Docker Desktop Settings -> General -> Expose daemon on tcp://localhost:2375 without TLS

# 测试 TCP 连接（如果已启用）
curl http://localhost:2375/version
# 或
Invoke-WebRequest -Uri http://localhost:2375/version
```

**Linux/Mac 系统（使用 Unix socket）:**
```bash
# 检查 Unix socket 文件是否存在
ls -l /var/run/docker.sock

# 测试 Unix socket 连接
docker version
```

### 4. 检查应用配置

查看 `application.yml` 中的配置：
```yaml
docker:
  host: ${DOCKER_HOST:unix:///var/run/docker.sock}
  container-name: ${DOCKER_CONTAINER_NAME:aifuturetrade-trade}
```

### 5. 设置正确的环境变量

**Windows 系统（推荐使用 TCP）:**
```powershell
# 方式1：在 application.yml 中配置
# docker:
#   host: tcp://localhost:2375

# 方式2：通过环境变量设置
$env:DOCKER_HOST="tcp://localhost:2375"
```

**Linux/Mac 系统:**
```bash
# 使用默认 Unix socket（通常不需要设置）
# 或通过环境变量设置
export DOCKER_HOST=unix:///var/run/docker.sock
```

## 快速验证脚本

### Windows PowerShell 脚本
```powershell
# verify-docker.ps1
Write-Host "=== Docker 配置验证 ===" -ForegroundColor Green

# 1. 检查操作系统
$os = [System.Environment]::OSVersion.Platform
Write-Host "操作系统: $os" -ForegroundColor Yellow

# 2. 检查 Docker 是否安装
Write-Host "`n检查 Docker 安装..." -ForegroundColor Cyan
try {
    $dockerVersion = docker version --format '{{.Server.Version}}' 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Docker 已安装: $dockerVersion" -ForegroundColor Green
    } else {
        Write-Host "✗ Docker 未安装或未运行" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Docker 命令不可用" -ForegroundColor Red
    exit 1
}

# 3. 检查容器
Write-Host "`n检查容器 aifuturetrade-trade..." -ForegroundColor Cyan
$container = docker ps -a --filter "name=aifuturetrade-trade" --format "{{.Names}}" 2>&1
if ($container -match "aifuturetrade-trade") {
    Write-Host "✓ 容器存在: $container" -ForegroundColor Green
    
    # 检查容器状态
    $status = docker ps --filter "name=aifuturetrade-trade" --format "{{.Status}}" 2>&1
    if ($status) {
        Write-Host "✓ 容器运行中: $status" -ForegroundColor Green
    } else {
        Write-Host "⚠ 容器存在但未运行" -ForegroundColor Yellow
        Write-Host "  启动命令: docker start aifuturetrade-trade" -ForegroundColor Gray
    }
} else {
    Write-Host "✗ 容器不存在" -ForegroundColor Red
    Write-Host "  请检查容器名称配置或创建容器" -ForegroundColor Gray
}

# 4. 检查 Docker 连接方式
Write-Host "`n检查 Docker 连接方式..." -ForegroundColor Cyan
if ($IsWindows -or $env:OS -match "Windows") {
    Write-Host "检测到 Windows 系统" -ForegroundColor Yellow
    Write-Host "推荐配置: docker.host=tcp://localhost:2375" -ForegroundColor Cyan
    Write-Host "注意: 需要在 Docker Desktop 中启用 TCP 端口" -ForegroundColor Yellow
} else {
    Write-Host "检测到 Linux/Mac 系统" -ForegroundColor Yellow
    Write-Host "推荐配置: docker.host=unix:///var/run/docker.sock" -ForegroundColor Cyan
    
    # 检查 Unix socket
    if (Test-Path "/var/run/docker.sock") {
        Write-Host "✓ Unix socket 文件存在" -ForegroundColor Green
    } else {
        Write-Host "✗ Unix socket 文件不存在" -ForegroundColor Red
    }
}

Write-Host "`n=== 验证完成 ===" -ForegroundColor Green
```

### Linux/Mac Bash 脚本
```bash
#!/bin/bash
# verify-docker.sh

echo "=== Docker 配置验证 ==="

# 1. 检查操作系统
echo "操作系统: $(uname -s)"

# 2. 检查 Docker 是否安装
echo -e "\n检查 Docker 安装..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2>&1)
    if [ $? -eq 0 ]; then
        echo "✓ Docker 已安装: $DOCKER_VERSION"
    else
        echo "✗ Docker 未运行"
        exit 1
    fi
else
    echo "✗ Docker 未安装"
    exit 1
fi

# 3. 检查容器
echo -e "\n检查容器 aifuturetrade-trade..."
CONTAINER=$(docker ps -a --filter "name=aifuturetrade-trade" --format "{{.Names}}" 2>&1)
if [[ $CONTAINER == *"aifuturetrade-trade"* ]]; then
    echo "✓ 容器存在: $CONTAINER"
    
    # 检查容器状态
    STATUS=$(docker ps --filter "name=aifuturetrade-trade" --format "{{.Status}}" 2>&1)
    if [ -n "$STATUS" ]; then
        echo "✓ 容器运行中: $STATUS"
    else
        echo "⚠ 容器存在但未运行"
        echo "  启动命令: docker start aifuturetrade-trade"
    fi
else
    echo "✗ 容器不存在"
    echo "  请检查容器名称配置或创建容器"
fi

# 4. 检查 Unix socket
echo -e "\n检查 Unix socket..."
if [ -S "/var/run/docker.sock" ]; then
    echo "✓ Unix socket 文件存在"
    echo "  推荐配置: docker.host=unix:///var/run/docker.sock"
else
    echo "✗ Unix socket 文件不存在"
    echo "  请检查 Docker 服务是否运行"
fi

echo -e "\n=== 验证完成 ==="
```

## 配置修复

### Windows 系统配置

**方法1：修改 application.yml**
```yaml
docker:
  host: tcp://localhost:2375  # Windows 使用 TCP
  container-name: aifuturetrade-trade
```

**方法2：设置环境变量**
```powershell
$env:DOCKER_HOST="tcp://localhost:2375"
```

**方法3：在 Docker Desktop 中启用 TCP**
1. 打开 Docker Desktop
2. 进入 Settings -> General
3. 勾选 "Expose daemon on tcp://localhost:2375 without TLS"
4. 应用并重启 Docker Desktop

### Linux/Mac 系统配置

通常使用默认配置即可：
```yaml
docker:
  host: unix:///var/run/docker.sock  # Linux/Mac 使用 Unix socket
  container-name: aifuturetrade-trade
```

## 测试连接

### 使用 curl 测试（如果启用 TCP）
```bash
# Windows PowerShell
Invoke-WebRequest -Uri http://localhost:2375/version

# Linux/Mac
curl http://localhost:2375/version
```

### 使用 Docker 命令测试
```bash
# 测试基本连接
docker version

# 测试容器访问
docker inspect aifuturetrade-trade

# 测试日志流
docker logs -f aifuturetrade-trade
```

