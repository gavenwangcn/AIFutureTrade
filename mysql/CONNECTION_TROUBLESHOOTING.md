# MySQL 连接数过多问题排查和解决方案

## 问题症状

```
java.sql.SQLNonTransientConnectionException: Too many connections
errorCode 1040, state 08004
```

## 原因分析

1. **应用连接池配置过大**：Druid 连接池的 `max-active` 设置过高
2. **连接泄漏**：应用没有正确关闭数据库连接
3. **MySQL 最大连接数限制**：MySQL 的 `max_connections` 设置过低
4. **多个应用实例**：多个应用实例共享同一个数据库，连接数累加

## 快速诊断

### 1. 查看当前连接数

```sql
-- 查看当前连接数
SHOW STATUS LIKE 'Threads_connected';

-- 查看最大连接数
SHOW VARIABLES LIKE 'max_connections';

-- 查看连接数使用率
SELECT 
    VARIABLE_VALUE as current_connections,
    (SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES WHERE VARIABLE_NAME = 'max_connections') as max_connections,
    ROUND(VARIABLE_VALUE / (SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES WHERE VARIABLE_NAME = 'max_connections') * 100, 2) as usage_percent
FROM information_schema.GLOBAL_STATUS 
WHERE VARIABLE_NAME = 'Threads_connected';
```

### 2. 查看连接详情

```sql
-- 查看所有连接的详细信息
SHOW PROCESSLIST;

-- 查看按用户分组的连接数
SELECT user, COUNT(*) as connection_count 
FROM information_schema.PROCESSLIST 
GROUP BY user;

-- 查看长时间运行的连接
SELECT 
    id, 
    user, 
    host, 
    db, 
    command, 
    time, 
    state, 
    LEFT(info, 100) as query
FROM information_schema.PROCESSLIST 
WHERE time > 60  -- 运行时间超过60秒
ORDER BY time DESC;
```

### 3. 查看连接池状态（Druid）

访问 Druid 监控页面（如果已配置）：
- URL: `http://your-server:port/druid/index.html`
- 查看 "数据源" -> "连接池" 部分

## 解决方案

### 方案1：优化应用连接池配置（推荐）

已优化 `application-prod.yml` 配置：

```yaml
druid:
  initial-size: 5          # 降低初始连接数
  min-idle: 5              # 降低最小空闲连接数
  max-active: 20           # 降低最大连接数（从50降到20）
  max-wait: 10000          # 降低等待时间，快速失败
  remove-abandoned: true   # 启用连接泄漏检测
  remove-abandoned-timeout-millis: 300000  # 5分钟未使用自动回收
  log-abandoned: true      # 记录泄漏连接堆栈
```

**修改后需要重启应用**。

### 方案2：增加 MySQL 最大连接数

如果确实需要更多连接，可以增加 MySQL 的 `max_connections`：

#### 临时修改（立即生效，重启后失效）

```sql
SET GLOBAL max_connections = 200;
```

#### 永久修改（需要重启 MySQL）

编辑 `mysql/my.cnf`：

```ini
[mysqld]
max_connections = 200  # 根据实际需求调整
```

然后重启 MySQL：

```bash
docker restart aifuturetrade-mysql
```

**注意**：增加 `max_connections` 会增加 MySQL 的内存使用，每个连接大约占用 256KB-1MB 内存。

### 方案3：检查并修复连接泄漏

#### 检查连接泄漏

1. **查看 Druid 监控**：访问 `/druid/index.html`，查看 "连接泄漏检测" 部分
2. **查看应用日志**：查找包含 "abandoned connection" 的日志
3. **代码审查**：确保所有数据库操作都正确关闭连接

#### 修复连接泄漏

确保使用 try-with-resources 或 finally 块关闭连接：

```java
// ✅ 正确：使用 try-with-resources
try (Connection conn = dataSource.getConnection();
     PreparedStatement stmt = conn.prepareStatement(sql)) {
    // 执行操作
}

// ✅ 正确：使用 finally 块
Connection conn = null;
try {
    conn = dataSource.getConnection();
    // 执行操作
} finally {
    if (conn != null) {
        conn.close();
    }
}

// ❌ 错误：忘记关闭连接
Connection conn = dataSource.getConnection();
// 执行操作
// 没有关闭连接！
```

### 方案4：检查是否有多个应用实例

如果部署了多个应用实例，每个实例的连接数会累加：

```bash
# 查看连接到数据库的客户端IP
mysql -u root -p -e "
SELECT 
    SUBSTRING_INDEX(host, ':', 1) as client_ip,
    COUNT(*) as connection_count
FROM information_schema.PROCESSLIST
WHERE user != 'system user'
GROUP BY client_ip;
"
```

如果发现多个应用实例，需要：
1. 降低每个实例的连接池大小
2. 或者增加 MySQL 的 `max_connections`

## 预防措施

### 1. 监控连接数使用情况

创建监控脚本 `scripts/monitor-connections.sh`：

```bash
#!/bin/bash
mysql -u root -p -e "
SELECT 
    VARIABLE_VALUE as current_connections,
    (SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES WHERE VARIABLE_NAME = 'max_connections') as max_connections,
    ROUND(VARIABLE_VALUE / (SELECT VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES WHERE VARIABLE_NAME = 'max_connections') * 100, 2) as usage_percent
FROM information_schema.GLOBAL_STATUS 
WHERE VARIABLE_NAME = 'Threads_connected';
"
```

### 2. 设置告警

当连接数使用率超过 80% 时发送告警。

### 3. 定期检查连接泄漏

定期查看 Druid 监控页面，检查是否有连接泄漏。

### 4. 代码规范

- 所有数据库操作必须使用 try-with-resources
- 禁止在类成员变量中持有 Connection
- 使用连接池，不要直接创建连接

## 紧急处理

如果连接数已经达到上限，无法创建新连接：

### 1. 临时增加最大连接数

```sql
SET GLOBAL max_connections = 500;
```

### 2. 杀死长时间空闲的连接

```sql
-- 查看空闲连接
SELECT id, user, host, db, command, time, state 
FROM information_schema.PROCESSLIST 
WHERE command = 'Sleep' AND time > 300  -- 空闲超过5分钟
ORDER BY time DESC;

-- 杀死指定连接（谨慎操作）
KILL <connection_id>;
```

### 3. 重启应用

如果连接泄漏严重，重启应用可以释放所有连接：

```bash
docker restart aifuturetrade-backend
```

## 配置建议

### 小型应用（单实例）

```yaml
druid:
  initial-size: 3
  min-idle: 3
  max-active: 10
```

### 中型应用（单实例）

```yaml
druid:
  initial-size: 5
  min-idle: 5
  max-active: 20
```

### 大型应用（多实例）

每个实例：
```yaml
druid:
  initial-size: 5
  min-idle: 5
  max-active: 15  # 3个实例总共45个连接
```

MySQL 配置：
```ini
max_connections = 200  # 为3个实例预留足够空间
```

## 总结

1. ✅ **已优化连接池配置**：降低 `max-active` 从 50 到 20
2. ✅ **启用连接泄漏检测**：5分钟未使用的连接自动回收
3. ✅ **降低连接等待时间**：快速失败，避免连接堆积
4. ⚠️ **需要重启应用**：使新配置生效
5. ⚠️ **监控连接数**：定期检查连接数使用情况

**下一步操作**：
1. 重启应用使新配置生效
2. 监控连接数使用情况
3. 如果问题持续，检查是否有连接泄漏
4. 根据实际情况调整 MySQL 的 `max_connections`
