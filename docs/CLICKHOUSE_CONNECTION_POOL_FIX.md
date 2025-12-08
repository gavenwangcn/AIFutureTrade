# ClickHouse 连接池修复说明

## 问题描述

遇到 `IncompleteRead` 和 `ProtocolError` 错误，怀疑是数据库连接池泄露或连接未正确回收导致的。

错误信息：
```
http.client.IncompleteRead: IncompleteRead(43124 bytes read, 3760 more expected)
urllib3.exceptions.ProtocolError: ('Connection broken: IncompleteRead(...)', IncompleteRead(...))
```

## 问题分析

1. **连接损坏未正确处理**：当发生 `IncompleteRead` 或 `ProtocolError` 时，连接已经损坏，但可能没有被正确关闭
2. **连接计数不准确**：损坏的连接被关闭后，连接计数可能没有正确减少
3. **异常处理不完善**：在 `_with_connection` 方法中，异常处理逻辑可能导致连接泄露

## 修复内容

### 1. 改进 `database_clickhouse.py` 中的 `_with_connection` 方法

**修复点：**
- 添加了 `finally` 块，确保连接总是被正确处理
- 区分网络错误和非网络错误，对网络错误（如 `IncompleteRead`、`ProtocolError`）进行特殊处理
- 网络错误时关闭损坏的连接并减少连接计数，而不是放回池中
- 添加了连接状态标记，避免重复处理

**关键改进：**
```python
# 检测网络错误
is_network_error = any(keyword in error_msg.lower() for keyword in [
    'connection', 'broken', 'aborted', 'protocol', 'chunk', 
    'incompleteread', 'incomplete read', 'timeout', 'reset',
    ...
])

# 网络错误时关闭连接
if is_network_error:
    client.close()
    # 减少连接计数
    with self._pool._lock:
        if self._pool._current_connections > 0:
            self._pool._current_connections -= 1
```

### 2. 增强连接健康检查

**修复点：**
- 改进了 `_is_connection_healthy` 方法，能够识别网络错误
- 添加了更详细的日志记录，帮助诊断问题

### 3. 修复 `database_basic.py` 中的连接处理

**修复点：**
- 添加了网络错误检测和处理
- 使用 `connection_handled` 标志避免连接被重复处理
- 确保损坏的连接被正确关闭

### 4. 添加连接池监控功能

**新增方法：**
- `get_pool_stats()`: 获取连接池统计信息，包括当前连接数、池大小、最大/最小连接数

**使用示例：**
```python
stats = pool.get_pool_stats()
logger.info(f"Connection pool stats: {stats}")
```

## 修复效果

1. **连接泄露问题**：损坏的连接现在会被正确关闭，不会泄露
2. **连接计数准确性**：连接计数现在会正确更新
3. **错误处理**：网络错误会被正确识别和处理
4. **可观测性**：添加了连接池统计功能，便于监控和诊断

## 建议的监控措施

1. **定期检查连接池状态**：
   ```python
   stats = db._pool.get_pool_stats()
   if stats['current_connections'] > stats['max_connections'] * 0.8:
       logger.warning(f"Connection pool usage high: {stats}")
   ```

2. **监控网络错误**：
   - 关注日志中的 "Network/Protocol error" 警告
   - 如果频繁出现，可能需要检查网络连接或 ClickHouse 服务器状态

3. **连接池配置建议**：
   - `min_connections`: 5（当前值）
   - `max_connections`: 50（当前值）
   - `connection_timeout`: 30秒（当前值）

## 注意事项

1. **连接超时设置**：
   - `connect_timeout`: 10秒
   - `send_receive_timeout`: 30秒
   - `max_execution_time`: 30秒

2. **重试机制**：
   - 网络错误会自动重试（最多3次）
   - 使用指数退避策略

3. **连接健康检查**：
   - 在 `acquire()` 时进行健康检查
   - 不健康的连接会被替换

## 相关文件

- `common/database_clickhouse.py`: ClickHouse 连接池实现
- `common/database_basic.py`: 基础数据库操作（使用连接池）

## 测试建议

1. **压力测试**：在高并发场景下测试连接池是否正常工作
2. **网络错误模拟**：模拟网络中断，验证连接是否正确恢复
3. **连接泄露检测**：长时间运行后检查连接池状态

