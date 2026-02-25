# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

AIFutureTrade 是一个基于币安期货的AI自动交易系统，采用微服务架构，包含前端、后端、交易服务、市场数据服务和异步服务。

## 技术栈

- **Backend**: Java 17 + Spring Boot 3.2.0 + MyBatis Plus
- **Binance Service**: Java 17 + Spring Boot + Undertow (高性能异步IO)
- **Async Service**: Java 17 + Spring Boot (WebSocket流处理 + 定时任务)
- **Trade Service**: Python 3 + Flask + Gunicorn + Eventlet
- **Frontend**: Vue 3 + Vite + KLineChart
- **Database**: MySQL 8.0
- **Container**: Docker + Docker Compose

## 核心架构

### 服务职责划分

1. **backend (端口5002)**: 主API服务
   - 用户管理、模型管理、交易记录
   - 通过Docker API动态创建/管理model-buy和model-sell容器
   - 调用trade服务执行交易逻辑
   - 挂载Docker socket (`/var/run/docker.sock`) 用于容器管理

2. **binance-service (端口5004)**: 币安API微服务
   - 市场数据查询（K线、价格、24小时统计）
   - 使用Undertow提供高性能异步IO
   - 独立部署，专注于币安API调用

3. **async-service (端口5003)**: 异步数据同步服务
   - WebSocket长连接接收市场ticker数据流
   - 定时刷新价格（每5分钟）
   - 定时清理过期数据（每30分钟）
   - 自动启动配置：`ASYNC_AUTO_START_ENABLED=true`, `ASYNC_AUTO_START_TASK=all`

4. **trade (端口5000)**: Python交易引擎
   - 交易策略执行、风险管理
   - 使用Gunicorn + Eventlet处理并发
   - 技术指标计算（TA-Lib, pandas, numpy）

5. **model-buy / model-sell**: 动态交易容器
   - 由backend通过Docker API动态创建
   - 每个模型独立运行在单独容器中
   - 镜像构建但不自动启动 (`--scale model-buy=0 --scale model-sell=0`)

6. **frontend (端口3000)**: Vue 3前端
   - 实时K线图表（KLineChart）
   - WebSocket实时数据推送
   - 开发环境使用Vite代理，生产环境使用当前域名+端口5002

### 数据流

```
Frontend (Vue3)
  ↓ HTTP/WebSocket
Backend (Java)
  ↓ HTTP
Trade Service (Python)
  ↓ API
Binance API

Async Service → WebSocket → Binance → MySQL (24_market_tickers)
```

### 动态容器管理

Backend通过Docker API动态创建model-buy/model-sell容器：
- 容器命名：`buy-{modelId}` / `sell-{modelId}`
- 环境变量：`MODEL_ID`, MySQL配置, Binance API密钥
- 网络：`aifuturetrade-network`
- 启动命令：`python -m trade.start.model_start_buy` / `model_start_sell`

## 常用命令

### 构建和启动

```bash
# 1. 先启动MySQL（必须）
docker-compose -f docker-compose-mysql.yml up -d

# 2. 启动所有服务（推荐使用脚本）
./scripts/docker-compose-up.sh --build

# 或手动启动（model-buy/model-sell不自动启动）
docker-compose up -d --build --scale model-buy=0 --scale model-sell=0

# 仅构建model镜像（不启动容器）
docker-compose build model-buy model-sell
```

### 服务管理

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f backend
docker-compose logs -f trade
docker-compose logs -f async-service

# 重启服务
docker-compose restart backend

# 停止所有服务
docker-compose down

# 停止并删除所有model容器
docker stop $(docker ps -q --filter "name=buy-*")
docker rm $(docker ps -a -q -f "name=buy-*")
docker stop $(docker ps -q --filter "name=sell-*")
docker rm $(docker ps -a -q -f "name=sell-*")
```

### Java服务构建

```bash
# Backend
cd backend
mvn clean package -DskipTests

# Binance Service
cd binance-service
mvn clean package -DskipTests

# Async Service
cd async-service
mvn clean package -DskipTests

# Binance SDK（依赖，需要先构建）
cd binance-connector-java-master/clients/derivatives-trading-usds-futures
mvn clean install
```

### Python服务

```bash
# 安装依赖
cd trade
pip install -r requirements.txt

# 运行测试
cd trade
python -m pytest tests/

# 启动开发服务器
cd trade
python -m trade.app
```

### 前端开发

```bash
cd frontend

# 安装依赖
npm install

# 开发模式（支持代理）
npm run dev

# 生产构建
npm run build

# 预览生产构建
npm run preview
```

## 重要配置

### 环境变量（.env文件）

```bash
# MySQL配置
MYSQL_HOST=154.89.148.172
MYSQL_PORT=32123
MYSQL_USER=aifuturetrade
MYSQL_PASSWORD=aifuturetrade123
MYSQL_DATABASE=aifuturetrade

# Binance API
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_secret_key

# 服务端口
BACKEND_PORT=5002
BINANCE_SERVICE_PORT=5004
ASYNC_SERVICE_PORT=5003
TRADE_PORT=5000
FRONTEND_PORT=3000

# 异步服务自动启动
ASYNC_AUTO_START_ENABLED=true
ASYNC_AUTO_START_TASK=all
```

### JVM参数

所有Java服务使用以下JVM参数：
- `--add-opens java.base/java.lang.invoke=ALL-UNNAMED` (解决MyBatis-Plus反射警告)
- Backend: `-Xms512m -Xmx1024m`
- Binance/Async Service: `-Xms1g -Xmx2g -XX:+UseG1GC -XX:MaxGCPauseMillis=200`

### 数据库表

关键表：
- `24_market_tickers`: 实时市场ticker数据（由async-service维护）
- `models`: 交易模型配置
- `trades`: 交易记录
- `positions`: 持仓信息

## 开发注意事项

### 依赖关系

1. 所有服务依赖MySQL，必须先启动MySQL
2. Backend依赖Trade服务（`TRADE_SERVICE_URL=http://trade:5000`）
3. Java服务依赖Binance SDK，需要先编译SDK
4. Frontend开发环境使用Vite代理，生产环境直接访问backend

### 版本对齐

Binance SDK使用特定版本的依赖（Jetty 11.0.25, Jackson 2.19.0），所有Java服务必须与之对齐，避免版本冲突。

### Docker网络

所有服务使用 `aifuturetrade-network` 桥接网络，容器间通过服务名通信（如 `http://backend:5002`）。

### 账户计算公式

```
cash = 初始资金 + 已实现盈亏 - 已用保证金
margin_used = Σ((持仓数量 × 开仓均价) / 杠杆倍数)
positions_value = Σ(持仓数量 × 开仓均价)
total_value = 初始资金 + 已实现盈亏 + 未实现盈亏
```

### WebSocket连接限制

币安WebSocket连接有30分钟限制，async-service会自动重连。

## API文档

- Backend Swagger: http://localhost:5002/swagger-ui.html
- Binance Service Swagger: http://localhost:5004/swagger-ui.html
- Async Service API: http://localhost:5003/api/async/status

## 故障排查

### 服务无法启动

1. 检查MySQL是否已启动：`docker-compose -f docker-compose-mysql.yml ps`
2. 检查端口占用：`netstat -tlnp | grep 5002`
3. 查看日志：`docker-compose logs -f [service-name]`

### Maven构建失败

1. 先构建Binance SDK：`cd binance-connector-java-master/clients/derivatives-trading-usds-futures && mvn clean install`
2. 清理缓存：`mvn clean`
3. 跳过测试：`mvn package -DskipTests`

### 前端无法连接后端

1. 开发环境：检查 `vite.config.js` 代理配置
2. 生产环境：检查 `VITE_BACKEND_PORT` 环境变量
3. Docker环境：确保backend服务已启动且在同一网络

### Model容器无法创建

1. 检查backend是否挂载Docker socket
2. 检查model-buy/model-sell镜像是否已构建
3. 查看backend日志中的Docker API调用错误
