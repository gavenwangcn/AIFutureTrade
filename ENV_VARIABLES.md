# 环境变量配置说明

## 概述

本文档列出了项目中实际使用的环境变量。所有变量都有默认值，可以不设置。

## 必需的环境变量

### Binance API 配置
```bash
# Binance API密钥（必需，用于交易和市场数据）
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
```

## 可选的环境变量

### Gunicorn 配置（后端服务）
```bash
# Worker进程数，建议为CPU核心数*2+1（默认：5）
GUNICORN_WORKERS=5

# Worker类型（默认：eventlet）
GUNICORN_WORKER_CLASS=eventlet

# 每个worker的最大连接数（默认：1000）
GUNICORN_WORKER_CONNECTIONS=1000

# Worker超时时间（秒）（默认：120）
GUNICORN_TIMEOUT=120

# Keep-alive时间（秒）（默认：5）
GUNICORN_KEEPALIVE=5

# 每个worker处理的最大请求数（默认：1000）
GUNICORN_MAX_REQUESTS=1000
```

### 价格刷新服务配置（后端服务）
```bash
# Cron表达式，默认每5分钟执行一次
PRICE_REFRESH_CRON=*/5 * * * *

# 每分钟最多刷新的symbol数量（默认：1000）
PRICE_REFRESH_MAX_PER_MINUTE=1000
```

### K线同步配置（async-agent 服务）
```bash
# K线WebSocket巡检间隔（秒）（默认：10）
KLINE_SYNC_CHECK_INTERVAL=10

# Cron表达式，默认每1小时执行一次
KLINE_CLEANUP_CRON=0 */1 * * *

# 保留天数，默认14天
KLINE_CLEANUP_RETENTION_DAYS=14
```

### Data Agent 配置（data-manager 和 data-agent 服务）
```bash
# 每个data_agent最多持有的symbol数量（默认：150）
DATA_AGENT_MAX_SYMBOL=150

# data_agent指令接口端口（默认：9999）
DATA_AGENT_PORT=9999

# data_agent注册IP（Docker环境中使用服务名 'data-manager'，默认：127.0.0.1）
DATA_AGENT_REGISTER_IP=data-manager

# data_agent注册端口（默认：8888）
DATA_AGENT_REGISTER_PORT=8888

# 批量添加symbol时每批最多处理的symbol数量（默认：20）
DATA_AGENT_BATCH_SYMBOL_SIZE=20

# 心跳超时（秒）（默认：60）
DATA_AGENT_HEARTBEAT_TIMEOUT=60

# 检查data_agent状态间隔（秒）（默认：60）
DATA_AGENT_STATUS_CHECK_INTERVAL=60

# 全量同步任务执行间隔（秒），默认3分钟（默认：180）
DATA_AGENT_FULL_SYNC_INTERVAL=180

# agent自己定时更新状态到数据库的间隔（秒），默认1分钟（默认：60）
DATA_AGENT_SELF_UPDATE_INTERVAL=60

# 命令执行超时（秒），防止agent不响应时阻塞队列（默认：90）
DATA_AGENT_COMMAND_TIMEOUT=90
```

### AI 决策配置（可选）
```bash
# 每次提交给AI模型的symbol数量，默认为1
AI_DECISION_SYMBOL_BATCH_SIZE=1
```

## 已移除的环境变量

以下环境变量已从 docker-compose.yml 中移除，因为代码已迁移到 MySQL：

- `CLICKHOUSE_HOST`
- `CLICKHOUSE_PORT`
- `CLICKHOUSE_USER`
- `CLICKHOUSE_PASSWORD`
- `CLICKHOUSE_DATABASE`
- `CLICKHOUSE_SECURE`
- `CLICKHOUSE_MARKET_TICKER_TABLE`
- `CLICKHOUSE_LEADERBOARD_TABLE`
- `CLICKHOUSE_MARKET_KLINES_TABLE`
- `CLICKHOUSE_LEADERBOARD_SYNC_INTERVAL`
- `CLICKHOUSE_LEADERBOARD_TIME_WINDOW`
- `CLICKHOUSE_LEADERBOARD_TOP_N`
- `CLICKHOUSE_LEADERBOARD_CLEANUP_INTERVAL_MINUTES`
- `CLICKHOUSE_LEADERBOARD_RETENTION_MINUTES`

## 硬编码的配置（无需设置环境变量）

以下配置在 docker-compose.yml 中已硬编码，无需设置环境变量：

### MySQL 配置
- `MYSQL_HOST=mysql`（Docker服务名）
- `MYSQL_PORT=3306`
- `MYSQL_USER=aifuturetrade`
- `MYSQL_PASSWORD=aifuturetrade123`
- `MYSQL_DATABASE=aifuturetrade`

### 其他配置
- `DATABASE_PATH=/app/data/trading_bot.db`
- `USE_GUNICORN=true`
- `FLASK_ENV=production`
- `PYTHONPATH=/app`
- `BACKEND_URL=http://backend:5002`
- `FRONTEND_PORT=3000`
- `NODE_ENV=production`

## 使用方法

### 方式1：使用 .env 文件（推荐）
1. 创建 `.env` 文件（参考本文档）
2. 设置需要的环境变量
3. Docker Compose 会自动读取 `.env` 文件

### 方式2：直接在命令行设置
```bash
BINANCE_API_KEY=your_key BINANCE_API_SECRET=your_secret docker-compose up -d
```

### 方式3：使用系统环境变量
```bash
export BINANCE_API_KEY=your_key
export BINANCE_API_SECRET=your_secret
docker-compose up -d
```

## 注意事项

1. **敏感信息**：生产环境请修改默认密码和API密钥
2. **默认值**：所有变量都有默认值，可以不设置
3. **Docker环境**：在 Docker Compose 中，服务名可以直接作为主机名使用（如 `mysql`）
4. **网络配置**：所有服务使用相同的 Docker 网络 `aifuturetrade-network`

