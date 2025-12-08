# ClickHouse 超时配置说明

## 问题描述

遇到 ClickHouse 连接读取超时错误：
```
ReadTimeoutError: HTTPConnectionPool(host='193.134.209.95', port=32123): Read timed out.
```

## 超时配置

### 1. 配置项说明

在 `common/config.py` 中新增了以下配置项：

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| `CLICKHOUSE_CONNECT_TIMEOUT` | `CLICKHOUSE_CONNECT_TIMEOUT` | 30秒 | 连接超时时间 |
| `CLICKHOUSE_SEND_RECEIVE_TIMEOUT` | `CLICKHOUSE_SEND_RECEIVE_TIMEOUT` | 120秒 | 发送/接收超时时间（读取数据） |
| `CLICKHOUSE_MAX_EXECUTION_TIME` | `CLICKHOUSE_MAX_EXECUTION_TIME` | 120秒 | 查询执行超时时间 |

### 2. 超时设置说明

#### 2.1 连接超时（connect_timeout）
- **默认值**: 30秒
- **作用**: 建立连接时的超时时间
- **适用场景**: 网络延迟较高或服务器响应慢时

#### 2.2 发送/接收超时（send_receive_timeout）
- **默认值**: 120秒（2分钟）
- **作用**: 发送请求和接收响应时的超时时间
- **适用场景**: 
  - 大数据量查询（如批量插入、复杂查询）
  - 网络不稳定时
  - 服务器处理时间较长时
- **⚠️ 重要**: 这是解决读取超时问题的关键配置

#### 2.3 查询执行超时（max_execution_time）
- **默认值**: 120秒（2分钟）
- **作用**: ClickHouse 服务器端查询执行的最大时间
- **适用场景**: 复杂查询或大数据量处理

### 3. 修改内容

#### 3.1 配置文件（common/config.py）
```python
# ClickHouse连接超时配置（秒）
CLICKHOUSE_CONNECT_TIMEOUT = int(os.getenv('CLICKHOUSE_CONNECT_TIMEOUT', '30'))  # 连接超时，默认30秒
CLICKHOUSE_SEND_RECEIVE_TIMEOUT = int(os.getenv('CLICKHOUSE_SEND_RECEIVE_TIMEOUT', '120'))  # 发送/接收超时，默认120秒（2分钟）
CLICKHOUSE_MAX_EXECUTION_TIME = int(os.getenv('CLICKHOUSE_MAX_EXECUTION_TIME', '120'))  # 查询执行超时，默认120秒（2分钟）
```

#### 3.2 连接池实现（common/database_clickhouse.py）
```python
# 使用配置中的超时设置，支持通过环境变量调整
connect_timeout = getattr(app_config, 'CLICKHOUSE_CONNECT_TIMEOUT', 30)
send_receive_timeout = getattr(app_config, 'CLICKHOUSE_SEND_RECEIVE_TIMEOUT', 120)
max_execution_time = getattr(app_config, 'CLICKHOUSE_MAX_EXECUTION_TIME', 120)

client = clickhouse_connect.get_client(
    ...
    connect_timeout=connect_timeout,  # 连接超时，默认30秒
    send_receive_timeout=send_receive_timeout,  # 发送/接收超时，默认120秒（2分钟）
    settings={'max_execution_time': max_execution_time}  # 查询执行超时，默认120秒（2分钟）
)
```

### 4. 使用方法

#### 4.1 使用默认值
无需任何配置，系统会自动使用默认值：
- 连接超时：30秒
- 发送/接收超时：120秒
- 查询执行超时：120秒

#### 4.2 通过环境变量调整
在启动应用前设置环境变量：

```bash
# Linux/Mac
export CLICKHOUSE_CONNECT_TIMEOUT=30
export CLICKHOUSE_SEND_RECEIVE_TIMEOUT=180  # 增加到3分钟
export CLICKHOUSE_MAX_EXECUTION_TIME=180

# Windows PowerShell
$env:CLICKHOUSE_CONNECT_TIMEOUT="30"
$env:CLICKHOUSE_SEND_RECEIVE_TIMEOUT="180"
$env:CLICKHOUSE_MAX_EXECUTION_TIME="180"
```

#### 4.3 Docker Compose 配置
在 `docker-compose.yml` 中添加环境变量：

```yaml
services:
  backend:
    environment:
      - CLICKHOUSE_CONNECT_TIMEOUT=30
      - CLICKHOUSE_SEND_RECEIVE_TIMEOUT=180
      - CLICKHOUSE_MAX_EXECUTION_TIME=180
```

### 5. 超时时间建议

#### 5.1 根据查询类型调整

| 查询类型 | 建议超时时间 | 说明 |
|---------|-------------|------|
| 简单查询 | 30-60秒 | 单表查询、小数据量 |
| 复杂查询 | 120-300秒 | JOIN查询、聚合查询 |
| 批量插入 | 180-600秒 | 大量数据插入 |
| 数据清理 | 300-600秒 | DELETE操作、大数据量操作 |

#### 5.2 根据网络环境调整

| 网络环境 | 建议超时时间 | 说明 |
|---------|-------------|------|
| 本地网络 | 30-60秒 | 低延迟、高带宽 |
| 内网 | 60-120秒 | 中等延迟 |
| 公网 | 120-300秒 | 高延迟、不稳定 |
| 跨地域 | 300-600秒 | 高延迟、可能不稳定 |

### 6. 故障排查

#### 6.1 如果仍然超时

1. **检查网络连接**：
   ```bash
   ping 193.134.209.95
   telnet 193.134.209.95 32123
   ```

2. **检查ClickHouse服务器状态**：
   - 服务器是否正常运行
   - 服务器负载是否过高
   - 是否有慢查询占用资源

3. **增加超时时间**：
   ```bash
   export CLICKHOUSE_SEND_RECEIVE_TIMEOUT=300  # 增加到5分钟
   export CLICKHOUSE_MAX_EXECUTION_TIME=300
   ```

4. **检查查询性能**：
   - 优化查询语句
   - 添加索引
   - 减少查询数据量

#### 6.2 监控超时情况

查看日志中的超时错误：
```bash
grep -i "timeout" logs/app.log
grep -i "Read timed out" logs/app.log
```

### 7. 相关文件

- `common/config.py`: 超时配置定义
- `common/database_clickhouse.py`: 连接池实现，使用超时配置
- `common/database_basic.py`: 使用连接池，继承超时配置

### 8. 注意事项

1. **超时时间不宜过长**：
   - 过长的超时时间可能导致请求长时间挂起
   - 建议根据实际需求设置合理的超时时间

2. **健康检查超时**：
   - 健康检查使用较短的超时时间（最多5秒）
   - 避免健康检查影响正常查询

3. **重试机制**：
   - 代码中已实现自动重试机制（最多3次）
   - 超时错误会自动重试

4. **连接池**：
   - 使用连接池可以复用连接，减少连接建立时间
   - 连接池大小可根据实际需求调整

