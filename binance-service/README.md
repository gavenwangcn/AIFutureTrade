# Binance Service 部署指南

## 概述

Binance Service 是一个独立的微服务，专门用于提供币安API的市场数据查询功能（如实时价格、K线信息等）。

**技术特点：**
- 使用 **Undertow 异步IO服务器**，提供高性能接口服务
- 支持高并发请求处理
- 低延迟响应
- 适合高频API调用场景

## 目录结构

```
binance-service/
├── pom.xml                          # Maven配置文件
├── Dockerfile                       # Docker构建文件
├── README.md                        # 本文档
├── scripts/                         # 脚本目录
│   ├── build-and-start.sh          # 构建和启动脚本
│   ├── install-service.sh          # Systemd服务安装脚本
│   └── binance-service.service     # Systemd服务文件模板
└── src/
    └── main/
        ├── java/                    # Java源代码
        └── resources/
            ├── application.yml      # 应用配置文件
            └── logback-spring.xml   # 日志配置文件
```

## 快速开始

### 方式一：使用构建和启动脚本（推荐用于开发/测试）

```bash
cd binance-service
bash scripts/build-and-start.sh
```

脚本会自动：
1. 检查并安装JDK 17和Maven（如果需要）
2. 使用 `mvn clean package` 构建JAR包
3. 使用 `java -jar` 方式启动服务

### 方式二：使用Systemd服务（推荐用于生产环境）

```bash
cd binance-service
sudo bash scripts/install-service.sh
```

脚本会自动：
1. 检查并安装JDK 17和Maven（如果需要）
2. 构建JAR包
3. 安装systemd服务
4. 启用并启动服务（开机自启）

## 配置说明

### 端口配置

服务端口在 `src/main/resources/application.yml` 中配置：

```yaml
server:
  port: ${SERVER_PORT:5004}  # 默认5004，可通过环境变量覆盖
```

### 环境变量

可以通过环境变量覆盖配置：

```bash
export SERVER_PORT=5004
export BINANCE_API_KEY=your_api_key
export BINANCE_SECRET_KEY=your_secret_key
```

### 日志配置

日志配置在 `src/main/resources/logback-spring.xml` 中：

- 应用日志：`logs/binance-service.log`
- Binance API日志：`logs/binance-api.log`
- 日志保留：7天
- 单个日志文件大小：10MB

## 服务管理

### Systemd服务管理

如果使用systemd服务安装：

```bash
# 查看服务状态
sudo systemctl status binance-service

# 启动服务
sudo systemctl start binance-service

# 停止服务
sudo systemctl stop binance-service

# 重启服务
sudo systemctl restart binance-service

# 查看日志
sudo journalctl -u binance-service -f

# 禁用开机自启
sudo systemctl disable binance-service

# 启用开机自启
sudo systemctl enable binance-service
```

### 手动启动

如果使用 `build-and-start.sh` 脚本启动：

```bash
# 查看进程
ps aux | grep binance-service

# 停止服务（使用PID文件）
kill $(cat binance-service.pid)

# 或者直接使用java命令启动
java -jar target/binance-service-1.0.0.jar
```

## API接口

服务启动后，可以通过以下接口访问：

- **Swagger文档**: http://localhost:5004/swagger-ui.html
- **24小时统计**: POST http://localhost:5004/api/market-data/24h-ticker
- **实时价格**: POST http://localhost:5004/api/market-data/symbol-prices
- **K线数据**: GET http://localhost:5004/api/market-data/klines?symbol=BTCUSDT&interval=1m&limit=120
- **格式化符号**: GET http://localhost:5004/api/market-data/format-symbol?baseSymbol=BTC

## Docker部署

### 构建镜像

```bash
cd binance-service
docker build -t binance-service:1.0.0 .
```

### 运行容器

```bash
docker run -d \
  --name binance-service \
  -p 5004:5004 \
  -e SERVER_PORT=5004 \
  -e BINANCE_API_KEY=your_api_key \
  -e BINANCE_SECRET_KEY=your_secret_key \
  binance-service:1.0.0
```

## 故障排查

### 服务无法启动

1. 检查Java版本：`java -version`（需要17+）
2. 检查Maven版本：`mvn -version`
3. 查看启动日志：`logs/startup.log` 或 `logs/service-error.log`
4. 检查端口是否被占用：`netstat -tlnp | grep 5004`

### 服务启动后无法访问

1. 检查防火墙设置
2. 检查服务是否正常运行：`systemctl status binance-service`
3. 查看应用日志：`tail -f logs/binance-service.log`

### 构建失败

1. 检查网络连接（Maven需要下载依赖）
2. 检查JDK和Maven是否正确安装
3. 清理并重新构建：`mvn clean package -DskipTests`

## 注意事项

1. **端口冲突**：确保5004端口未被其他服务占用
2. **API密钥**：确保配置了正确的币安API密钥
3. **日志目录**：确保有写入权限（logs目录会自动创建）
4. **内存设置**：默认JVM内存为512MB-1024MB，可根据需要调整

## 相关文件

- `scripts/build-and-start.sh` - 构建和启动脚本
- `scripts/install-service.sh` - Systemd服务安装脚本
- `../scripts/install-jdk17-maven.sh` - JDK和Maven安装脚本
- `backend/Dockerfile` - 参考Dockerfile（类似结构）
- `backend/src/main/resources/logback-spring.xml` - 参考日志配置

