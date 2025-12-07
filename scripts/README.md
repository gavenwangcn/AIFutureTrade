# Data Agent K线监听连接检查脚本

本目录包含用于检查 Data Agent K线监听连接的实用脚本。

## 脚本列表

### 1. `check_kline_connections.sh` - 完整检查脚本（推荐）

**功能：**
- 检查 data_agent 进程
- 统计连接数量和状态
- 显示连接详细信息
- 显示连接状态分布
- 网络连通性检查

**使用方法：**
```bash
chmod +x scripts/check_kline_connections.sh
./scripts/check_kline_connections.sh
```

**输出示例：**
```
==========================================
  Data Agent K线监听连接检查工具
==========================================
时间: 2025-12-07 21:30:00

==========================================
1. 检查 Data Agent 进程
==========================================
✅ 找到 data_agent 进程: PID=12345
...

==========================================
2. 检查 TCP 连接统计
==========================================
📊 连接统计:
  - 总TCP连接数: 14
  - 到 Binance 的连接数: 14
  - 已建立连接数 (ESTABLISHED): 14
  - 估计symbol数: 2 (每个symbol有7个interval)
...
```

---

### 2. `monitor_kline_connections.sh` - 实时监控脚本

**功能：**
- 实时显示连接数量和状态
- 自动刷新（默认2秒）
- 监控连接变化

**使用方法：**
```bash
chmod +x scripts/monitor_kline_connections.sh

# 使用默认刷新间隔（2秒）
./scripts/monitor_kline_connections.sh

# 指定刷新间隔（5秒）
./scripts/monitor_kline_connections.sh 5
```

**退出：** 按 `Ctrl+C` 退出监控

---

### 3. `count_kline_connections.sh` - 快速统计脚本

**功能：**
- 快速统计连接数量
- 计算symbol数量
- 显示简要信息

**使用方法：**
```bash
chmod +x scripts/count_kline_connections.sh
./scripts/count_kline_connections.sh
```

**输出示例：**
```
==========================================
K线监听连接统计
==========================================
进程ID: 12345
总TCP连接数: 14
到 Binance 连接数: 14
已建立连接数: 14
估计symbol数: 2
==========================================
```

---

### 4. `show_kline_connections_detail.sh` - 详细连接信息脚本

**功能：**
- 显示所有连接的详细信息
- 按状态分组显示
- 显示本地和远程地址

**使用方法：**
```bash
chmod +x scripts/show_kline_connections_detail.sh
./scripts/show_kline_connections_detail.sh
```

---

### 5. `check_kline_connections_by_symbol.sh` - 按Symbol检查脚本

**功能：**
- 通过 HTTP API 获取 symbol 列表
- 显示每个 symbol 的连接情况
- 验证连接完整性

**使用方法：**
```bash
chmod +x scripts/check_kline_connections_by_symbol.sh

# 使用默认地址（localhost:9999）
./scripts/check_kline_connections_by_symbol.sh

# 指定地址
./scripts/check_kline_connections_by_symbol.sh 192.168.1.100 9999
```

---

## 快速命令参考

### 查看所有连接
```bash
ss -tnp | grep fstream.binance.com
```

### 查看特定进程的连接
```bash
# 查找进程
ps aux | grep data_agent

# 查看连接（假设PID是12345）
ss -tnp | grep pid=12345
```

### 统计连接数
```bash
ss -tnp state established | grep fstream.binance.com | wc -l
```

### 实时监控
```bash
watch -n 2 'ss -tnp | grep fstream.binance.com'
```

---

## 连接数计算

- **每个 symbol 有 7 个 interval**: 1m, 5m, 15m, 1h, 4h, 1d, 1w
- **每个 interval 对应 1 个 WebSocket 连接**
- **总连接数 = symbol数 × 7**

### 示例

- 1 个 symbol = 7 个连接
- 2 个 symbol = 14 个连接
- 10 个 symbol = 70 个连接

---

## 故障排查

### 问题1: 找不到 data_agent 进程

```bash
# 检查进程是否运行
ps aux | grep data_agent

# 检查服务状态（如果使用systemd）
systemctl status data-agent
```

### 问题2: 连接数不对

```bash
# 检查连接状态
ss -tnp | grep fstream.binance.com | awk '{print $1}' | sort | uniq -c

# 检查是否有异常状态的连接
ss -tnp | grep fstream.binance.com | grep -v ESTAB
```

### 问题3: 连接被拒绝

```bash
# 检查网络连通性
ping fstream.binance.com

# 检查端口
nc -zv fstream.binance.com 443
```

---

## 注意事项

1. **权限要求**：
   - 查看进程信息需要相应权限
   - 某些命令可能需要 root 权限

2. **命令依赖**：
   - `ss` 命令（推荐，性能最好）
   - `netstat` 命令（传统工具）
   - `lsof` 命令（可选）

3. **连接状态**：
   - `ESTABLISHED`: 正常状态
   - `TIME-WAIT`: 正常关闭中
   - `CLOSE-WAIT`: 可能有问题
   - `SYN-SENT`: 连接被拒绝

---

## 相关文档

- [Linux TCP连接检查详细指南](../docs/LINUX_TCP_CONNECTION_CHECK.md)
- [Data Agent API参考](../docs/DATA_AGENT_API_REFERENCE.md)

