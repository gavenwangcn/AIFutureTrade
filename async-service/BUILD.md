# Async Service 构建指南

## 前置要求

1. **JDK 11+**：确保已安装JDK 11或更高版本
2. **Maven 3.6+**：确保已安装Maven
3. **Binance SDK**：需要先编译Binance Java SDK

## 构建步骤

### 1. 编译Binance Java SDK

由于项目依赖本地的Binance Java SDK，需要先编译SDK：

```bash
cd binance-connector-java-master/clients/derivatives-trading-usds-futures
mvn clean install -DskipTests
```

这将把SDK安装到本地Maven仓库。

### 2. 构建Async Service

```bash
cd async-service
mvn clean package -DskipTests
```

### 3. 运行服务

#### 方式1：使用启动脚本（推荐）

```bash
cd async-service
bash scripts/build-and-start.sh --auto-start
```

#### 方式2：直接运行JAR

```bash
java -Xms1g -Xmx2g -XX:+UseG1GC -jar target/async-service-1.0.0.jar
```

#### 方式3：使用Docker

```bash
# 构建镜像
docker build -t async-service:1.0.0 .

# 运行容器
docker run -d \
  --name async-service \
  -p 5003:5003 \
  -e SPRING_DATASOURCE_URL=jdbc:mysql://... \
  -e SPRING_DATASOURCE_USERNAME=... \
  -e SPRING_DATASOURCE_PASSWORD=... \
  -e BINANCE_API_KEY=... \
  -e BINANCE_SECRET_KEY=... \
  async-service:1.0.0
```

## 依赖问题排查

### 问题1：找不到Binance SDK依赖

**解决方案**：
1. 确保已编译并安装Binance SDK到本地Maven仓库
2. 或者修改`pom.xml`使用`system` scope指向本地JAR文件

### 问题2：编译错误

**解决方案**：
1. 检查JDK版本（需要11+）
2. 检查Maven版本（需要3.6+）
3. 清理并重新构建：`mvn clean install -U`

## 配置说明

所有配置都在`application.yml`中，支持通过环境变量覆盖：

- `SERVER_PORT`：服务端口（默认5003）
- `SPRING_DATASOURCE_URL`：数据库连接URL
- `SPRING_DATASOURCE_USERNAME`：数据库用户名
- `SPRING_DATASOURCE_PASSWORD`：数据库密码
- `BINANCE_API_KEY`：币安API密钥
- `BINANCE_SECRET_KEY`：币安API密钥
- `PRICE_REFRESH_CRON`：价格刷新Cron表达式
- `PRICE_REFRESH_MAX_PER_MINUTE`：每分钟最多刷新数量
- `MARKET_SYMBOL_OFFLINE_CRON`：Symbol下线Cron表达式
- `MARKET_SYMBOL_RETENTION_MINUTES`：数据保留分钟数

