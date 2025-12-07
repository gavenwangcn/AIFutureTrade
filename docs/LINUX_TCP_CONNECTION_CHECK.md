# Linux 中查看 WebSocket TCP 连接的命令指南

本文档介绍如何在 Linux 系统中查看 Data Agent 构建的 WebSocket 长连接（K线监听）对应的 TCP 连接。

---

## 快速命令

### 1. 查看所有 WebSocket 连接到 Binance

```bash
# 使用 ss 命令（推荐，更现代）
ss -tnp | grep fstream.binance.com

# 或使用 netstat 命令
netstat -tnp | grep fstream.binance.com

# 查看 ESTABLISHED 状态的连接
ss -tnp state established | grep fstream.binance.com
```

### 2. 查看特定进程的 TCP 连接

```bash
# 查找 data_agent 进程
ps aux | grep data_agent

# 假设进3程ID是 1245，查看该进程的所有TCP连接
ss -tnp | grep 12345

# 或使用 lsof
lsof -p 12345 -i TCP
```

### 3. 查看所有 WebSocket 连接（443端口，HTTPS/WSS）

```bash
# 查看所有到 443 端口的连接
ss -tnp | grep :443

# 查看 Binance 的 WebSocket 连接（通常是 443 端口）
ss -tnp | grep 'fstream.binance.com:443'
```

---

## 详细命令说明

### 方法1: 使用 `ss` 命令（推荐）

`ss` 是 `netstat` 的现代替代品，性能更好，功能更强大。

#### 基本用法

```bash
# 查看所有TCP连接
ss -tnp

# 参数说明：
# -t: 只显示TCP连接
# -n: 以数字形式显示地址和端口（不解析域名）
# -p: 显示进程信息
```

#### 查看 WebSocket 连接

```bash
# 查看所有到 Binance WebSocket 服务器的连接
ss -tnp | grep fstream.binance.com

# 查看 ESTABLISHED 状态的连接（已建立的连接）
ss -tnp state established | grep fstream.binance.com

# 查看所有 WebSocket 连接（443端口）
ss -tnp | grep ':443'

# 查看特定状态的连接
ss -tnp state established '( dport = :443 )'
```

#### 查看连接详细信息

```bash
# 显示更详细的信息（包括发送/接收队列）
ss -tnp -i | grep fstream.binance.com

# 显示所有TCP连接的统计信息
ss -s
```

#### 实时监控连接

```bash
# 每2秒刷新一次
watch -n 2 'ss -tnp | grep fstream.binance.com'

# 或使用循环
while true; do clear; ss -tnp | grep fstream.binance.com; sleep 2; done
```

---

### 方法2: 使用 `netstat` 命令

`netstat` 是传统的网络工具，大多数系统都预装了。

#### 基本用法

```bash
# 查看所有TCP连接
netstat -tnp

# 参数说明：
# -t: 只显示TCP连接
# -n: 以数字形式显示地址和端口
# -p: 显示进程信息
```

#### 查看 WebSocket 连接

```bash
# 查看所有到 Binance WebSocket 服务器的连接
netstat -tnp | grep fstream.binance.com

# 查看 ESTABLISHED 状态的连接
netstat -tnp | grep ESTABLISHED | grep fstream.binance.com

# 查看所有 WebSocket 连接（443端口）
netstat -tnp | grep ':443'
```

#### 查看连接统计

```bash
# 按状态统计连接数
netstat -tn | awk '/^tcp/ {print $6}' | sort | uniq -c

# 查看特定状态的连接数
netstat -tn | grep ESTABLISHED | wc -l
```

---

### 方法3: 使用 `lsof` 命令

`lsof` 可以查看进程打开的文件和网络连接。

#### 基本用法

```bash
# 查看特定进程的所有TCP连接
lsof -p <PID> -i TCP

# 查看所有到特定主机的连接
lsof -i TCP@fstream.binance.com

# 查看所有到特定端口的连接
lsof -i TCP:443
```

#### 查看 WebSocket 连接

```bash
# 查找 data_agent 进程
ps aux | grep data_agent

# 假设进程ID是 12345
lsof -p 12345 -i TCP

# 查看所有到 Binance 的连接
lsof -i TCP@fstream.binance.com

# 查看所有 WebSocket 连接（443端口）
lsof -i TCP:443
```

---

### 方法4: 使用 `tcpdump` 抓包（高级）

如果需要查看 WebSocket 数据包内容：

```bash
# 抓取所有到 Binance 的流量
sudo tcpdump -i any -n host fstream.binance.com

# 只抓取 WebSocket 流量（443端口）
sudo tcpdump -i any -n 'host fstream.binance.com and port 443'

# 保存到文件
sudo tcpdump -i any -n -w websocket.pcap 'host fstream.binance.com and port 443'
```

---

## 实用脚本

### 脚本1: 查看 Data Agent 的所有 WebSocket 连接

```bash
#!/bin/bash
# 文件名: check_websocket_connections.sh

echo "=========================================="
echo "Data Agent WebSocket 连接检查"
echo "=========================================="

# 查找 data_agent 进程
PID=$(pgrep -f "data_agent.py" | head -1)

if [ -z "$PID" ]; then
    echo "❌ 未找到 data_agent 进程"
    exit 1
fi

echo "✅ 找到 data_agent 进程: PID=$PID"
echo ""

# 查看该进程的所有TCP连接
echo "📡 所有TCP连接:"
ss -tnp | grep "pid=$PID"

echo ""
echo "📡 到 Binance WebSocket 的连接:"
ss -tnp | grep "pid=$PID" | grep fstream.binance.com

echo ""
echo "📊 连接统计:"
echo "  - 总连接数: $(ss -tnp | grep "pid=$PID" | wc -l)"
echo "  - Binance连接数: $(ss -tnp | grep "pid=$PID" | grep fstream.binance.com | wc -l)"
echo "  - ESTABLISHED状态: $(ss -tnp state established | grep "pid=$PID" | grep fstream.binance.com | wc -l)"
```

### 脚本2: 实时监控 WebSocket 连接

```bash
#!/bin/bash
# 文件名: monitor_websocket_connections.sh

PID=$(pgrep -f "data_agent.py" | head -1)

if [ -z "$PID" ]; then
    echo "❌ 未找到 data_agent 进程"
    exit 1
fi

echo "监控 data_agent (PID=$PID) 的 WebSocket 连接..."
echo "按 Ctrl+C 退出"
echo ""

while true; do
    clear
    echo "=========================================="
    echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "进程: data_agent (PID=$PID)"
    echo "=========================================="
    echo ""
    echo "📡 到 Binance WebSocket 的连接:"
    ss -tnp | grep "pid=$PID" | grep fstream.binance.com | while read line; do
        echo "  $line"
    done
    echo ""
    echo "📊 连接统计:"
    echo "  - 总连接数: $(ss -tnp | grep "pid=$PID" | wc -l)"
    echo "  - Binance连接数: $(ss -tnp | grep "pid=$PID" | grep fstream.binance.com | wc -l)"
    echo ""
    sleep 2
done
```

### 脚本3: 检查连接状态和健康度

```bash
#!/bin/bash
# 文件名: check_connection_health.sh

echo "=========================================="
echo "WebSocket 连接健康检查"
echo "=========================================="

# 查找 data_agent 进程
PID=$(pgrep -f "data_agent.py" | head -1)

if [ -z "$PID" ]; then
    echo "❌ 未找到 data_agent 进程"
    exit 1
fi

echo "进程ID: $PID"
echo ""

# 检查连接状态
echo "📊 连接状态统计:"
ss -tnp | grep "pid=$PID" | grep fstream.binance.com | awk '{print $1}' | sort | uniq -c

echo ""
echo "📡 连接详情:"
ss -tnp | grep "pid=$PID" | grep fstream.binance.com | while read line; do
    state=$(echo "$line" | awk '{print $1}')
    local_addr=$(echo "$line" | awk '{print $4}')
    remote_addr=$(echo "$line" | awk '{print $5}')
    
    if [ "$state" = "ESTAB" ]; then
        status="✅ 已建立"
    else
        status="⚠️  $state"
    fi
    
    echo "  $status | 本地: $local_addr -> 远程: $remote_addr"
done

echo ""
echo "📈 连接持续时间（需要 root 权限）:"
sudo ss -tnp -o | grep "pid=$PID" | grep fstream.binance.com | awk '{print $6}'
```

---

## 常用命令组合

### 1. 查看连接数统计

```bash
# 统计每个状态的连接数
ss -tnp | grep fstream.binance.com | awk '{print $1}' | sort | uniq -c

# 统计总连接数
ss -tnp | grep fstream.binance.com | wc -l

# 统计 ESTABLISHED 状态的连接数
ss -tnp state established | grep fstream.binance.com | wc -l
```

### 2. 查看连接详细信息

```bash
# 显示连接状态、本地地址、远程地址、进程信息
ss -tnp | grep fstream.binance.com | awk '{printf "状态: %s | 本地: %s | 远程: %s | 进程: %s\n", $1, $4, $5, $NF}'
```

### 3. 查看连接持续时间

```bash
# 需要 root 权限
sudo ss -tnp -o | grep fstream.binance.com

# 显示连接持续时间（timer 信息）
sudo ss -tnp -o | grep fstream.binance.com | grep -o 'timer:[^,]*'
```

### 4. 查看连接的网络统计

```bash
# 显示发送/接收队列大小
ss -tnp -i | grep fstream.binance.com

# 显示更详细的网络统计
ss -tnp -i | grep fstream.binance.com | grep -E 'send|pacing|delivery'
```

---

## 根据连接数判断状态

### 正常情况

每个 symbol 有 7 个 interval，所以：
- 1 个 symbol = 7 个 WebSocket 连接
- 2 个 symbol = 14 个 WebSocket 连接
- 10 个 symbol = 70 个 WebSocket 连接

### 检查命令

```bash
# 计算当前连接数
CONN_COUNT=$(ss -tnp state established | grep fstream.binance.com | wc -l)
SYMBOL_COUNT=$((CONN_COUNT / 7))

echo "当前连接数: $CONN_COUNT"
echo "估计symbol数: $SYMBOL_COUNT"
echo "每个symbol应该有7个连接（7个interval）"
```

---

## 故障排查

### 1. 检查连接是否建立

```bash
# 查看是否有 ESTABLISHED 状态的连接
ss -tnp state established | grep fstream.binance.com

# 如果没有连接，检查进程是否在运行
ps aux | grep data_agent
```

### 2. 检查连接是否卡住

```bash
# 查看 CLOSE_WAIT 状态的连接（可能有问题）
ss -tnp state close-wait | grep fstream.binance.com

# 查看 TIME_WAIT 状态的连接（正在关闭）
ss -tnp state time-wait | grep fstream.binance.com
```

### 3. 检查连接是否被拒绝

```bash
# 查看 SYN_SENT 状态的连接（连接被拒绝）
ss -tnp state syn-sent | grep fstream.binance.com

# 查看连接错误
dmesg | grep -i "connection"
```

### 4. 检查网络延迟

```bash
# ping Binance 服务器
ping -c 5 fstream.binance.com

# 测试 WebSocket 端口连通性
telnet fstream.binance.com 443

# 或使用 nc
nc -zv fstream.binance.com 443
```

---

## 示例输出解读

### ss 命令输出示例

```
ESTAB 0      0      192.168.1.100:54321 52.84.123.45:443  users:(("python",pid=12345,fd=10))
```

解读：
- `ESTAB`: 连接状态（ESTABLISHED，已建立）
- `192.168.1.100:54321`: 本地地址和端口
- `52.84.123.45:443`: 远程地址和端口（Binance服务器）
- `users:(("python",pid=12345,fd=10))`: 进程信息（Python进程，PID=12345，文件描述符10）

### 连接状态说明

| 状态 | 说明 | 是否正常 |
|------|------|----------|
| `ESTAB` | 连接已建立 | ✅ 正常 |
| `SYN-SENT` | 正在建立连接 | ⚠️ 可能被拒绝 |
| `SYN-RECV` | 正在建立连接 | ⚠️ 可能有问题 |
| `FIN-WAIT-1` | 正在关闭连接 | ⚠️ 正常关闭中 |
| `FIN-WAIT-2` | 正在关闭连接 | ⚠️ 正常关闭中 |
| `TIME-WAIT` | 连接已关闭，等待清理 | ✅ 正常 |
| `CLOSE-WAIT` | 远程端已关闭 | ❌ 可能有问题 |
| `LAST-ACK` | 等待最后确认 | ⚠️ 正常关闭中 |

---

## 一键检查脚本

创建一个综合检查脚本：

```bash
#!/bin/bash
# 文件名: check_data_agent_connections.sh

echo "=========================================="
echo "Data Agent WebSocket 连接综合检查"
echo "=========================================="
echo ""

# 1. 检查进程
echo "1️⃣ 检查 data_agent 进程:"
PID=$(pgrep -f "data_agent.py" | head -1)
if [ -z "$PID" ]; then
    echo "   ❌ 未找到 data_agent 进程"
    exit 1
else
    echo "   ✅ 进程ID: $PID"
    echo "   📋 进程信息:"
    ps -p $PID -o pid,user,cmd --no-headers | sed 's/^/      /'
fi
echo ""

# 2. 检查TCP连接
echo "2️⃣ 检查TCP连接:"
CONN_COUNT=$(ss -tnp | grep "pid=$PID" | wc -l)
BINANCE_CONN=$(ss -tnp | grep "pid=$PID" | grep fstream.binance.com | wc -l)
ESTAB_CONN=$(ss -tnp state established | grep "pid=$PID" | grep fstream.binance.com | wc -l)

echo "   📊 连接统计:"
echo "      - 总TCP连接数: $CONN_COUNT"
echo "      - Binance连接数: $BINANCE_CONN"
echo "      - 已建立连接数: $ESTAB_CONN"
echo ""

# 3. 显示连接详情
if [ $BINANCE_CONN -gt 0 ]; then
    echo "   📡 连接详情:"
    ss -tnp | grep "pid=$PID" | grep fstream.binance.com | while read line; do
        state=$(echo "$line" | awk '{print $1}')
        local_addr=$(echo "$line" | awk '{print $4}')
        remote_addr=$(echo "$line" | awk '{print $5}')
        
        if [ "$state" = "ESTAB" ]; then
            echo "      ✅ $local_addr -> $remote_addr"
        else
            echo "      ⚠️  [$state] $local_addr -> $remote_addr"
        fi
    done
else
    echo "   ⚠️  未找到到 Binance 的连接"
fi
echo ""

# 4. 估算symbol数量
if [ $ESTAB_CONN -gt 0 ]; then
    SYMBOL_COUNT=$((ESTAB_CONN / 7))
    echo "   📈 估算:"
    echo "      - 已建立连接数: $ESTAB_CONN"
    echo "      - 估计symbol数: $SYMBOL_COUNT (每个symbol有7个interval)"
fi
echo ""

# 5. 检查连接状态分布
echo "3️⃣ 连接状态分布:"
ss -tnp | grep "pid=$PID" | grep fstream.binance.com | awk '{print $1}' | sort | uniq -c | while read count state; do
    echo "      - $state: $count 个"
done
echo ""

# 6. 网络连通性测试
echo "4️⃣ 网络连通性测试:"
if ping -c 1 -W 2 fstream.binance.com > /dev/null 2>&1; then
    echo "   ✅ Binance 服务器可达"
else
    echo "   ❌ Binance 服务器不可达"
fi
echo ""

echo "=========================================="
echo "检查完成"
echo "=========================================="
```

---

## 使用示例

### 示例1: 快速检查

```bash
# 查看所有 WebSocket 连接
ss -tnp | grep fstream.binance.com
```

### 示例2: 查看特定进程的连接

```bash
# 查找进程
ps aux | grep data_agent

# 查看该进程的连接（假设PID是12345）
ss -tnp | grep pid=12345
```

### 示例3: 实时监控

```bash
# 每2秒刷新一次
watch -n 2 'ss -tnp | grep fstream.binance.com'
```

### 示例4: 保存连接信息

```bash
# 保存到文件
ss -tnp | grep fstream.binance.com > websocket_connections.txt

# 带时间戳
echo "=== $(date) ===" >> websocket_connections.log
ss -tnp | grep fstream.binance.com >> websocket_connections.log
```

---

## 注意事项

1. **权限要求**：
   - 查看进程信息需要相应权限
   - 某些命令（如 `lsof`）可能需要 root 权限

2. **性能影响**：
   - `ss` 命令性能最好，推荐使用
   - `netstat` 在连接数很多时可能较慢

3. **连接数计算**：
   - 每个 symbol 有 7 个 interval
   - 每个 interval 对应 1 个 WebSocket 连接
   - 总连接数 = symbol数 × 7

4. **连接状态**：
   - `ESTABLISHED` 是正常状态
   - 如果看到大量 `CLOSE_WAIT` 或 `TIME_WAIT`，可能有问题

---

## 相关文件

- `data/data_agent.py`: Data Agent 主代码
- `tests/websocket_klines.py`: WebSocket 测试代码
- `tests/test_data_agent.py`: Data Agent 测试代码

