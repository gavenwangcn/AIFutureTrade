# Data Agent 业务场景调用链分析

## 目录
1. [系统架构概览](#系统架构概览)
2. [主场景调用链](#主场景调用链)
3. [服务端口构建](#服务端口构建)
4. [HTTP请求处理流程](#http请求处理流程)
5. [外部可调用API](#外部可调用api)
6. [内部调用链逻辑](#内部调用链逻辑)
7. [核心业务场景](#核心业务场景)

---

## 系统架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Agent 系统架构                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  入口点: main()                                              │
│  └─> run_data_agent()                                        │
│      ├─> 初始化 DataAgentKlineManager                        │
│      ├─> 启动指令服务器 (端口 9999)                          │
│      ├─> 启动状态服务器 (端口 9988)                          │
│      ├─> 注册到 async_agent                                  │
│      └─> 启动后台任务                                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  HTTP 服务器层                                               │
│  ├─> DataAgentCommandHandler (端口 9999)                     │
│  │   └─> 处理指令请求 (GET/POST)                            │
│  └─> DataAgentStatusHandler (端口 9988)                       │
│      └─> 处理健康检查 (GET /ping)                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  核心管理器: DataAgentKlineManager                          │
│  ├─> 连接管理                                                │
│  ├─> 流管理                                                  │
│  ├─> 消息处理                                                │
│  └─> 清理任务                                                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  SDK 层                                                      │
│  └─> Binance WebSocket SDK                                  │
│      └─> 创建连接、订阅流、接收消息                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 主场景调用链

### 场景1: 服务启动流程

```
main()
  │
  ├─> _setup_logging()
  │   └─> 配置日志系统
  │
  ├─> 读取配置
  │   ├─> DATA_AGENT_MAX_SYMBOL (默认: 100)
  │   ├─> DATA_AGENT_PORT (默认: 9999)
  │   ├─> DATA_AGENT_STATUS_PORT (默认: 9988)
  │   ├─> DATA_AGENT_REGISTER_IP
  │   ├─> DATA_AGENT_REGISTER_PORT
  │   └─> DATA_AGENT_IP
  │
  └─> asyncio.run(run_data_agent(...))
      │
      ├─> ClickHouseDatabase()  # 初始化数据库
      │
      ├─> DataAgentKlineManager(db, max_symbols)
      │   ├─> 初始化连接字典: _active_connections
      │   ├─> 初始化锁: _lock
      │   ├─> 启动定期检查任务: _check_task
      │   └─> 启动定期ping任务: _ping_task
      │
      ├─> run_data_agent_command_server(...)  # 指令服务器
      │   ├─> create_command_handler()
      │   ├─> ThreadingHTTPServer((host, port), handler)
      │   └─> 启动服务器线程
      │
      ├─> run_data_agent_status_server(...)  # 状态服务器
      │   ├─> create_status_handler()
      │   ├─> ThreadingHTTPServer((host, port), handler)
      │   └─> 启动服务器线程
      │
      ├─> register_to_async_agent(...)  # 注册到管理器
      │   └─> POST http://register_ip:register_port/register
      │
      ├─> cleanup_task()  # 定期清理任务
      │   └─> 每小时清理过期连接
      │
      └─> self_update_status_task()  # 定期更新状态
          └─> 每分钟更新连接信息到数据库
```

### 场景2: 批量添加Symbol流程

```
外部请求: POST http://localhost:9999/symbols/add
  │
  └─> DataAgentCommandHandler.do_POST()
      │
      └─> _handle_add_symbols()
          │
          ├─> 解析请求体 JSON
          │   └─> {"symbols": ["BTCUSDT", "ETHUSDT", ...]}
          │
          ├─> 遍历每个 symbol
          │   │
          │   └─> 对每个 symbol:
          │       │
          │       ├─> asyncio.run_coroutine_threadsafe(
          │       │       kline_manager.add_symbol_streams(symbol),
          │       │       main_loop
          │       │   )
          │       │
          │       └─> add_symbol_streams(symbol)
          │           │
          │           ├─> 检查已有连接 (持有锁)
          │           │   └─> 遍历 KLINE_INTERVALS (7个)
          │           │
          │           └─> 为每个 interval 调用 add_stream()
          │               │
          │               ├─> step1_init_client()
          │               │   └─> 初始化 Binance SDK 客户端
          │               │
          │               ├─> step2_rate_limit_check()
          │               │   └─> 检查订阅频率限制 (每秒最多10个)
          │               │
          │               ├─> step3_create_connection()
          │               │   └─> SDK.create_connection() (超时15秒)
          │               │
          │               ├─> step4_register_connection_error_handler()
          │               │   └─> connection.on("error", handler)
          │               │
          │               ├─> step5_subscribe_kline_stream()
          │               │   └─> connection.kline_candlestick_streams() (超时15秒)
          │               │
          │               ├─> step6_register_message_handler()
          │               │   └─> stream.on("message", handler)
          │               │
          │               └─> step7_save_connection()
          │                   └─> 保存到 _active_connections (持有锁)
          │
          ├─> 收集所有结果
          │
          ├─> get_connection_status()  # 获取当前状态
          │
          └─> 返回响应 JSON
```

### 场景3: K线消息处理流程

```
Binance WebSocket 收到消息
  │
  └─> stream.on("message") 回调
      │
      └─> handler(data)  # 在 step6 中注册的处理器
          │
          └─> asyncio.create_task(
                  _handle_kline_message(symbol, interval, data)
              )
              │
              └─> _handle_kline_message()
                  │
                  ├─> _normalize_kline(message)
                  │   └─> 规范化K线数据格式
                  │
                  └─> asyncio.to_thread(
                          db.insert_market_klines([normalized])
                      )
                      └─> 插入到 ClickHouse 数据库
```

---

## 服务端口构建

### 端口1: 指令服务器 (端口 9999)

**构建流程：**

```
run_data_agent_command_server(kline_manager, host='0.0.0.0', port=9999)
  │
  ├─> 获取主事件循环: asyncio.get_event_loop()
  │
  ├─> 创建处理器工厂: create_command_handler(kline_manager, main_loop)
  │   └─> 返回: DataAgentCommandHandler(kline_manager, main_loop, ...)
  │
  ├─> 创建 HTTP 服务器: ThreadingHTTPServer((host, port), handler)
  │   └─> 使用多线程模式，每个请求在独立线程中处理
  │
  ├─> 启动服务器线程
  │   └─> threading.Thread(target=run_server, daemon=True)
  │       └─> server.serve_forever()
  │
  ├─> 等待服务器启动: await asyncio.sleep(1)
  │
  ├─> 验证端口监听: socket.connect_ex()
  │
  └─> 保持运行: while True: await asyncio.sleep(1)
```

**特点：**
- 使用 `ThreadingHTTPServer`，支持并发请求
- 每个请求在独立线程中处理，避免阻塞
- 守护线程，主进程退出时自动退出

### 端口2: 状态服务器 (端口 9988)

**构建流程：**

```
run_data_agent_status_server(kline_manager, host='0.0.0.0', port=9988)
  │
  ├─> 获取主事件循环: asyncio.get_event_loop()
  │
  ├─> 创建处理器工厂: create_status_handler(kline_manager, main_loop)
  │   └─> 返回: DataAgentStatusHandler(kline_manager, main_loop, ...)
  │
  ├─> 创建 HTTP 服务器: ThreadingHTTPServer((host, port), handler)
  │
  ├─> 启动服务器线程
  │   └─> threading.Thread(target=run_server, daemon=True)
  │       └─> server.serve_forever()
  │
  ├─> 等待服务器启动: await asyncio.sleep(0.5)
  │
  └─> 保持运行: while True: await asyncio.sleep(1)
```

**特点：**
- 独立端口，避免指令服务阻塞
- 仅处理轻量级健康检查请求
- 不执行任何异步操作，快速响应

---

## HTTP请求处理流程

### 指令服务器请求处理 (端口 9999)

#### GET 请求处理链

```
HTTP GET 请求到达
  │
  └─> DataAgentCommandHandler.do_GET()
      │
      ├─> 解析路径: urllib.parse.urlparse(self.path)
      │
      └─> 路由分发:
          │
          ├─> /ping
          │   └─> _handle_ping()
          │       └─> 返回: {"status": "ok", "message": "pong"}
          │
          ├─> /connections/count
          │   └─> _handle_get_connection_count()
          │       ├─> asyncio.run_coroutine_threadsafe(
          │       │       kline_manager.get_connection_count(),
          │       │       main_loop
          │       │   )
          │       └─> 返回: {"connection_count": int}
          │
          ├─> /connections/list
          │   └─> _handle_get_connection_list()
          │       ├─> asyncio.run_coroutine_threadsafe(
          │       │       kline_manager.get_connection_list(),
          │       │       main_loop
          │       │   )
          │       └─> 返回: {"connections": [...], "count": int}
          │
          ├─> /symbols
          │   └─> _handle_get_symbols()
          │       ├─> asyncio.run_coroutine_threadsafe(
          │       │       kline_manager.get_symbols(),
          │       │       main_loop
          │       │   )
          │       └─> 返回: {"symbols": [...], "count": int}
          │
          └─> /status
              └─> _handle_get_status()
                  ├─> asyncio.run_coroutine_threadsafe(
                  │       kline_manager.get_connection_status(),
                  │       main_loop
                  │   )
                  └─> 返回: {"status": "ok", "connection_count": int, "symbols": [...]}
```

#### POST 请求处理链

```
HTTP POST 请求到达
  │
  └─> DataAgentCommandHandler.do_POST()
      │
      ├─> 解析路径: urllib.parse.urlparse(self.path)
      │
      ├─> 读取请求体: self.rfile.read(content_length)
      │
      └─> 路由分发:
          │
          ├─> /streams/add
          │   └─> _handle_add_stream()
          │       ├─> 解析 JSON: {"symbol": "BTCUSDT", "interval": "1m"}
          │       ├─> asyncio.run_coroutine_threadsafe(
          │       │       kline_manager.add_stream(symbol, interval),
          │       │       main_loop
          │       │   )
          │       ├─> future.result(timeout=30)  # 超时30秒
          │       └─> 返回: {"status": "ok", "message": "..."}
          │
          ├─> /streams/remove
          │   └─> _handle_remove_stream()
          │       ├─> 解析 JSON: {"symbol": "BTCUSDT", "interval": "1m"}
          │       ├─> asyncio.run_coroutine_threadsafe(
          │       │       kline_manager.remove_stream(symbol, interval),
          │       │       main_loop
          │       │   )
          │       ├─> future.result(timeout=10)  # 超时10秒
          │       └─> 返回: {"status": "ok", "message": "..."}
          │
          └─> /symbols/add
              └─> _handle_add_symbols()
                  ├─> 解析 JSON: {"symbols": ["BTCUSDT", "ETHUSDT", ...]}
                  ├─> 遍历每个 symbol
                  │   └─> 对每个 symbol:
                  │       ├─> asyncio.run_coroutine_threadsafe(
                  │       │       kline_manager.add_symbol_streams(symbol),
                  │       │       main_loop
                  │       │   )
                  │       └─> future.result(timeout=30)  # 每个symbol超时30秒
                  ├─> get_connection_status()  # 获取最终状态
                  └─> 返回: {
                          "status": "ok|partial",
                          "results": [...],
                          "current_status": {...},
                          "summary": {...}
                      }
```

### 状态服务器请求处理 (端口 9988)

```
HTTP GET 请求到达
  │
  └─> DataAgentStatusHandler.do_GET()
      │
      ├─> 解析路径: urllib.parse.urlparse(self.path)
      │
      └─> 路由分发:
          │
          └─> /ping
              └─> _handle_ping()
                  └─> 返回: {"status": "ok", "message": "pong"}
                  # 注意：不执行任何异步操作，快速响应
```

---

## 外部可调用API

### 指令服务器 API (端口 9999)

#### GET 接口

| 路径 | 说明 | 返回格式 |
|------|------|----------|
| `/ping` | 健康检查 | `{"status": "ok", "message": "pong"}` |
| `/connections/count` | 获取连接数 | `{"connection_count": int}` |
| `/connections/list` | 获取连接列表 | `{"connections": [...], "count": int}` |
| `/symbols` | 获取symbol列表 | `{"symbols": [...], "count": int}` |
| `/status` | 获取连接状态 | `{"status": "ok", "connection_count": int, "symbols": [...]}` |

#### POST 接口

| 路径 | 说明 | 请求体 | 返回格式 |
|------|------|--------|----------|
| `/streams/add` | 添加单个K线流 | `{"symbol": "BTCUSDT", "interval": "1m"}` | `{"status": "ok", "message": "..."}` |
| `/streams/remove` | 移除单个K线流 | `{"symbol": "BTCUSDT", "interval": "1m"}` | `{"status": "ok", "message": "..."}` |
| `/symbols/add` | 批量添加symbol | `{"symbols": ["BTCUSDT", "ETHUSDT", ...]}` | `{"status": "ok|partial", "results": [...], "current_status": {...}, "summary": {...}}` |

### 状态服务器 API (端口 9988)

| 路径 | 说明 | 返回格式 |
|------|------|----------|
| `/ping` | 健康检查（轻量级） | `{"status": "ok", "message": "pong"}` |

---

## 内部调用链逻辑

### 1. 添加流 (add_stream) 调用链

```
add_stream(symbol, interval)
  │
  ├─> 验证 interval 是否支持
  │
  ├─> 获取锁: async with self._lock
  │   ├─> 检查连接是否已存在
  │   ├─> 如果存在且活跃，返回 True
  │   ├─> 如果存在但过期，关闭并删除
  │   └─> 检查 symbol 数量限制
  │
  ├─> step1_init_client()
  │   └─> 初始化 Binance SDK 客户端（懒加载）
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
  │       └─> handler 调用 _handle_kline_message()
  │
  └─> step7_save_connection()
      └─> 保存到 _active_connections (持有锁)
```

### 2. 批量添加Symbol (add_symbol_streams) 调用链

```
add_symbol_streams(symbol)
  │
  ├─> 获取锁: async with self._lock
  │   └─> 检查已有连接（遍历7个interval）
  │
  └─> 遍历 KLINE_INTERVALS (7个)
      │
      └─> 对每个 interval:
          ├─> 如果已存在，跳过
          │
          └─> 如果不存在，调用 add_stream()
              └─> (见上面的调用链)
```

### 3. K线消息处理调用链

```
WebSocket 收到消息
  │
  └─> stream.on("message") 回调
      │
      └─> handler(data)
          │
          └─> asyncio.create_task(
                  _handle_kline_message(symbol, interval, data)
              )
              │
              └─> _handle_kline_message()
                  │
                  ├─> _normalize_kline(message)
                  │   └─> 规范化K线数据格式
                  │
                  └─> asyncio.to_thread(
                          db.insert_market_klines([normalized])
                      )
                      └─> 插入到 ClickHouse 数据库
```

### 4. 清理连接调用链

```
cleanup_all()
  │
  ├─> 标记为正在关闭: self._is_closing = True
  │
  ├─> 取消后台任务
  │   ├─> _check_task.cancel()
  │   └─> _ping_task.cancel()
  │
  ├─> 获取锁: async with self._lock
  │   └─> 收集所有连接并清空字典
  │
  └─> 在锁外关闭所有连接
      └─> 对每个连接:
          └─> asyncio.wait_for(conn.close(), timeout=5.0)
              ├─> stream.unsubscribe()
              └─> connection.close_connection()
```

---

## 核心业务场景

### 场景1: 服务启动和初始化

**调用链：**
```
main()
  └─> run_data_agent()
      ├─> 初始化数据库连接
      ├─> 创建 DataAgentKlineManager
      ├─> 启动指令服务器 (端口 9999)
      ├─> 启动状态服务器 (端口 9988)
      ├─> 注册到 async_agent
      ├─> 启动清理任务
      └─> 启动状态更新任务
```

**关键点：**
- 两个独立的HTTP服务器，分别处理指令和状态检查
- 使用多线程模式，支持并发请求
- 后台任务自动运行（清理、状态更新）

### 场景2: 批量添加Symbol

**调用链：**
```
POST /symbols/add
  └─> _handle_add_symbols()
      └─> 对每个 symbol:
          └─> add_symbol_streams(symbol)
              └─> 对每个 interval (7个):
                  └─> add_stream(symbol, interval)
                      ├─> step1: 初始化客户端
                      ├─> step2: 频率限制检查
                      ├─> step3: 创建连接
                      ├─> step4: 注册错误处理器
                      ├─> step5: 订阅流
                      ├─> step6: 注册消息处理器
                      └─> step7: 保存连接
```

**关键点：**
- 每个symbol创建7个interval的连接
- 频率限制：每秒最多10个订阅
- 每个步骤都有超时保护
- 支持批量处理，每个symbol独立处理

### 场景3: 接收和处理K线消息

**调用链：**
```
Binance WebSocket 消息
  └─> stream.on("message") 回调
      └─> handler(data)
          └─> _handle_kline_message()
              ├─> _normalize_kline()  # 规范化数据
              └─> db.insert_market_klines()  # 插入数据库
```

**关键点：**
- 异步处理消息，不阻塞WebSocket接收
- 数据规范化后插入数据库
- 使用线程池执行数据库操作

### 场景4: 查询连接状态

**调用链：**
```
GET /status
  └─> _handle_get_status()
      └─> get_connection_status()
          ├─> cleanup_expired_connections()  # 清理过期连接
          ├─> _cleanup_broken_connections()  # 清理断开连接
          └─> 计算连接数和symbol列表
```

**关键点：**
- 自动清理过期和断开的连接
- 返回当前活跃连接的状态
- 在锁外执行清理操作，避免阻塞

### 场景5: 定期清理任务

**调用链：**
```
cleanup_task() (每小时执行)
  └─> cleanup_expired_connections()
      ├─> 收集过期连接 (持有锁)
      ├─> 从字典中删除 (持有锁)
      └─> 在锁外关闭连接
          └─> asyncio.wait_for(conn.close(), timeout=5.0)
```

**关键点：**
- 定期清理超过24小时的连接
- 不在持有锁的情况下关闭连接
- 添加超时保护，避免卡住

---

## 关键设计模式

### 1. 线程模型
- **HTTP服务器**: 多线程模式 (`ThreadingHTTPServer`)
- **异步操作**: 通过 `asyncio.run_coroutine_threadsafe()` 在事件循环中执行
- **消息处理**: 异步任务 (`asyncio.create_task`)

### 2. 锁机制
- **连接字典**: 使用 `asyncio.Lock()` 保护
- **原则**: 不在持有锁的情况下调用可能阻塞的操作
- **清理操作**: 先收集，释放锁，然后执行

### 3. 超时保护
- **SDK调用**: 15秒超时
- **HTTP请求**: 10-30秒超时
- **连接关闭**: 5秒超时

### 4. 错误处理
- **连接错误**: 自动清理断开的连接
- **流错误**: 自动移除错误的流
- **异常捕获**: 所有关键操作都有异常处理

---

## 数据流图

```
┌─────────────────────────────────────────────────────────────┐
│                    外部请求                                  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│          HTTP 服务器 (ThreadingHTTPServer)                  │
│  ┌────────────────────┐  ┌────────────────────┐           │
│  │ CommandHandler     │  │ StatusHandler       │           │
│  │ (端口 9999)        │  │ (端口 9988)        │           │
│  └────────────────────┘  └────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│    asyncio.run_coroutine_threadsafe()                       │
│    (将同步HTTP请求转换为异步操作)                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│          DataAgentKlineManager                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 连接管理: _active_connections (Dict)                 │   │
│  │ 锁: _lock (asyncio.Lock)                            │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 流管理方法                                           │   │
│  │ - add_stream()                                      │   │
│  │ - add_symbol_streams()                              │   │
│  │ - remove_stream()                                   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│          Binance WebSocket SDK                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ - create_connection()                               │   │
│  │ - kline_candlestick_streams()                       │   │
│  │ - stream.on("message")                              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│          K线消息处理                                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ _handle_kline_message()                              │   │
│  │   ├─> _normalize_kline()                            │   │
│  │   └─> db.insert_market_klines()                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│          ClickHouse 数据库                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 关键方法说明

### 外部可调用方法 (DataAgentKlineManager)

| 方法 | 说明 | 参数 | 返回 |
|------|------|------|------|
| `add_stream(symbol, interval)` | 添加单个K线流 | symbol: str, interval: str | bool |
| `add_symbol_streams(symbol)` | 为symbol添加所有interval的流 | symbol: str | Dict |
| `remove_stream(symbol, interval)` | 移除单个K线流 | symbol: str, interval: str | bool |
| `get_connection_count()` | 获取连接数 | - | int |
| `get_connection_list()` | 获取连接列表 | - | List[Dict] |
| `get_connection_status()` | 获取连接状态 | - | Dict |
| `get_symbols()` | 获取symbol列表 | - | Set[str] |
| `cleanup_all()` | 清理所有连接 | - | None |

### 内部方法 (DataAgentKlineManager)

| 方法 | 说明 | 调用位置 |
|------|------|----------|
| `step1_init_client()` | 初始化客户端 | add_stream() |
| `step2_rate_limit_check()` | 频率限制检查 | add_stream() |
| `step3_create_connection()` | 创建连接 | add_stream() |
| `step4_register_connection_error_handler()` | 注册错误处理器 | add_stream() |
| `step5_subscribe_kline_stream()` | 订阅流 | add_stream() |
| `step6_register_message_handler()` | 注册消息处理器 | add_stream() |
| `step7_save_connection()` | 保存连接 | add_stream() |
| `_handle_kline_message()` | 处理K线消息 | stream.on("message") |
| `_remove_broken_connection()` | 移除断开连接 | 错误处理器 |
| `cleanup_expired_connections()` | 清理过期连接 | 定期任务 |
| `_cleanup_broken_connections()` | 清理断开连接 | 定期任务 |

---

## 总结

Data Agent 系统采用分层架构设计：

1. **HTTP服务器层**: 处理外部请求，使用多线程模式支持并发
2. **管理器层**: DataAgentKlineManager 管理所有连接和流
3. **SDK层**: Binance WebSocket SDK 处理底层连接和消息
4. **数据库层**: ClickHouse 存储K线数据

关键设计：
- ✅ 异步操作通过事件循环执行
- ✅ 锁机制保护共享资源
- ✅ 超时保护避免卡住
- ✅ 错误处理确保系统稳定
- ✅ 定期清理保持系统健康

