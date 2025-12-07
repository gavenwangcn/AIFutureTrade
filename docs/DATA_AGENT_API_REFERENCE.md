# Data Agent API 快速参考

## 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| 指令服务器 | 9999 | 处理所有指令请求（添加/移除流、查询状态等） |
| 状态服务器 | 9988 | 仅处理健康检查请求（轻量级，快速响应） |

---

## 指令服务器 API (端口 9999)

### GET 接口

#### 1. 健康检查
```http
GET /ping
```

**响应：**
```json
{
  "status": "ok",
  "message": "pong"
}
```

---

#### 2. 获取连接数
```http
GET /connections/count
```

**响应：**
```json
{
  "connection_count": 7
}
```

**调用链：**
```
GET /connections/count
  → _handle_get_connection_count()
    → asyncio.run_coroutine_threadsafe(
          kline_manager.get_connection_count(),
          main_loop
      )
    → future.result(timeout=10)
```

---

#### 3. 获取连接列表
```http
GET /connections/list
```

**响应：**
```json
{
  "connections": [
    {
      "symbol": "BTCUSDT",
      "interval": "1m",
      "created_at": "2025-12-07T20:00:00+00:00",
      "is_active": true
    },
    ...
  ],
  "count": 7
}
```

**调用链：**
```
GET /connections/list
  → _handle_get_connection_list()
    → asyncio.run_coroutine_threadsafe(
          kline_manager.get_connection_list(),
          main_loop
      )
    → future.result(timeout=10)
```

---

#### 4. 获取Symbol列表
```http
GET /symbols
```

**响应：**
```json
{
  "symbols": ["BTCUSDT", "ETHUSDT", ...],
  "count": 2
}
```

**调用链：**
```
GET /symbols
  → _handle_get_symbols()
    → asyncio.run_coroutine_threadsafe(
          kline_manager.get_symbols(),
          main_loop
      )
    → future.result(timeout=10)
```

---

#### 5. 获取连接状态
```http
GET /status
```

**响应：**
```json
{
  "status": "ok",
  "connection_count": 14,
  "symbols": ["BTCUSDT", "ETHUSDT"]
}
```

**调用链：**
```
GET /status
  → _handle_get_status()
    → asyncio.run_coroutine_threadsafe(
          kline_manager.get_connection_status(),
          main_loop
      )
    → future.result(timeout=10)
    → cleanup_expired_connections()  # 自动清理
    → _cleanup_broken_connections()  # 自动清理
```

---

### POST 接口

#### 1. 添加单个K线流
```http
POST /streams/add
Content-Type: application/json

{
  "symbol": "BTCUSDT",
  "interval": "1m"
}
```

**响应：**
```json
{
  "status": "ok",
  "message": "Added stream for BTCUSDT 1m"
}
```

**调用链：**
```
POST /streams/add
  → _handle_add_stream()
    → 解析JSON请求体
    → asyncio.run_coroutine_threadsafe(
          kline_manager.add_stream(symbol, interval),
          main_loop
      )
    → future.result(timeout=30)
    → add_stream()
      → step1_init_client()
      → step2_rate_limit_check()
      → step3_create_connection()
      → step4_register_connection_error_handler()
      → step5_subscribe_kline_stream()
      → step6_register_message_handler()
      → step7_save_connection()
```

---

#### 2. 移除单个K线流
```http
POST /streams/remove
Content-Type: application/json

{
  "symbol": "BTCUSDT",
  "interval": "1m"
}
```

**响应：**
```json
{
  "status": "ok",
  "message": "Removed stream for BTCUSDT 1m"
}
```

**调用链：**
```
POST /streams/remove
  → _handle_remove_stream()
    → 解析JSON请求体
    → asyncio.run_coroutine_threadsafe(
          kline_manager.remove_stream(symbol, interval),
          main_loop
      )
    → future.result(timeout=10)
    → remove_stream()
      → 获取锁
      → conn.close()
      → 从字典中删除
```

---

#### 3. 批量添加Symbol
```http
POST /symbols/add
Content-Type: application/json

{
  "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", ...]
}
```

**响应：**
```json
{
  "status": "ok",
  "results": [
    {
      "symbol": "BTCUSDT",
      "success_count": 7,
      "failed_count": 0,
      "skipped_count": 0,
      "total_count": 7
    },
    ...
  ],
  "current_status": {
    "connection_count": 14,
    "symbols": ["BTCUSDT", "ETHUSDT"]
  },
  "summary": {
    "total_symbols": 2,
    "success_count": 2,
    "failed_count": 0,
    "failed_symbols": [],
    "duration_seconds": 5.234
  }
}
```

**调用链：**
```
POST /symbols/add
  → _handle_add_symbols()
    → 解析JSON请求体
    → 遍历每个symbol
      → asyncio.run_coroutine_threadsafe(
            kline_manager.add_symbol_streams(symbol),
            main_loop
        )
      → future.result(timeout=30)  # 每个symbol最多30秒
      → add_symbol_streams()
        → 检查已有连接 (7个interval)
        → 对每个interval调用 add_stream()
    → get_connection_status()  # 获取最终状态
    → 返回汇总结果
```

---

## 状态服务器 API (端口 9988)

### GET 接口

#### 健康检查（轻量级）
```http
GET /ping
```

**响应：**
```json
{
  "status": "ok",
  "message": "pong"
}
```

**特点：**
- 不执行任何异步操作
- 快速响应，不阻塞
- 用于健康检查和监控

---

## 内部方法调用链

### DataAgentKlineManager 核心方法

#### 1. add_stream(symbol, interval) → bool

**完整调用链：**
```
add_stream()
  ├─> 验证interval
  ├─> 获取锁: async with self._lock
  │   ├─> 检查连接是否已存在
  │   ├─> 如果存在且活跃 → 返回True
  │   ├─> 如果存在但过期 → 关闭并删除
  │   └─> 检查symbol数量限制
  │
  ├─> step1_init_client()
  │   └─> 初始化Binance SDK客户端（懒加载）
  │
  ├─> step2_rate_limit_check()
  │   └─> 检查订阅频率限制（每秒最多10个）
  │
  ├─> step3_create_connection()
  │   └─> SDK.create_connection() (超时15秒)
  │
  ├─> step4_register_connection_error_handler()
  │   └─> connection.on("error", handler)
  │
  ├─> step5_subscribe_kline_stream()
  │   └─> connection.kline_candlestick_streams() (超时15秒)
  │
  ├─> step6_register_message_handler()
  │   └─> stream.on("message", handler)
  │       └─> handler → _handle_kline_message()
  │
  └─> step7_save_connection()
      └─> 保存到_active_connections (持有锁)
```

**超时设置：**
- step3: 15秒
- step5: 15秒
- 整体: 25秒（在add_symbol_streams中）

---

#### 2. add_symbol_streams(symbol) → Dict

**完整调用链：**
```
add_symbol_streams()
  ├─> 获取锁: async with self._lock
  │   └─> 检查已有连接（遍历7个interval）
  │
  └─> 遍历 KLINE_INTERVALS (7个)
      └─> 对每个interval:
          ├─> 如果已存在 → 跳过
          └─> 如果不存在 → add_stream() (超时25秒)
```

**返回结果：**
```json
{
  "success_count": 7,
  "failed_count": 0,
  "skipped_count": 0,
  "total_count": 7
}
```

---

#### 3. _handle_kline_message(symbol, interval, message)

**完整调用链：**
```
WebSocket消息到达
  → stream.on("message") 回调
    → handler(data)
      → asyncio.create_task(
            _handle_kline_message(symbol, interval, data)
        )
        └─> _handle_kline_message()
            ├─> _normalize_kline(message)
            │   └─> 规范化K线数据格式
            │
            └─> asyncio.to_thread(
                    db.insert_market_klines([normalized])
                )
                └─> 插入到ClickHouse数据库
```

---

## 关键配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `DATA_AGENT_PORT` | 9999 | 指令服务器端口 |
| `DATA_AGENT_STATUS_PORT` | 9988 | 状态服务器端口 |
| `DATA_AGENT_MAX_SYMBOL` | 100 | 最大symbol数量 |
| `DATA_AGENT_REGISTER_IP` | None | async_agent的IP地址 |
| `DATA_AGENT_REGISTER_PORT` | None | async_agent的端口号 |
| `DATA_AGENT_IP` | None | 当前agent的IP地址 |

---

## 超时设置

| 操作 | 超时时间 | 说明 |
|------|----------|------|
| step3_create_connection | 15秒 | SDK创建连接 |
| step5_subscribe_kline_stream | 15秒 | SDK订阅流 |
| add_stream (整体) | 25秒 | 在add_symbol_streams中 |
| add_symbol_streams (单个symbol) | 30秒 | 在_handle_add_symbols中 |
| GET请求 | 10秒 | 查询类请求 |
| POST /streams/add | 30秒 | 添加单个流 |
| POST /streams/remove | 10秒 | 移除流 |
| 连接关闭 | 5秒 | cleanup操作 |

---

## 频率限制

| 限制项 | 值 | 说明 |
|--------|-----|------|
| 订阅频率 | 每秒最多10个 | 控制向Binance发送订阅消息的频率 |
| 等待时间 | 最多1秒 | 如果超过限制，等待剩余时间 |

---

## 错误处理

### 连接错误
```
connection.on("error")
  → asyncio.create_task(
        _remove_broken_connection(symbol, interval)
    )
    └─> 标记is_active=False
    └─> 关闭连接
    └─> 从字典中删除
```

### 流错误
```
stream.on("error")
  → asyncio.create_task(
        _remove_broken_connection(symbol, interval)
    )
    └─> 同上
```

### 超时错误
- 所有SDK调用都有超时保护
- 超时后会抛出 `asyncio.TimeoutError`
- 自动清理已创建的资源

---

## 定期任务

| 任务 | 执行频率 | 说明 |
|------|----------|------|
| cleanup_expired_connections | 每小时 | 清理超过24小时的连接 |
| self_update_status_task | 每分钟 | 更新连接信息到数据库 |
| _periodic_connection_check | 后台持续 | 定期检查连接状态 |
| _periodic_ping | 每5分钟 | 发送ping保持连接活跃 |

---

## 使用示例

### 示例1: 批量添加Symbol
```bash
curl -X POST http://localhost:9999/symbols/add \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"]}'
```

### 示例2: 添加单个流
```bash
curl -X POST http://localhost:9999/streams/add \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT", "interval": "1m"}'
```

### 示例3: 查询状态
```bash
curl http://localhost:9999/status
```

### 示例4: 健康检查
```bash
curl http://localhost:9988/ping
```

---

## 注意事项

1. **并发处理**: 使用多线程HTTP服务器，支持并发请求
2. **异步操作**: 所有异步操作通过 `asyncio.run_coroutine_threadsafe()` 执行
3. **超时保护**: 所有关键操作都有超时保护，避免卡住
4. **锁机制**: 连接字典使用 `asyncio.Lock()` 保护
5. **资源清理**: 不在持有锁的情况下关闭连接，避免阻塞
6. **错误恢复**: 自动清理断开的连接，保持系统稳定

