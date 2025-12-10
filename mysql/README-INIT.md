# MySQL 初始化说明

## 自动初始化流程

当首次执行 `docker-compose -f docker-compose-mysql.yml up -d` 时，MySQL 会自动完成以下初始化：

### 1. 数据库和用户创建
- 自动创建数据库：`aifuturetrade`
- 自动创建用户：`aifuturetrade`（密码：`aifuturetrade123`）
- 自动授予权限

### 2. 认证插件配置
- 自动执行 `mysql/init-database.sh` 脚本
- 将所有用户（root 和 aifuturetrade）的认证插件设置为 `mysql_native_password`
- 解决 MySQL 8.0 默认使用 `caching_sha2_password` 导致的连接问题

### 3. 高性能配置加载
- 自动加载 `mysql/my.cnf` 配置文件
- 应用所有性能优化设置

## 初始化脚本执行顺序

MySQL 官方镜像会按以下顺序执行初始化：

1. 创建 root 用户
2. 创建数据库（如果设置了 `MYSQL_DATABASE`）
3. 创建应用用户（如果设置了 `MYSQL_USER`）
4. **按字母顺序执行 `/docker-entrypoint-initdb.d/` 目录下的所有脚本**
   - `.sh` 脚本会以 bash 执行
   - `.sql` 脚本会以 mysql 客户端执行
   - `.sql.gz` 脚本会先解压再执行
   - **注意**：当前 `docker-compose-mysql.yml` 只挂载了 `init-database.sh`，未挂载 `init-auth-plugin.sql`
   - `init-database.sh` 已包含认证插件配置，无需额外挂载 SQL 文件

## 文件说明

### `mysql/init-database.sh`
- **用途**：主初始化脚本（推荐使用）
- **执行时机**：数据库和用户创建后
- **功能**：
  - 等待 MySQL 完全启动
  - 修改所有用户的认证插件
  - 验证配置

### `mysql/init-auth-plugin.sql`
- **用途**：SQL 版本的初始化脚本（备用/参考）
- **执行时机**：数据库和用户创建后（如果挂载）
- **功能**：修改用户认证插件
- **注意**：
  - 当前 `docker-compose-mysql.yml` **未挂载此文件**
  - `init-database.sh` 已包含所有认证插件配置逻辑
  - 此文件可作为参考或备用方案
  - 如需使用纯 SQL 方式，可手动挂载到 `/mysql/scripts/init-auth-plugin.sql` 并在 `docker-compose-mysql.yml` 中添加挂载配置

### `mysql/my.cnf`
- **用途**：MySQL 高性能配置文件
- **加载时机**：MySQL 启动时自动加载
- **位置**：`/etc/mysql/conf.d/my.cnf`

## 验证初始化结果

### 检查用户认证插件
```bash
docker exec -it aifuturetrade-mysql mysql -u root -paifuturetrade_root123 -e "SELECT user, host, plugin FROM mysql.user WHERE user IN ('root', 'aifuturetrade');"
```

预期输出：
```
+----------------+-----------+-----------------------+
| user           | host      | plugin                |
+----------------+-----------+-----------------------+
| aifuturetrade  | %         | mysql_native_password |
| aifuturetrade  | localhost | mysql_native_password |
| root           | %         | mysql_native_password |
| root           | localhost | mysql_native_password |
+----------------+-----------+-----------------------+
```

### 测试连接
```bash
# 测试应用用户连接
docker exec -it aifuturetrade-mysql mysql -u aifuturetrade -paifuturetrade123 -e "SELECT 1"

# 测试 root 用户连接
docker exec -it aifuturetrade-mysql mysql -u root -paifuturetrade_root123 -e "SELECT 1"
```

## 重新初始化

如果需要重新初始化（**会丢失所有数据**）：

```bash
# 1. 停止 MySQL 服务
docker-compose -f docker-compose-mysql.yml down

# 2. 删除数据卷
docker volume rm aifuturetrade_mysql_data

# 3. 重新启动（会自动执行初始化）
docker-compose -f docker-compose-mysql.yml up -d

# 4. 等待初始化完成（30-60秒）
# 查看日志确认初始化成功
docker-compose -f docker-compose-mysql.yml logs -f mysql
```

## 常见问题

### Q: 初始化脚本没有执行？
**A:** 检查数据卷是否已存在。如果数据卷已存在，MySQL 不会执行初始化脚本。

### Q: 如何确认初始化脚本已执行？
**A:** 查看 MySQL 日志：
```bash
docker-compose -f docker-compose-mysql.yml logs mysql | grep -i "init\|initialization\|database"
```

### Q: 用户认证插件仍然是 caching_sha2_password？
**A:** 可能是数据卷已存在，初始化脚本未执行。需要删除数据卷重新初始化，或手动执行修复脚本。

### Q: 初始化需要多长时间？
**A:** 通常需要 30-60 秒，取决于服务器性能。可以通过日志监控进度。

## 注意事项

1. **数据持久化**：数据存储在 `mysql_data` 卷中，删除容器不会丢失数据
2. **初始化脚本**：只在首次启动时执行，后续启动不会执行
3. **配置文件**：`my.cnf` 每次启动都会加载
4. **密码安全**：生产环境请修改默认密码

