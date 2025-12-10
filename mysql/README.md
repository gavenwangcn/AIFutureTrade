# MySQL 高性能配置说明

## 配置文件说明

`my.cnf` 文件包含了针对高频交易数据存储场景的 MySQL 性能优化配置。

## 性能优化要点

### 1. 内存配置
- **innodb_buffer_pool_size**: InnoDB 缓冲池大小，建议设置为服务器内存的 50-70%
- **innodb_buffer_pool_instances**: 缓冲池实例数，提高并发性能

### 2. InnoDB 优化
- **innodb_log_file_size**: 日志文件大小，影响写入性能
- **innodb_flush_log_at_trx_commit**: 刷新策略，平衡性能和数据安全
- **innodb_flush_method**: 使用 O_DIRECT 提高 IO 性能

### 3. 连接优化
- **max_connections**: 最大连接数，根据应用需求设置
- **thread_cache_size**: 线程缓存，减少线程创建开销

### 4. 查询优化
- **慢查询日志**: 记录执行时间超过 2 秒的查询
- **表缓存**: 提高表访问性能

## 根据服务器配置调整

### 4GB 内存服务器
```ini
innodb_buffer_pool_size=2G
innodb_buffer_pool_instances=4
```

### 8GB 内存服务器
```ini
innodb_buffer_pool_size=4G
innodb_buffer_pool_instances=8
```

### 16GB 内存服务器
```ini
innodb_buffer_pool_size=8G
innodb_buffer_pool_instances=8
```

## 监控和调优

### 查看 MySQL 状态
```bash
# 进入 MySQL 容器
docker exec -it aifuturetrade-mysql mysql -u root -p

# 查看 InnoDB 状态
SHOW ENGINE INNODB STATUS\G

# 查看连接数
SHOW STATUS LIKE 'Threads_connected';
SHOW VARIABLES LIKE 'max_connections';

# 查看缓冲池使用情况
SHOW STATUS LIKE 'Innodb_buffer_pool%';
```

### 查看慢查询日志
```bash
# 查看慢查询日志
docker exec -it aifuturetrade-mysql tail -f /var/log/mysql/slow-query.log

# 或使用 mysqldumpslow 分析
docker exec -it aifuturetrade-mysql mysqldumpslow /var/log/mysql/slow-query.log
```

### 性能监控指标

1. **连接数使用率**
   - 监控 `Threads_connected / max_connections`
   - 建议保持在 70% 以下

2. **缓冲池命中率**
   - 监控 `Innodb_buffer_pool_read_requests / (Innodb_buffer_pool_read_requests + Innodb_buffer_pool_reads)`
   - 建议保持在 99% 以上

3. **慢查询数量**
   - 定期检查慢查询日志
   - 优化执行时间超过 2 秒的查询

4. **锁等待时间**
   - 监控 `Innodb_row_lock_waits`
   - 如果频繁出现锁等待，考虑优化事务或索引

## 注意事项

1. **内存配置**: 根据服务器实际内存调整 `innodb_buffer_pool_size`，不要超过服务器可用内存的 70%
2. **磁盘IO**: 如果使用 SSD，可以适当增加 `innodb_log_file_size`
3. **连接数**: 根据应用实际连接数设置 `max_connections`，避免设置过大导致资源浪费
4. **日志文件**: 定期清理慢查询日志和二进制日志，避免占用过多磁盘空间

## 故障排查

### 如果 MySQL 启动失败
1. 检查配置文件语法：`docker exec -it aifuturetrade-mysql mysql --help | grep my.cnf`
2. 查看错误日志：`docker logs aifuturetrade-mysql`
3. 检查磁盘空间：`df -h`

### 如果性能下降
1. 检查慢查询日志
2. 检查连接数使用情况
3. 检查缓冲池命中率
4. 检查磁盘 IO 使用情况

