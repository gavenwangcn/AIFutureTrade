# MySQL 连接问题排查指南

## 问题：无法通过 localhost 或 127.0.0.1 连接

### 常见错误
```
[MySQL] Failed to create connection: (2003, "Can't connect to MySQL server on 'localhost' ([Errno 111] Connection refused)")
```

## 解决方案

### 1. 检查 MySQL 服务状态

```bash
# 检查容器是否运行
docker ps | grep mysql

# 检查容器日志
docker-compose -f docker-compose-mysql.yml logs -f mysql

# 检查端口是否监听
netstat -tlnp | grep 32123
# 或
ss -tlnp | grep 32123
```

### 2. 验证 MySQL 配置

确保以下配置正确：

#### docker-compose-mysql.yml
- 端口映射：`"0.0.0.0:32123:3306"`
- command 参数：`--bind-address=0.0.0.0`

#### mysql/my.cnf
- `bind-address=0.0.0.0`（在 [mysqld] 部分）

### 3. 测试连接

#### 从容器内部测试
```bash
# 进入容器
docker exec -it aifuturetrade-mysql bash

# 测试 localhost 连接
mysql -h localhost -u aifuturetrade -paifuturetrade123 -e "SELECT 1"

# 测试 127.0.0.1 连接
mysql -h 127.0.0.1 -u aifuturetrade -paifuturetrade123 -e "SELECT 1"
```

#### 从主机测试
```bash
# 测试 localhost 连接
mysql -h localhost -P 32123 -u aifuturetrade -paifuturetrade123 -e "SELECT 1"

# 测试 127.0.0.1 连接
mysql -h 127.0.0.1 -P 32123 -u aifuturetrade -paifuturetrade123 -e "SELECT 1"
```

### 4. 检查用户权限

```bash
# 进入 MySQL 容器
docker exec -it aifuturetrade-mysql mysql -u root -paifuturetrade_root123

# 查看用户列表
SELECT user, host, plugin FROM mysql.user WHERE user IN ('root', 'aifuturetrade');

# 应该看到以下用户：
# - root@%
# - root@localhost
# - aifuturetrade@%
# - aifuturetrade@localhost
# - aifuturetrade@127.0.0.1（如果已创建）
```

### 5. 重新初始化（如果需要）

如果配置有问题，可以重新初始化：

```bash
# 停止并删除容器和数据卷
docker-compose -f docker-compose-mysql.yml down -v

# 重新启动
docker-compose -f docker-compose-mysql.yml up -d

# 查看初始化日志
docker-compose -f docker-compose-mysql.yml logs -f mysql
```

### 6. 检查防火墙

确保防火墙允许 32123 端口：

```bash
# 检查防火墙状态（Ubuntu/Debian）
sudo ufw status

# 如果防火墙开启，允许端口
sudo ufw allow 32123/tcp

# 检查防火墙状态（CentOS/RHEL）
sudo firewall-cmd --list-ports

# 如果防火墙开启，允许端口
sudo firewall-cmd --add-port=32123/tcp --permanent
sudo firewall-cmd --reload
```

### 7. 检查网络配置

如果使用 Docker 网络，确保服务在同一网络中：

```bash
# 查看网络配置
docker network inspect aifuturetrade-network

# 确保 MySQL 容器在正确的网络中
docker inspect aifuturetrade-mysql | grep NetworkMode
```

## 连接方式说明

### 从主机连接（推荐）
- **localhost:32123** - 使用 localhost
- **127.0.0.1:32123** - 使用 IP 地址

### 从 Docker 容器连接
- **mysql:3306** - 使用 Docker 服务名（在同一网络中）
- **localhost:3306** - 从容器内部连接
- **127.0.0.1:3306** - 从容器内部连接

### 从外部网络连接
- **<服务器IP>:32123** - 使用服务器公网IP

## 配置验证清单

- [ ] MySQL 容器正在运行
- [ ] 端口 32123 正在监听
- [ ] my.cnf 中设置了 `bind-address=0.0.0.0`
- [ ] docker-compose-mysql.yml 中设置了 `--bind-address=0.0.0.0`
- [ ] 用户权限正确（支持 %、localhost、127.0.0.1）
- [ ] 防火墙允许 32123 端口
- [ ] 可以从容器内部连接
- [ ] 可以从主机连接

## 常见问题

### Q: 为什么设置了 bind-address=0.0.0.0 还是无法连接？
A: 检查以下几点：
1. 确保 my.cnf 文件正确挂载到容器
2. 确保容器重启后配置生效
3. 检查是否有其他配置覆盖了 bind-address

### Q: 为什么从容器内部可以连接，但从主机无法连接？
A: 可能是端口映射问题：
1. 检查 docker-compose-mysql.yml 中的端口映射
2. 确保使用 `0.0.0.0:32123:3306` 而不是 `127.0.0.1:32123:3306`

### Q: 为什么需要创建多个用户（%、localhost、127.0.0.1）？
A: MySQL 将不同来源的连接视为不同的用户：
- `%` - 匹配任何主机
- `localhost` - 匹配 localhost 主机名
- `127.0.0.1` - 匹配 IP 地址

为了确保从所有方式都能连接，需要为每种方式创建用户。

