# Data Agent 调用链可视化图表

## 1. 系统启动流程

```mermaid
graph TD
    A[main函数] --> B[_setup_logging]
    A --> C[读取配置]
    A --> D[asyncio.run run_data_agent]
    
    D --> E[ClickHouseDatabase初始化]
    D --> F[DataAgentKlineManager初始化]
    D --> G[启动指令服务器 端口9999]
    D --> H[启动状态服务器 端口9988]
    D --> I[注册到async_agent]
    D --> J[启动清理任务]
    D --> K[启动状态更新任务]
    
    F --> F1[初始化连接字典]
    F --> F2[初始化锁]
    F --> F3[启动定期检查任务]
    F --> F4[启动定期ping任务]
    
    G --> G1[create_command_handler]
    G --> G2[ThreadingHTTPServer]
    G --> G3[启动服务器线程]
    
    H --> H1[create_status_handler]
    H --> H2[ThreadingHTTPServer]
    H --> H3[启动服务器线程]
```

## 2. HTTP请求处理流程

```mermaid
graph TD
    A[HTTP请求到达] --> B{请求类型}
    
    B -->|GET| C[do_GET方法]
    B -->|POST| D[do_POST方法]
    
    C --> C1{路径路由}
    C1 -->|/ping| C2[_handle_ping]
    C1 -->|/connections/count| C3[_handle_get_connection_count]
    C1 -->|/connections/list| C4[_handle_get_connection_list]
    C1 -->|/symbols| C5[_handle_get_symbols]
    C1 -->|/status| C6[_handle_get_status]
    
    D --> D1{路径路由}
    D1 -->|/streams/add| D2[_handle_add_stream]
    D1 -->|/streams/remove| D3[_handle_remove_stream]
    D1 -->|/symbols/add| D4[_handle_add_symbols]
    
    C3 --> E[asyncio.run_coroutine_threadsafe]
    C4 --> E
    C5 --> E
    C6 --> E
    D2 --> E
    D3 --> E
    D4 --> E
    
    E --> F[DataAgentKlineManager方法]
    F --> G[返回结果]
    G --> H[_send_json响应]
```

## 3. 批量添加Symbol完整流程

```mermaid
graph TD
    A[POST /symbols/add] --> B[_handle_add_symbols]
    B --> C[解析JSON请求体]
    C --> D[遍历每个symbol]
    
    D --> E[对每个symbol]
    E --> F[asyncio.run_coroutine_threadsafe]
    F --> G[add_symbol_streams]
    
    G --> H[检查已有连接 持有锁]
    H --> I[遍历7个interval]
    
    I --> J{连接是否存在?}
    J -->|是| K[跳过]
    J -->|否| L[add_stream]
    
    L --> M[step1_init_client]
    L --> N[step2_rate_limit_check]
    L --> O[step3_create_connection]
    L --> P[step4_register_connection_error_handler]
    L --> Q[step5_subscribe_kline_stream]
    L --> R[step6_register_message_handler]
    L --> S[step7_save_connection]
    
    M --> M1[初始化Binance SDK客户端]
    N --> N1[检查订阅频率限制]
    O --> O1[SDK.create_connection 超时15秒]
    P --> P1[connection.on error handler]
    Q --> Q1[connection.kline_candlestick_streams 超时15秒]
    R --> R1[stream.on message handler]
    S --> S1[保存到_active_connections 持有锁]
    
    S1 --> T[收集结果]
    T --> U[get_connection_status]
    U --> V[返回JSON响应]
```

## 4. 添加单个流 (add_stream) 详细流程

```mermaid
graph TD
    A[add_stream symbol interval] --> B{验证interval}
    B -->|不支持| C[返回False]
    B -->|支持| D[获取锁]
    
    D --> E{连接是否存在?}
    E -->|存在且活跃| F[返回True]
    E -->|存在但过期| G[关闭并删除]
    E -->|不存在| H[检查symbol数量限制]
    
    G --> H
    H --> I{超过限制?}
    I -->|是| J[返回False]
    I -->|否| K[释放锁]
    
    K --> L[step1_init_client]
    L --> M[step2_rate_limit_check]
    M --> N[step3_create_connection]
    N --> O[step4_register_connection_error_handler]
    O --> P[step5_subscribe_kline_stream]
    P --> Q[step6_register_message_handler]
    Q --> R[step7_save_connection]
    
    L --> L1{客户端已初始化?}
    L1 -->|是| M
    L1 -->|否| L2[创建DerivativesTradingUsdsFutures]
    L2 --> M
    
    M --> M1{频率限制检查}
    M1 -->|需要等待| M2[await asyncio.sleep]
    M1 -->|通过| N
    M2 --> N
    
    N --> N1[SDK.create_connection 超时15秒]
    N1 --> N2{成功?}
    N2 -->|否| N3[返回False]
    N2 -->|是| O
    
    O --> O1[connection.on error]
    P --> P1[connection.kline_candlestick_streams 超时15秒]
    P1 --> P2{成功?}
    P2 -->|否| P3[关闭连接 返回False]
    P2 -->|是| Q
    
    Q --> Q1[stream.on message]
    Q1 --> Q2[stream.on error]
    R --> R1[获取锁]
    R1 --> R2[创建KlineStreamConnection]
    R2 --> R3[保存到_active_connections]
    R3 --> R4[释放锁]
    R4 --> S[返回True]
```

## 5. K线消息处理流程

```mermaid
graph TD
    A[Binance WebSocket收到消息] --> B[stream.on message回调]
    B --> C[handler函数]
    C --> D[asyncio.create_task]
    D --> E[_handle_kline_message]
    
    E --> F[_normalize_kline]
    F --> F1{规范化成功?}
    F1 -->|否| G[记录错误]
    F1 -->|是| H[asyncio.to_thread]
    
    H --> I[db.insert_market_klines]
    I --> J[插入到ClickHouse]
    J --> K{插入成功?}
    K -->|是| L[记录调试日志]
    K -->|否| M[记录错误日志]
```

## 6. 连接清理流程

```mermaid
graph TD
    A[cleanup_all] --> B[标记_is_closing=True]
    B --> C[取消后台任务]
    C --> C1[_check_task.cancel]
    C --> C2[_ping_task.cancel]
    
    C1 --> D[获取锁]
    C2 --> D
    D --> E[收集所有连接]
    E --> F[清空_active_connections]
    F --> G[释放锁]
    
    G --> H[在锁外关闭连接]
    H --> I[遍历所有连接]
    I --> J[asyncio.wait_for conn.close timeout=5s]
    J --> K{关闭成功?}
    K -->|是| L[记录日志]
    K -->|超时| M[记录警告]
    K -->|异常| N[记录警告]
    
    L --> O{还有连接?}
    M --> O
    N --> O
    O -->|是| I
    O -->|否| P[清理完成]
```

## 7. 定期任务流程

```mermaid
graph TD
    A[run_data_agent] --> B[启动定期任务]
    
    B --> C[cleanup_task 每小时]
    B --> D[self_update_status_task 每分钟]
    B --> E[_periodic_connection_check 后台]
    B --> F[_periodic_ping 后台]
    
    C --> C1[await asyncio.sleep 3600]
    C1 --> C2[cleanup_expired_connections]
    C2 --> C1
    
    D --> D1[await asyncio.sleep 60]
    D1 --> D2[get_connection_status]
    D2 --> D3[db.update_agent_connection_info]
    D3 --> D1
    
    E --> E1[定期检查连接状态]
    F --> F1[定期发送ping]
```

## 8. 错误处理流程

```mermaid
graph TD
    A[连接错误] --> B[connection.on error回调]
    B --> C[asyncio.create_task]
    C --> D[_remove_broken_connection]
    
    D --> E[获取锁]
    E --> F{连接在字典中?}
    F -->|是| G[标记is_active=False]
    F -->|否| H[结束]
    G --> I[关闭连接]
    I --> J[从字典中删除]
    J --> K[释放锁]
    
    L[流错误] --> M[stream.on error回调]
    M --> N[asyncio.create_task]
    N --> D
```

## 9. 服务端口架构

```mermaid
graph LR
    A[外部客户端] -->|HTTP请求| B[端口9999 指令服务器]
    A -->|健康检查| C[端口9988 状态服务器]
    
    B --> D[ThreadingHTTPServer]
    D --> E[DataAgentCommandHandler]
    E --> F[多线程处理]
    F --> G[asyncio.run_coroutine_threadsafe]
    G --> H[主事件循环]
    
    C --> I[ThreadingHTTPServer]
    I --> J[DataAgentStatusHandler]
    J --> K[轻量级响应]
    
    H --> L[DataAgentKlineManager]
    L --> M[Binance WebSocket SDK]
    M --> N[Binance服务器]
    
    N -->|K线消息| M
    M -->|消息回调| L
    L -->|处理消息| O[ClickHouse数据库]
```

## 10. 数据流图

```mermaid
flowchart TD
    A[外部请求] --> B[HTTP服务器]
    B --> C[Handler处理]
    C --> D[asyncio.run_coroutine_threadsafe]
    D --> E[DataAgentKlineManager]
    E --> F[Binance SDK]
    F --> G[WebSocket连接]
    G -->|接收消息| H[消息处理器]
    H --> I[数据规范化]
    I --> J[数据库插入]
    
    style A fill:#e1f5ff
    style B fill:#fff4e1
    style E fill:#e8f5e9
    style F fill:#f3e5f5
    style J fill:#ffebee
```

## 11. 并发处理模型

```mermaid
graph TD
    A[HTTP请求1] --> B[Thread 1]
    A2[HTTP请求2] --> C[Thread 2]
    A3[HTTP请求3] --> D[Thread 3]
    
    B --> E[asyncio.run_coroutine_threadsafe]
    C --> E
    D --> E
    
    E --> F[主事件循环]
    F --> G[DataAgentKlineManager]
    
    G --> H[连接1]
    G --> I[连接2]
    G --> J[连接3]
    
    H --> K[WebSocket消息1]
    I --> L[WebSocket消息2]
    J --> M[WebSocket消息3]
    
    K --> N[asyncio.create_task]
    L --> N
    M --> N
    
    N --> O[消息处理任务池]
    O --> P[数据库插入]
```

## 12. 锁机制使用

```mermaid
graph TD
    A[操作需要访问_active_connections] --> B{需要关闭连接?}
    
    B -->|否| C[直接获取锁]
    B -->|是| D[先收集需要操作的对象]
    
    C --> E[async with self._lock]
    E --> F[执行操作]
    F --> G[释放锁]
    
    D --> H[获取锁]
    H --> I[收集对象到列表]
    I --> J[从字典中删除]
    J --> K[释放锁]
    K --> L[在锁外关闭连接]
    L --> M[asyncio.wait_for timeout=5s]
```

---

## 关键调用链总结

### 1. 服务启动链
```
main() 
  → run_data_agent() 
    → 初始化管理器 
    → 启动HTTP服务器 
    → 启动后台任务
```

### 2. 添加Symbol链
```
POST /symbols/add 
  → _handle_add_symbols() 
    → add_symbol_streams() 
      → add_stream() 
        → step1-7 (7个步骤)
```

### 3. 消息处理链
```
WebSocket消息 
  → stream.on("message") 
    → _handle_kline_message() 
      → _normalize_kline() 
        → db.insert_market_klines()
```

### 4. 清理资源链
```
cleanup_all() 
  → 取消任务 
    → 收集连接 
      → 在锁外关闭连接
```

