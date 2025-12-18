# MySQL 性能调优指南

## 当前配置评估

### ✅ 已优化的配置
1. **InnoDB 缓冲池**: 2GB（可根据服务器内存调整）
2. **连接池**: 最大100个连接
3. **日志文件**: 512MB（适合高频写入）
4. **IO优化**: O_DIRECT 刷新方法
5. **慢查询日志**: 已启用，记录超过2秒的查询

### ⚠️ 需要根据实际情况调整的参数

## 1. 内存配置调整

### 查看服务器内存
```bash
# 查看服务器总内存
free -h

# 查看 Docker 容器内存限制
docker stats aifuturetrade-mysql
```

### 调整 innodb_buffer_pool_size

根据服务器内存大小，编辑 `mysql/my.cnf`：

**4GB 服务器**:
```ini
innodb_buffer_pool_size=2G
innodb_buffer_pool_instances=4
```

**8GB 服务器**:
```ini
innodb_buffer_pool_size=4G
innodb_buffer_pool_instances=8
```

**16GB 服务器**:
```ini
innodb_buffer_pool_size=8G
innodb_buffer_pool_instances=8
```

**32GB+ 服务器**:
```ini
innodb_buffer_pool_size=16G
innodb_buffer_pool_instances=8
```

## 2. 连接数调整

### 查看当前连接数使用情况
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

### 调整 max_connections

如果连接数使用率经常超过 70%，需要增加 `max_connections`：

```ini
max_connections=200  # 根据实际需求调整
```

## 3. 磁盘IO优化

### 如果使用 SSD
可以增加日志文件大小和IO线程数：

```ini
innodb_log_file_size=1G
innodb_read_io_threads=8
innodb_write_io_threads=8
```

### 如果使用传统HDD
保持当前配置或适当降低：

```ini
innodb_log_file_size=256M
innodb_read_io_threads=4
innodb_write_io_threads=4
```

## 4. 查询优化

### 启用查询缓存（MySQL 5.7及以下）
MySQL 8.0 已移除查询缓存，但可以通过以下方式优化：

1. **添加合适的索引**
```sql
-- 查看表索引
SHOW INDEX FROM table_name;

-- 分析查询执行计划
EXPLAIN SELECT * FROM table_name WHERE condition;
```

2. **优化慢查询**
```bash
# 查看慢查询日志
docker exec -it aifuturetrade-mysql tail -f /var/log/mysql/slow-query.log

# 使用 mysqldumpslow 分析
docker exec -it aifuturetrade-mysql mysqldumpslow -s t /var/log/mysql/slow-query.log
```

## 5. 监控关键指标

### 缓冲池命中率
```sql
-- 查看缓冲池统计信息
SHOW STATUS LIKE 'Innodb_buffer_pool%';

-- 计算命中率（应该 > 99%）
SELECT 
    (1 - (Innodb_buffer_pool_reads / Innodb_buffer_pool_read_requests)) * 100 as hit_rate
FROM (
    SELECT 
        VARIABLE_VALUE as Innodb_buffer_pool_reads
    FROM information_schema.GLOBAL_STATUS 
    WHERE VARIABLE_NAME = 'Innodb_buffer_pool_reads'
) reads,
(
    SELECT 
        VARIABLE_VALUE as Innodb_buffer_pool_read_requests
    FROM information_schema.GLOBAL_STATUS 
    WHERE VARIABLE_NAME = 'Innodb_buffer_pool_read_requests'
) requests;
```

### 锁等待情况
```sql
-- 查看锁等待
SHOW STATUS LIKE 'Innodb_row_lock%';

-- 如果 Innodb_row_lock_waits 较高，需要优化事务或索引
```

### 表缓存使用情况
```sql
-- 查看表缓存
SHOW STATUS LIKE 'Table_open_cache%';

-- 如果 Table_open_cache_misses 较高，需要增加 table_open_cache
```

## 6. 应用层优化建议

### 连接池配置
根据 `common/database_basic.py` 中的配置：
- 当前最大连接数：50
- 建议：根据并发请求量调整，但不要超过 MySQL 的 `max_connections`

### 批量插入优化
对于高频数据写入（如市场数据），建议：
1. 使用批量插入（INSERT ... VALUES (...), (...), (...)）
2. 批量大小：100-1000 条记录
3. 使用事务批量提交

### 索引优化
1. 为常用查询字段添加索引
2. 避免过多索引（影响写入性能）
3. 定期分析表：`ANALYZE TABLE table_name`

## 7. 定期维护

### 优化表
```sql
-- 优化表（重建索引和碎片整理）
OPTIMIZE TABLE table_name;
```

### 分析表
```sql
-- 更新表统计信息
ANALYZE TABLE table_name;
```

### 清理日志
```bash
# 清理慢查询日志（保留最近7天）
docker exec -it aifuturetrade-mysql find /var/log/mysql -name "slow-query.log" -mtime +7 -delete

# 清理二进制日志（MySQL会自动清理，但可以手动清理）
docker exec -it aifuturetrade-mysql mysql -u root -p -e "PURGE BINARY LOGS BEFORE DATE_SUB(NOW(), INTERVAL 7 DAY);"
```

## 8. 性能测试

### 使用 sysbench 进行压力测试
```bash
# 安装 sysbench（在主机上）
# Ubuntu/Debian: apt-get install sysbench
# CentOS/RHEL: yum install sysbench

# 准备测试数据
sysbench mysql \
  --mysql-host=localhost \
  --mysql-port=3306 \
  --mysql-user=aifuturetrade \
  --mysql-password=aifuturetrade123 \
  --mysql-db=aifuturetrade \
  --tables=10 \
  --table-size=10000 \
  prepare

# 运行测试
sysbench mysql \
  --mysql-host=localhost \
  --mysql-port=3306 \
  --mysql-user=aifuturetrade \
  --mysql-password=aifuturetrade123 \
  --mysql-db=aifuturetrade \
  --tables=10 \
  --threads=10 \
  --time=60 \
  run

# 清理测试数据
sysbench mysql \
  --mysql-host=localhost \
  --mysql-port=3306 \
  --mysql-user=aifuturetrade \
  --mysql-password=aifuturetrade123 \
  --mysql-db=aifuturetrade \
  --tables=10 \
  cleanup
```

## 9. 故障排查

### MySQL 启动失败
1. 检查配置文件语法
2. 查看错误日志：`docker logs aifuturetrade-mysql`
3. 检查磁盘空间：`df -h`
4. 检查内存是否足够

### 性能突然下降
1. 检查慢查询日志
2. 检查连接数使用情况
3. 检查是否有锁等待
4. 检查磁盘IO使用情况：`iostat -x 1`

### 内存不足
1. 检查缓冲池使用情况
2. 检查临时表使用情况
3. 适当降低 `innodb_buffer_pool_size`
4. 增加服务器内存

## 10. 推荐配置（根据服务器规模）

### 小型服务器（4GB内存，2核CPU）
```ini
innodb_buffer_pool_size=2G
max_connections=100
innodb_log_file_size=256M
```

### 中型服务器（8GB内存，4核CPU）
```ini
innodb_buffer_pool_size=4G
max_connections=200
innodb_log_file_size=512M
```

### 大型服务器（16GB+内存，8核+CPU）
```ini
innodb_buffer_pool_size=8G
max_connections=300
innodb_log_file_size=1G
innodb_read_io_threads=8
innodb_write_io_threads=8
```

## 总结

当前 MySQL 配置已经针对高频交易数据存储进行了优化，主要包括：
- ✅ InnoDB 缓冲池优化
- ✅ 连接和线程优化
- ✅ IO 性能优化
- ✅ 慢查询监控

**下一步操作**：
1. 根据服务器实际内存调整 `innodb_buffer_pool_size`
2. 监控慢查询日志，优化慢查询
3. 定期检查缓冲池命中率和连接数使用情况
4. 根据实际负载情况调整相关参数

