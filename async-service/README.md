# Async Service - 异步同步服务

Java版本的异步同步服务，完全迁移了Python async目录下所有模块的功能。

## 项目结构

```
async-service/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/aifuturetrade/asyncservice/
│   │   │       ├── AsyncServiceApplication.java    # 主应用类
│   │   │       ├── config/                         # 配置类
│   │   │       │   ├── CorsConfig.java
│   │   │       │   └── MyBatisPlusConfig.java
│   │   │       ├── controller/                     # Controller层
│   │   │       │   └── AsyncAgentController.java
│   │   │       ├── dao/                            # DAO层
│   │   │       │   └── mapper/
│   │   │       │       └── MarketTickerMapper.java
│   │   │       └── service/                         # Service层
│   │   │           ├── AsyncAgentService.java
│   │   │           ├── MarketSymbolOfflineService.java
│   │   │           ├── MarketTickerStreamService.java
│   │   │           ├── PriceRefreshService.java
│   │   │           └── impl/                        # Service实现
│   │   │               ├── AsyncAgentServiceImpl.java
│   │   │               ├── MarketSymbolOfflineServiceImpl.java
│   │   │               ├── MarketTickerStreamServiceImpl.java
│   │   │               └── PriceRefreshServiceImpl.java
│   │   └── resources/
│   │       ├── application.yml                     # 应用配置
│   │       └── mapper/
│   │           └── MarketTickerMapper.xml          # MyBatis映射文件
│   └── test/
├── pom.xml                                          # Maven配置
└── README.md                                        # 本文档
```

## 功能模块

### 1. MarketTickerStreamService - 市场Ticker流服务
- **功能**：通过币安WebSocket接收所有交易对的24小时ticker数据，存储到MySQL
- **对应Python模块**：`market/market_streams.py`
- **特性**：
  - 自动重连（每30分钟重新建立连接，币安限制）
  - 增量更新（使用upsert实现）
  - 异常处理和日志记录

### 2. PriceRefreshService - 价格刷新服务
- **功能**：定期刷新24_market_tickers表的开盘价格
- **对应Python模块**：`async/price_refresh_service.py`
- **特性**：
  - 使用昨天的收盘价作为今天的开盘价
  - 批量处理，控制刷新频率（每分钟最多1000个）
  - 定时调度（默认每5分钟）

### 3. MarketSymbolOfflineService - 市场Symbol下线服务
- **功能**：定时删除过期的ticker数据
- **对应Python模块**：`async/market_symbol_offline.py`
- **特性**：
  - 删除ingestion_time早于（当前时间 - 保留分钟数）的记录
  - 定时执行（默认每30分钟）
  - 数据保留时间可配置（默认30分钟）

### 4. AsyncAgentService - 异步代理服务
- **功能**：统一管理和调度各种后台异步任务服务
- **对应Python模块**：`async/async_agent.py`
- **支持的任务**：
  - `market_tickers`: 市场ticker数据流服务
  - `price_refresh`: 价格刷新服务
  - `market_symbol_offline`: 市场Symbol下线服务
  - `all`: 运行所有服务

## 自动启动配置

应用启动时会自动启动配置的异步服务，无需手动调用API。

### 配置项

在`application.yml`中配置：

```yaml
async:
  # 是否在应用启动时自动启动服务（默认true）
  auto-start-enabled: ${ASYNC_AUTO_START_ENABLED:true}
  # 启动时自动启动的任务（默认all，启动所有服务）
  # 可选值：market_tickers, price_refresh, market_symbol_offline, all
  auto-start-task: ${ASYNC_AUTO_START_TASK:all}
```

### 环境变量

- `ASYNC_AUTO_START_ENABLED`：是否启用自动启动（默认true）
- `ASYNC_AUTO_START_TASK`：启动时自动启动的任务（默认all）
- `ASYNC_AUTO_START_DELAY`：启动延迟（秒），确保所有Bean初始化完成（默认3秒）

### 示例

```bash
# 启动时只启动市场Ticker流服务
export ASYNC_AUTO_START_TASK=market_tickers

# 禁用自动启动（手动通过API启动）
export ASYNC_AUTO_START_ENABLED=false

# 启动所有服务（默认）
export ASYNC_AUTO_START_TASK=all

# 设置启动延迟为5秒
export ASYNC_AUTO_START_DELAY=5
```

### 说明

- **market_tickers**：市场Ticker流服务，需要手动启动（通过AsyncAgentService）
- **price_refresh**：价格刷新服务，通过`@Scheduled`定时任务自动运行，启动时也会立即执行一次
- **market_symbol_offline**：Symbol下线服务，通过`@Scheduled`定时任务自动运行，启动时也会立即执行一次
- **all**：启动所有服务（market_tickers流服务 + 立即执行一次price_refresh和market_symbol_offline）

**注意**：即使不通过AsyncAgentService启动，price_refresh和market_symbol_offline服务也会通过Spring的`@Scheduled`注解自动运行定时任务。

## 配置说明

### application.yml配置项

```yaml
# 服务器配置
server:
  port: ${SERVER_PORT:5003}  # 默认5003端口

# 数据库配置
spring:
  datasource:
    url: ${SPRING_DATASOURCE_URL:jdbc:mysql://...}
    username: ${SPRING_DATASOURCE_USERNAME:...}
    password: ${SPRING_DATASOURCE_PASSWORD:...}

# Binance API配置
binance:
  api-key: ${BINANCE_API_KEY:...}
  secret-key: ${BINANCE_SECRET_KEY:...}
  quote-asset: USDT

# 异步服务配置
async:
  market-ticker:
    max-connection-minutes: 30      # WebSocket连接最大时长（分钟）
    reconnect-delay: 120             # 重连延迟（秒）
    message-timeout: 30              # 消息处理超时（秒）
    db-operation-timeout: 20        # 数据库操作超时（秒）
  
  price-refresh:
    cron: ${PRICE_REFRESH_CRON:*/5 * * * *}  # Cron表达式
    max-per-minute: ${PRICE_REFRESH_MAX_PER_MINUTE:1000}  # 每分钟最多刷新数量
  
  market-symbol-offline:
    cron: ${MARKET_SYMBOL_OFFLINE_CRON:*/30 * * * *}  # Cron表达式
    retention-minutes: ${MARKET_SYMBOL_RETENTION_MINUTES:30}  # 数据保留分钟数
```

## 使用方式

### 1. 构建项目

```bash
cd async-service
mvn clean package
```

### 2. 运行服务

```bash
java -jar target/async-service-1.0.0.jar
```

### 3. 通过REST API管理任务

#### 启动任务
```bash
# 启动市场Ticker流服务
curl -X POST http://localhost:5003/api/async/task/market_tickers

# 启动价格刷新服务
curl -X POST http://localhost:5003/api/async/task/price_refresh

# 启动Symbol下线服务
curl -X POST http://localhost:5003/api/async/task/market_symbol_offline

# 启动所有服务
curl -X POST http://localhost:5003/api/async/task/all

# 启动任务并指定运行时长（秒）
curl -X POST "http://localhost:5003/api/async/task/market_tickers?durationSeconds=3600"
```

#### 停止所有任务
```bash
curl -X POST http://localhost:5003/api/async/stop
```

#### 查询任务状态
```bash
# 查询单个任务状态
curl http://localhost:5003/api/async/task/market_tickers/status

# 查询所有任务状态
curl http://localhost:5003/api/async/status
```

### 4. 定时任务

价格刷新和Symbol下线服务会自动通过Spring的`@Scheduled`注解定时执行，无需手动启动。

## 与Python版本的对应关系

| Java Service | Python模块 | 功能 |
|-------------|-----------|------|
| MarketTickerStreamService | market/market_streams.py | WebSocket长连接，接收ticker数据 |
| PriceRefreshService | async/price_refresh_service.py | 刷新开盘价格 |
| MarketSymbolOfflineService | async/market_symbol_offline.py | 删除过期数据 |
| AsyncAgentService | async/async_agent.py | 统一管理和调度 |

## 注意事项

1. **Binance SDK依赖**：项目依赖本地的Binance Java SDK，需要先编译SDK：
   ```bash
   cd binance-connector-java-master/clients/derivatives-trading-usds-futures
   mvn clean install
   ```

2. **数据库连接**：确保数据库连接配置正确，服务需要访问`24_market_tickers`表。

3. **WebSocket连接**：币安WebSocket连接有30分钟限制，服务会自动重连。

4. **定时任务**：价格刷新和Symbol下线服务通过Spring定时任务自动运行，启动服务后会自动开始执行。

## 开发说明

### 架构设计

- **Controller层**：提供REST API接口，用于任务管理
- **Service层**：实现核心业务逻辑
- **DAO层**：数据库操作，使用MyBatis Plus

### 扩展开发

如需添加新的异步任务：
1. 创建Service接口和实现类
2. 在`AsyncAgentService`中注册新任务
3. 在`AsyncAgentController`中添加API接口

## 故障排查

1. **WebSocket连接失败**：检查网络连接和币安API状态
2. **数据库操作失败**：检查数据库连接配置和表结构
3. **定时任务不执行**：检查`@EnableScheduling`注解是否启用

## 代码完善说明

### 已完成的完善工作

1. **WebSocket Ticker数据解析**：
   - 完善了`MarketTickerStreamServiceImpl.normalizeSingleTicker()`方法
   - 根据`AllMarketTickersStreamsResponseInner`的实际字段结构完成字段映射
   - 支持所有ticker字段的解析和转换

2. **K线数据解析**：
   - 完善了`PriceRefreshServiceImpl.extractClosePrice()`方法
   - 根据`BinanceFuturesClient.getKlines()`返回的Map结构提取收盘价
   - 支持多种数据格式的兼容处理

3. **批量处理优化**：
   - 使用`CountDownLatch`确保批次内所有任务完成
   - 添加超时控制（最多等待5分钟）
   - 使用`AtomicInteger`确保线程安全的计数

4. **WebSocket重连逻辑**：
   - 实现了自动重连机制（每30分钟或连接断开后）
   - 支持无限运行模式（自动重连循环）
   - 支持指定运行时长模式

5. **启动脚本**：
   - 创建了`build-and-start.sh`脚本
   - 支持交互模式和自动启动模式
   - 包含完整的错误处理和日志输出

6. **Docker支持**：
   - 创建了`Dockerfile`支持容器化部署
   - 使用多阶段构建优化镜像大小
   - 所有配置从application.yml读取

## 后续优化建议

- [ ] 添加监控和告警功能
- [ ] 支持分布式部署
- [ ] 添加健康检查接口
- [ ] 优化数据库批量插入性能

