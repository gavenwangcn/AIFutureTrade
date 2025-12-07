# Data Agent 调用链 PlantUML 时序图

本文档包含 Data Agent 系统的 PlantUML 时序图，便于查看和编辑。

---

## 1. 系统启动流程

```plantuml
@startuml 系统启动流程
participant "main()" as main
participant "run_data_agent()" as run
participant "ClickHouseDatabase" as db
participant "DataAgentKlineManager" as manager
participant "指令服务器" as cmd_server
participant "状态服务器" as status_server
participant "async_agent" as async_agent

main -> run: asyncio.run()
run -> db: 初始化数据库连接
run -> manager: DataAgentKlineManager(db, max_symbols)
activate manager
manager -> manager: 初始化连接字典
manager -> manager: 初始化锁
manager -> manager: 启动定期检查任务
manager -> manager: 启动定期ping任务
deactivate manager

run -> cmd_server: run_data_agent_command_server()
activate cmd_server
cmd_server -> cmd_server: create_command_handler()
cmd_server -> cmd_server: ThreadingHTTPServer(端口9999)
cmd_server -> cmd_server: 启动服务器线程
deactivate cmd_server

run -> status_server: run_data_agent_status_server()
activate status_server
status_server -> status_server: create_status_handler()
status_server -> status_server: ThreadingHTTPServer(端口9988)
status_server -> status_server: 启动服务器线程
deactivate status_server

run -> async_agent: register_to_async_agent()
activate async_agent
async_agent --> run: 注册成功
deactivate async_agent

run -> run: 启动清理任务
run -> run: 启动状态更新任务
@enduml
```

---

## 2. HTTP GET 请求处理流程

```plantuml
@startuml HTTP_GET请求处理流程
participant "客户端" as client
participant "ThreadingHTTPServer" as server
participant "DataAgentCommandHandler" as handler
participant "主事件循环" as loop
participant "DataAgentKlineManager" as manager

client -> server: GET /status
activate server
server -> handler: do_GET()
activate handler
handler -> handler: 解析路径
handler -> handler: _handle_get_status()
handler -> loop: asyncio.run_coroutine_threadsafe(\n  kline_manager.get_connection_status(),\n  main_loop\n)
activate loop
loop -> manager: get_connection_status()
activate manager
manager -> manager: cleanup_expired_connections()
manager -> manager: _cleanup_broken_connections()
manager -> manager: 计算连接数和symbol列表
manager --> loop: 返回状态
deactivate manager
loop --> handler: future.result(timeout=10)
deactivate loop
handler -> handler: _send_json(响应)
handler --> server: 返回JSON响应
deactivate handler
server --> client: HTTP 200 OK
deactivate server
@enduml
```

---

## 3. HTTP POST 请求处理流程（批量添加Symbol）

```plantuml
@startuml HTTP_POST批量添加Symbol
participant "客户端" as client
participant "ThreadingHTTPServer" as server
participant "DataAgentCommandHandler" as handler
participant "主事件循环" as loop
participant "DataAgentKlineManager" as manager
participant "Binance SDK" as sdk

client -> server: POST /symbols/add\n{"symbols": ["BTCUSDT", ...]}
activate server
server -> handler: do_POST()
activate handler
handler -> handler: 解析JSON请求体
handler -> handler: _handle_add_symbols()

loop 遍历每个symbol
    handler -> loop: asyncio.run_coroutine_threadsafe(\n  add_symbol_streams(symbol),\n  main_loop\n)
    activate loop
    loop -> manager: add_symbol_streams(symbol)
    activate manager
    
    manager -> manager: 检查已有连接（持有锁）
    
    loop 遍历7个interval
        manager -> manager: add_stream(symbol, interval)
        activate manager
        
        manager -> manager: step1_init_client()
        manager -> manager: step2_rate_limit_check()
        manager -> manager: step3_create_connection()
        manager -> sdk: SDK.create_connection()
        activate sdk
        sdk --> manager: 连接对象
        deactivate sdk
        
        manager -> manager: step4_register_connection_error_handler()
        manager -> manager: step5_subscribe_kline_stream()
        manager -> sdk: connection.kline_candlestick_streams()
        activate sdk
        sdk --> manager: 流对象
        deactivate sdk
        
        manager -> manager: step6_register_message_handler()
        manager -> manager: step7_save_connection()
        
        deactivate manager
    end
    
    manager --> loop: 返回结果
    deactivate manager
    loop --> handler: future.result(timeout=30)
    deactivate loop
end

handler -> loop: get_connection_status()
activate loop
loop -> manager: get_connection_status()
manager --> loop: 返回状态
deactivate loop
loop --> handler: future.result(timeout=10)
deactivate loop

handler -> handler: _send_json(汇总结果)
handler --> server: 返回JSON响应
deactivate handler
server --> client: HTTP 200 OK
deactivate server
@enduml
```

---

## 4. 添加单个流 (add_stream) 详细流程

```plantuml
@startuml 添加单个流详细流程
participant "调用者" as caller
participant "DataAgentKlineManager" as manager
participant "Binance SDK" as sdk
participant "WebSocket连接" as ws

caller -> manager: add_stream(symbol, interval)
activate manager

manager -> manager: 验证interval
alt interval不支持
    manager --> caller: 返回False
else interval支持
    manager -> manager: 获取锁: async with self._lock
    activate manager
    
    alt 连接已存在且活跃
        manager --> caller: 返回True
    else 连接存在但过期
        manager -> manager: 关闭并删除过期连接
        manager -> manager: 检查symbol数量限制
    else 连接不存在
        manager -> manager: 检查symbol数量限制
    end
    
    alt 超过symbol数量限制
        manager --> caller: 返回False
    else 未超过限制
        manager -> manager: 释放锁
        deactivate manager
        
        manager -> manager: step1_init_client()
        alt 客户端未初始化
            manager -> manager: 创建DerivativesTradingUsdsFutures
        end
        
        manager -> manager: step2_rate_limit_check()
        alt 需要等待
            manager -> manager: await asyncio.sleep(等待时间)
        end
        
        manager -> manager: step3_create_connection()
        manager -> sdk: SDK.create_connection() (超时15秒)
        activate sdk
        alt 超时
            sdk --> manager: TimeoutError
            manager --> caller: 返回False
        else 成功
            sdk --> manager: 连接对象
            deactivate sdk
            
            manager -> manager: step4_register_connection_error_handler()
            manager -> ws: connection.on("error", handler)
            
            manager -> manager: step5_subscribe_kline_stream()
            manager -> sdk: connection.kline_candlestick_streams() (超时15秒)
            activate sdk
            alt 超时
                sdk --> manager: TimeoutError
                manager -> ws: 关闭连接
                manager --> caller: 返回False
            else 成功
                sdk --> manager: 流对象
                deactivate sdk
                
                manager -> manager: step6_register_message_handler()
                manager -> ws: stream.on("message", handler)
                manager -> ws: stream.on("error", handler)
                
                manager -> manager: step7_save_connection()
                manager -> manager: 获取锁
                activate manager
                manager -> manager: 创建KlineStreamConnection
                manager -> manager: 保存到_active_connections
                manager -> manager: 释放锁
                deactivate manager
                
                manager --> caller: 返回True
            end
        end
    end
end
deactivate manager
@enduml
```

---

## 5. K线消息处理流程

```plantuml
@startuml K线消息处理流程
participant "Binance服务器" as binance
participant "WebSocket连接" as ws
participant "消息处理器" as handler
participant "DataAgentKlineManager" as manager
participant "数据规范化" as normalize
participant "ClickHouse数据库" as db

binance -> ws: K线消息
activate ws
ws -> handler: stream.on("message") 回调
activate handler
handler -> manager: asyncio.create_task(\n  _handle_kline_message(\n    symbol, interval, data\n  )\n)
activate manager

manager -> normalize: _normalize_kline(message)
activate normalize
alt 规范化成功
    normalize --> manager: 规范化后的数据
    deactivate normalize
    
    manager -> db: asyncio.to_thread(\n  db.insert_market_klines([normalized])\n)
    activate db
    db -> db: 插入K线数据
    db --> manager: 插入成功
    deactivate db
    manager -> manager: 记录调试日志
else 规范化失败
    normalize --> manager: None
    deactivate normalize
    manager -> manager: 记录错误日志
end

deactivate manager
deactivate handler
deactivate ws
@enduml
```

---

## 6. 连接清理流程

```plantuml
@startuml 连接清理流程
participant "调用者" as caller
participant "DataAgentKlineManager" as manager
participant "后台任务" as tasks
participant "连接对象" as conn

caller -> manager: cleanup_all()
activate manager

manager -> manager: 标记_is_closing=True
manager -> tasks: _check_task.cancel()
activate tasks
tasks --> manager: CancelledError
deactivate tasks

manager -> tasks: _ping_task.cancel()
activate tasks
tasks --> manager: CancelledError
deactivate tasks

manager -> manager: 获取锁: async with self._lock
activate manager
manager -> manager: 收集所有连接到列表
manager -> manager: 清空_active_connections字典
manager -> manager: 释放锁
deactivate manager

loop 遍历所有连接
    manager -> conn: asyncio.wait_for(\n  conn.close(),\n  timeout=5.0\n)
    activate conn
    
    alt 关闭成功
        conn -> conn: stream.unsubscribe()
        conn -> conn: connection.close_connection()
        conn --> manager: 关闭成功
        manager -> manager: 记录日志
    else 超时
        conn --> manager: TimeoutError
        manager -> manager: 记录警告
    else 异常
        conn --> manager: Exception
        manager -> manager: 记录警告
    end
    deactivate conn
end

manager --> caller: 清理完成
deactivate manager
@enduml
```

---

## 7. 错误处理流程（连接错误）

```plantuml
@startuml 连接错误处理流程
participant "WebSocket连接" as ws
participant "错误处理器" as error_handler
participant "DataAgentKlineManager" as manager
participant "连接对象" as conn

ws -> error_handler: connection.on("error") 回调
activate error_handler
error_handler -> manager: asyncio.create_task(\n  _remove_broken_connection(\n    symbol, interval\n  )\n)
activate manager

manager -> manager: 获取锁: async with self._lock
activate manager
manager -> manager: 检查连接是否在字典中
alt 连接在字典中
    manager -> conn: 标记is_active=False
    manager -> manager: 释放锁
    deactivate manager
    
    manager -> conn: conn.close()
    activate conn
    conn -> conn: stream.unsubscribe()
    conn -> conn: connection.close_connection()
    conn --> manager: 关闭完成
    deactivate conn
    
    manager -> manager: 再次获取锁
    activate manager
    manager -> manager: 从字典中删除连接
    manager -> manager: 释放锁
    deactivate manager
    manager -> manager: 记录日志
else 连接不在字典中
    manager -> manager: 释放锁
    deactivate manager
end

deactivate manager
deactivate error_handler
@enduml
```

---

## 8. 批量添加Symbol完整流程（简化版）

```plantuml
@startuml 批量添加Symbol简化流程
participant "客户端" as client
participant "HTTP服务器" as server
participant "Handler" as handler
participant "事件循环" as loop
participant "KlineManager" as manager
participant "Binance SDK" as sdk

client -> server: POST /symbols/add\n{"symbols": ["BTCUSDT", "ETHUSDT"]}
server -> handler: do_POST()
handler -> handler: _handle_add_symbols()

loop 对每个symbol
    handler -> loop: run_coroutine_threadsafe(\n  add_symbol_streams(symbol)\n)
    loop -> manager: add_symbol_streams(symbol)
    
    manager -> manager: 检查已有连接
    
    loop 对每个interval (7个)
        manager -> manager: add_stream(symbol, interval)
        
        manager -> manager: step1: 初始化客户端
        manager -> manager: step2: 频率限制检查
        manager -> sdk: step3: 创建连接
        sdk --> manager: 连接对象
        manager -> manager: step4: 注册错误处理器
        manager -> sdk: step5: 订阅流
        sdk --> manager: 流对象
        manager -> manager: step6: 注册消息处理器
        manager -> manager: step7: 保存连接
    end
    
    manager --> loop: 返回结果
    loop --> handler: future.result(timeout=30)
end

handler -> loop: get_connection_status()
loop -> manager: get_connection_status()
manager --> loop: 返回状态
loop --> handler: 状态信息

handler -> handler: 构建响应JSON
handler --> server: 返回响应
server --> client: HTTP 200 OK
@enduml
```

---

## 9. 定期任务流程

```plantuml
@startuml 定期任务流程
participant "run_data_agent" as main
participant "清理任务" as cleanup
participant "状态更新任务" as update
participant "KlineManager" as manager
participant "数据库" as db

main -> cleanup: 启动清理任务
activate cleanup

loop 每小时执行
    cleanup -> cleanup: await asyncio.sleep(3600)
    cleanup -> manager: cleanup_expired_connections()
    activate manager
    manager -> manager: 收集过期连接
    manager -> manager: 关闭过期连接
    manager --> cleanup: 清理完成
    deactivate manager
end

main -> update: 启动状态更新任务
activate update

loop 每分钟执行
    update -> update: await asyncio.sleep(60)
    update -> manager: get_connection_status()
    activate manager
    manager -> manager: 清理过期连接
    manager -> manager: 计算连接数和symbol列表
    manager --> update: 返回状态
    deactivate manager
    update -> db: update_agent_connection_info()
    activate db
    db --> update: 更新成功
    deactivate db
end
@enduml
```

---

## 10. 服务端口架构

```plantuml
@startuml 服务端口架构
participant "外部客户端" as client
participant "指令服务器\n(端口9999)" as cmd_server
participant "状态服务器\n(端口9988)" as status_server
participant "主事件循环" as loop
participant "KlineManager" as manager
participant "Binance SDK" as sdk
participant "Binance服务器" as binance
participant "ClickHouse" as db

client -> cmd_server: HTTP请求\n(添加/查询等)
activate cmd_server
cmd_server -> cmd_server: ThreadingHTTPServer\n多线程处理
cmd_server -> loop: run_coroutine_threadsafe()
activate loop
loop -> manager: 执行操作
activate manager
manager -> sdk: SDK调用
activate sdk
sdk -> binance: WebSocket连接
binance --> sdk: 响应
sdk --> manager: 结果
deactivate sdk
manager --> loop: 返回结果
deactivate manager
loop --> cmd_server: future.result()
deactivate loop
cmd_server --> client: HTTP响应
deactivate cmd_server

client -> status_server: GET /ping\n健康检查
activate status_server
status_server -> status_server: 轻量级响应\n不执行异步操作
status_server --> client: {"status": "ok"}
deactivate status_server

binance -> sdk: K线消息
activate sdk
sdk -> manager: stream.on("message")
activate manager
manager -> db: 插入K线数据
activate db
db --> manager: 插入成功
deactivate db
deactivate manager
deactivate sdk
@enduml
```

---

## 11. 并发处理模型

```plantuml
@startuml 并发处理模型
participant "请求1" as req1
participant "请求2" as req2
participant "请求3" as req3
participant "Thread1" as t1
participant "Thread2" as t2
participant "Thread3" as t3
participant "主事件循环" as loop
participant "KlineManager" as manager
participant "连接1" as conn1
participant "连接2" as conn2
participant "连接3" as conn3

par 并发请求
    req1 -> t1: HTTP请求1
    activate t1
    t1 -> loop: run_coroutine_threadsafe()
    activate loop
    loop -> manager: 操作1
    activate manager
    manager -> conn1: 处理连接1
    activate conn1
    conn1 --> manager: 结果1
    deactivate conn1
    manager --> loop: 返回1
    deactivate manager
    loop --> t1: future.result()
    deactivate loop
    t1 --> req1: 响应1
    deactivate t1
else
    req2 -> t2: HTTP请求2
    activate t2
    t2 -> loop: run_coroutine_threadsafe()
    activate loop
    loop -> manager: 操作2
    activate manager
    manager -> conn2: 处理连接2
    activate conn2
    conn2 --> manager: 结果2
    deactivate conn2
    manager --> loop: 返回2
    deactivate manager
    loop --> t2: future.result()
    deactivate loop
    t2 --> req2: 响应2
    deactivate t2
else
    req3 -> t3: HTTP请求3
    activate t3
    t3 -> loop: run_coroutine_threadsafe()
    activate loop
    loop -> manager: 操作3
    activate manager
    manager -> conn3: 处理连接3
    activate conn3
    conn3 --> manager: 结果3
    deactivate conn3
    manager --> loop: 返回3
    deactivate manager
    loop --> t3: future.result()
    deactivate loop
    t3 --> req3: 响应3
    deactivate t3
end
@enduml
```

---

## 12. 锁机制使用

```plantuml
@startuml 锁机制使用
participant "操作1" as op1
participant "操作2" as op2
participant "KlineManager" as manager
participant "锁" as lock
participant "连接对象" as conn

par 并发操作
    op1 -> manager: 需要访问_active_connections
    activate manager
    manager -> lock: 获取锁
    activate lock
    lock --> manager: 锁已获取
    manager -> manager: 读取/修改连接字典
    manager -> lock: 释放锁
    deactivate lock
    manager --> op1: 返回结果
    deactivate manager
else
    op2 -> manager: 需要访问_active_connections
    activate manager
    manager -> lock: 尝试获取锁
    activate lock
    note right: 等待锁释放
    lock --> manager: 锁已获取
    manager -> manager: 读取/修改连接字典
    manager -> lock: 释放锁
    deactivate lock
    manager --> op2: 返回结果
    deactivate manager
end

note over manager,lock: 清理连接时的锁使用\n1. 获取锁，收集需要清理的连接\n2. 释放锁\n3. 在锁外关闭连接（避免阻塞）\n4. 再次获取锁，从字典中删除
@enduml
```

---

## 使用说明

### 如何查看这些图表

1. **在线查看**：
   - 访问 http://www.plantuml.com/plantuml/uml/
   - 复制代码块中的 PlantUML 代码
   - 粘贴到在线编辑器中查看

2. **VS Code 插件**：
   - 安装 "PlantUML" 插件
   - 打开 `.puml` 文件或 Markdown 文件
   - 使用预览功能查看图表

3. **本地工具**：
   - 安装 PlantUML：`brew install plantuml` (Mac) 或下载 jar 文件
   - 使用命令行：`plantuml diagram.puml`
   - 生成 PNG 或 SVG 图片

### 图表说明

- **系统启动流程**：展示服务启动的完整过程
- **HTTP请求处理**：展示HTTP请求如何被处理
- **批量添加Symbol**：展示批量添加的详细流程
- **添加单个流**：展示单个流添加的所有步骤
- **K线消息处理**：展示消息从接收到存储的流程
- **连接清理**：展示资源清理的过程
- **错误处理**：展示错误发生时的处理流程
- **定期任务**：展示后台任务的执行
- **服务端口架构**：展示整体架构
- **并发处理**：展示多线程并发处理
- **锁机制**：展示锁的使用方式

### 编辑建议

如果需要修改图表：
1. 复制对应的 PlantUML 代码
2. 在 PlantUML 编辑器中编辑
3. 查看实时预览
4. 修改后更新文档

---

## 与 Mermaid 图表的对应关系

| PlantUML 图表 | Mermaid 图表 | 说明 |
|--------------|-------------|------|
| 系统启动流程 | 系统启动流程 | 对应关系 |
| HTTP GET请求处理 | HTTP请求处理流程 | 对应关系 |
| HTTP POST批量添加 | 批量添加Symbol完整流程 | 对应关系 |
| 添加单个流详细流程 | 添加单个流详细流程 | 对应关系 |
| K线消息处理流程 | K线消息处理流程 | 对应关系 |
| 连接清理流程 | 连接清理流程 | 对应关系 |
| 错误处理流程 | 错误处理流程 | 对应关系 |
| 定期任务流程 | 定期任务流程 | 对应关系 |
| 服务端口架构 | 服务端口架构 | 对应关系 |
| 并发处理模型 | 并发处理模型 | 对应关系 |
| 锁机制使用 | 锁机制使用 | 对应关系 |

---

## 总结

PlantUML 时序图提供了更详细的交互视图，特别适合：
- 展示方法调用顺序
- 展示异步操作的执行流程
- 展示并发处理的时序关系
- 展示错误处理的流程

这些图表可以与 Mermaid 图表互补使用，提供不同视角的系统视图。

