# MySQL 连接问题排查指南

## 问题1: ECONNREFUSED (连接被拒绝)

### 症状
```
ERROR - [MySQL] Failed to create connection: (2003, "Can't connect to MySQL server on 'mysql' ([Errno 111] ECONNREFUSED)")
```

### 可能原因和解决方案

#### 1. MySQL 服务未启动
```bash
# 检查 MySQL 容器是否运行
docker ps | grep mysql

# 如果未运行，启动 MySQL 服务
docker-compose -f docker-compose-mysql.yml up -d

# 查看 MySQL 日志
docker-compose -f docker-compose-mysql.yml logs -f mysql
```

#### 2. 网络配置问题
```bash
# 检查网络是否存在
docker network ls | grep aifuturetrade-network

# 如果不存在，创建网络
docker network create aifuturetrade-network

# 或者重新启动所有服务
docker-compose -f docker-compose-mysql.yml up -d
docker-compose up -d
```

#### 3. 端口冲突
```bash
# 检查 3306 端口是否被占用
netstat -tuln | grep 3306
# 或
lsof -i :3306

# 如果被占用，停止占用端口的服务或修改 docker-compose-mysql.yml 中的端口映射
```

#### 4. MySQL 启动失败
```bash
# 查看 MySQL 容器日志
docker logs aifuturetrade-mysql

# 检查常见问题：
# - 配置文件语法错误
# - 磁盘空间不足
# - 内存不足
# - 数据目录权限问题
```

## 问题2: cryptography 包缺失

### 症状
```
ERROR - [MySQL] Failed to create connection: 'cryptography' package is required for sha256_password or caching_sha2_password auth methods
```

### 解决方案

#### 方案1: 安装 cryptography 包（推荐）
```bash
# 安装 cryptography 包
pip install cryptography>=41.0.0

# 或重新安装所有依赖
pip install -r requirements.txt
```

#### 方案2: 修改 MySQL 用户认证插件
如果已经安装了 cryptography 包但仍然有问题，可能需要修改 MySQL 用户的认证插件：

```bash
# 进入 MySQL 容器
docker exec -it aifuturetrade-mysql mysql -u root -p

# 执行以下 SQL 命令
ALTER USER 'aifuturetrade'@'%' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';
ALTER USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade_root123';
FLUSH PRIVILEGES;
```

#### 方案3: 重新创建 MySQL 容器（如果数据可以丢失）
```bash
# 停止并删除 MySQL 容器和数据卷
docker-compose -f docker-compose-mysql.yml down -v

# 重新启动（会自动执行初始化脚本）
docker-compose -f docker-compose-mysql.yml up -d
```

## 问题3: 连接超时

### 症状
```
ERROR - [MySQL] Failed to acquire connection within timeout 30 seconds
```

### 解决方案

#### 1. 检查 MySQL 是否正在启动
MySQL 首次启动需要时间初始化，等待 30-60 秒后再重试。

#### 2. 检查健康检查状态
```bash
# 查看容器健康状态
docker inspect aifuturetrade-mysql | grep -A 10 Health

# 等待健康检查通过
docker-compose -f docker-compose-mysql.yml ps
```

#### 3. 增加连接超时时间
在 `common/config.py` 中增加 `MYSQL_CONNECT_TIMEOUT`：
```python
MYSQL_CONNECT_TIMEOUT = int(os.getenv('MYSQL_CONNECT_TIMEOUT', '60'))  # 增加到60秒
```

## 问题4: 认证失败

### 症状
```
ERROR - Access denied for user 'aifuturetrade'@'xxx'
```

### 解决方案

#### 1. 检查用户名和密码
确认 `common/config.py` 中的配置与 `docker-compose-mysql.yml` 中的环境变量一致。

#### 2. 检查用户权限
```bash
# 进入 MySQL 容器
docker exec -it aifuturetrade-mysql mysql -u root -p

# 检查用户是否存在
SELECT user, host FROM mysql.user WHERE user='aifuturetrade';

# 如果不存在，创建用户
CREATE USER 'aifuturetrade'@'%' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';
GRANT ALL PRIVILEGES ON aifuturetrade.* TO 'aifuturetrade'@'%';
FLUSH PRIVILEGES;
```

## 快速诊断命令

### 检查 MySQL 服务状态
```bash
# 1. 检查容器状态
docker ps -a | grep mysql

# 2. 检查日志
docker logs aifuturetrade-mysql --tail 50

# 3. 检查网络
docker network inspect aifuturetrade-network

# 4. 测试连接
docker exec -it aifuturetrade-mysql mysql -u aifuturetrade -paifuturetrade123 -e "SELECT 1"
```

### 检查应用连接配置
```bash
# 在应用容器中测试连接
docker exec -it aifuturetrade-backend python -c "
import pymysql
conn = pymysql.connect(
    host='mysql',
    port=3306,
    user='aifuturetrade',
    password='aifuturetrade123',
    database='aifuturetrade'
)
print('Connection successful!')
conn.close()
"
```

## 常见修复步骤

### 完整重置（数据会丢失）
```bash
# 1. 停止所有服务
docker-compose down
docker-compose -f docker-compose-mysql.yml down

# 2. 删除数据卷
docker volume rm aifuturetrade_mysql_data

# 3. 重新启动 MySQL
docker-compose -f docker-compose-mysql.yml up -d

# 4. 等待 MySQL 启动完成（30-60秒）
sleep 60

# 5. 启动其他服务
docker-compose up -d
```

### 保留数据的修复
```bash
# 1. 停止 MySQL
docker-compose -f docker-compose-mysql.yml stop mysql

# 2. 备份数据（可选）
docker run --rm -v aifuturetrade_mysql_data:/data -v $(pwd):/backup alpine tar czf /backup/mysql-backup.tar.gz /data

# 3. 进入 MySQL 容器修改认证插件
docker-compose -f docker-compose-mysql.yml run --rm mysql mysql -u root -paifuturetrade_root123 -e "
ALTER USER 'aifuturetrade'@'%' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade123';
ALTER USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY 'aifuturetrade_root123';
FLUSH PRIVILEGES;
"

# 4. 重新启动 MySQL
docker-compose -f docker-compose-mysql.yml up -d
```

## 预防措施

1. **确保 requirements.txt 包含 cryptography**
   ```txt
   cryptography>=41.0.0
   ```

2. **使用 mysql_native_password 认证插件**
   - 在 `docker-compose-mysql.yml` 中设置 `--default-authentication-plugin=mysql_native_password`
   - 在 `mysql/my.cnf` 中设置 `default-authentication-plugin=mysql_native_password`

3. **确保网络配置正确**
   - 所有服务使用相同的网络名称
   - MySQL 服务先启动

4. **监控 MySQL 健康状态**
   ```bash
   # 定期检查
   docker-compose -f docker-compose-mysql.yml ps
   ```

