# Data Agent K线监听长期运行优化说明

## 优化目标

确保 K线监听连接长期运行，不主动关闭，持续同步K线数据到ClickHouse数据库。

## 优化内容

### 1. 连接过期时间调整

**优化前：**
```python
WS_CONNECTION_MAX_AGE = timedelta(hours=24)  # 24小时后过期
```

**优化后：**
```python
WS_CONNECTION_MAX_AGE = timedelta(days=365)  # 1年，实际上不会过期
```

**说明：** K线监听是长期运行的异步任务，连接应该一直保持活跃，不应该因为时间过期而关闭。

---

### 2. 过期连接清理逻辑调整

**优化前：**
- `cleanup_expired_connections()` 会主动关闭超过24小时的连接

**优化后：**
- `cleanup_expired_connections()` 只检查连接状态，不关闭连接
- 记录日志说明连接状态，但不执行关闭操作

**关键代码：**
```python
async def cleanup_expired_connections(self) -> None:
    """检查并处理过期的连接（实际上不会执行清理，因为连接应该长期运行）。
    
    注意：K线监听是长期运行的异步任务，不应该主动关闭连接。
    此方法保留用于检查连接状态，但不会主动关闭连接。
    只有在连接出错或服务关闭时才会关闭连接。
    """
    # 只检查连接状态，不关闭连接
    async with self._lock:
        total_connections = len(self._active_connections)
        expired_count = 0
        for key, conn in self._active_connections.items():
            if conn.is_expired():
                expired_count += 1
                logger.debug(
                    "[DataAgentKline] 🔍 [检查] 发现过期连接（但不会关闭）: %s %s (创建时间: %s)",
                    key[0], key[1], conn.created_at.isoformat()
                )
        
        if expired_count > 0:
            logger.info(
                "[DataAgentKline] 📊 [检查] 连接状态: 总数=%s, 过期数=%s (过期连接不会自动关闭，保持长期运行)",
                total_connections, expired_count
            )
```

---

### 3. 断开连接清理逻辑调整

**优化前：**
- `_cleanup_broken_connections()` 会主动关闭非活跃的连接

**优化后：**
- `_cleanup_broken_connections()` 只检查连接状态，不关闭连接
- 只有在错误处理器检测到连接确实无法使用时才会关闭

**关键代码：**
```python
async def _cleanup_broken_connections(self) -> None:
    """检查断开的连接（但不主动关闭，因为K线监听应该长期运行）。
    
    注意：K线监听是长期运行的异步任务，不应该主动关闭连接。
    此方法只检查连接状态，不关闭连接。
    只有在连接确实无法使用时（通过错误处理器检测到）才会关闭。
    """
    # 只检查连接状态，不关闭连接
    async with self._lock:
        total_connections = len(self._active_connections)
        broken_count = 0
        for key, conn in self._active_connections.items():
            if not conn.is_active:
                broken_count += 1
                logger.debug(
                    "[DataAgentKline] 🔍 [检查] 发现非活跃连接（但不会主动关闭）: %s %s",
                    key[0], key[1]
                )
    
    # 不再主动关闭连接，让连接长期运行
    # 只有在错误处理器检测到连接确实无法使用时才会关闭
    return
```

---

### 4. 定期检查任务重命名和说明

**优化前：**
```python
async def cleanup_task():
    """定期清理过期连接"""
    while True:
        await asyncio.sleep(3600)  # 每小时清理一次
        await kline_manager.cleanup_expired_connections()
```

**优化后：**
```python
async def connection_check_task():
    """定期检查连接状态，但不关闭连接。
    
    注意：K线监听是长期运行的异步任务，连接应该一直保持活跃状态。
    此任务只用于监控连接状态，不会主动关闭连接。
    """
    while True:
        await asyncio.sleep(3600)  # 每小时检查一次
        await kline_manager.cleanup_expired_connections()  # 只检查，不关闭
```

---

### 5. 类文档更新

**优化前：**
```python
class DataAgentKlineManager:
    """管理所有K线WebSocket连接。
    
    主要功能包括：
    - 过期连接清理和重连
    ...
    """
```

**优化后：**
```python
class DataAgentKlineManager:
    """管理所有K线WebSocket连接。
    
    **重要说明：K线监听是长期运行的异步任务**
    - 连接构建完成后会一直保持活跃，持续接收K线消息
    - 不会主动关闭连接（除非服务关闭或连接出错）
    - 所有连接会持续运行，同步K线数据到ClickHouse数据库
    
    主要功能包括：
    - 连接状态查询和监控（不主动关闭）
    - 连接健康检查（不关闭连接）
    ...
    """
```

---

### 6. remove_stream 方法说明更新

**优化后：**
```python
async def remove_stream(self, symbol: str, interval: str) -> bool:
    """移除K线流（手动调用，用于停止监听某个symbol的某个interval）。
    
    注意：正常情况下，K线监听应该长期运行，不应该主动调用此方法。
    此方法主要用于：
    - 手动停止监听某个symbol的某个interval
    - 服务关闭时清理所有连接
    - 错误处理时清理无法使用的连接
    """
```

---

## 连接关闭的场景

虽然优化后连接会长期运行，但在以下情况下仍会关闭连接：

### 1. 服务关闭时
- 调用 `cleanup_all()` 方法时，会关闭所有连接
- 这是正常的服务关闭流程

### 2. 手动移除时
- 调用 `remove_stream()` 方法时，会关闭指定连接
- 用于手动停止监听某个symbol的某个interval

### 3. 错误处理时
- 当连接错误处理器检测到连接确实无法使用时，会关闭连接
- 例如：WebSocket连接断开、网络错误等

### 4. 连接已过期且需要重建时
- 在 `add_stream()` 方法中，如果发现连接已过期，会先关闭旧连接再创建新连接
- 但由于过期时间已设置为1年，这种情况基本不会发生

---

## 运行机制

### 连接生命周期

```
构建连接
  ↓
注册消息处理器
  ↓
保存到活跃连接字典
  ↓
持续接收K线消息（长期运行）
  ↓
处理消息并插入数据库
  ↓
（一直运行，直到服务关闭或出错）
```

### 定期检查任务

- **连接状态检查**：每小时检查一次连接状态，但不关闭连接
- **Ping任务**：每5分钟检查一次连接（当前已注释，SDK可能不支持）
- **状态更新**：定期更新agent状态到数据库

---

## 注意事项

1. **连接不会自动过期**：过期时间已设置为1年，实际上连接不会因为时间过期而关闭。

2. **只检查不关闭**：所有定期检查任务只检查连接状态，不主动关闭连接。

3. **长期运行**：K线监听是长期运行的异步任务，连接会一直保持活跃，持续接收消息。

4. **错误处理**：只有在连接确实无法使用时（通过错误处理器检测到），才会关闭连接。

5. **服务关闭**：只有在服务关闭时（调用 `cleanup_all()`），才会关闭所有连接。

---

## 相关文件

- `data/data_agent.py`: DataAgentKlineManager 类和相关方法
- `docs/DATA_AGENT_SYMBOLS_ADD_API_ANALYSIS.md`: API分析文档

---

## 总结

经过优化后，K线监听连接会：
- ✅ 构建完成后一直保持活跃
- ✅ 持续接收K线消息
- ✅ 不会因为时间过期而关闭
- ✅ 不会因为定期检查而关闭
- ✅ 只在服务关闭或出错时才关闭
- ✅ 作为长期运行的异步任务，持续同步K线数据到ClickHouse

