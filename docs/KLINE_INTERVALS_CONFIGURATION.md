# K线时间间隔（Interval）配置说明

## 概述

K线时间间隔（interval）数量现在可以通过配置文件进行自定义，默认配置为7个interval：`['1m', '5m', '15m', '1h', '4h', '1d', '1w']`。

## 配置位置

### 1. data_agent 配置（生产环境）

**配置文件：** `common/config.py`

**配置项：** `DATA_AGENT_KLINE_INTERVALS`

**默认值：** `['1m', '5m', '15m', '1h', '4h', '1d', '1w']`（7个interval）

**配置方式：**

#### 方式1：通过环境变量配置

```bash
# 设置环境变量（用逗号分隔）
export DATA_AGENT_KLINE_INTERVALS="1m,5m,15m,1h,4h,1d,1w"

# 或者只配置部分interval
export DATA_AGENT_KLINE_INTERVALS="1m,5m,15m"
```

#### 方式2：直接修改 config.py

```python
# common/config.py
DATA_AGENT_KLINE_INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
```

### 2. 测试代码配置（测试环境）

**配置文件：** `tests/test_data_agent.py`

**配置项：** `TEST_KLINE_INTERVALS`

**默认值：** `['1m', '5m', '15m', '1h', '4h', '1d', '1w']`（7个interval）

**配置方式：**

```python
# tests/test_data_agent.py
# 测试用的K线时间间隔列表（默认7个interval，与data_agent默认配置一致）
TEST_KLINE_INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']  # 默认7个interval

# 或者设置为None，使用data_agent的配置
TEST_KLINE_INTERVALS = None  # 使用data_agent中的配置（从config.py读取）
```

## 支持的Interval值

Binance支持的K线时间间隔：
- `1m` - 1分钟
- `3m` - 3分钟
- `5m` - 5分钟
- `15m` - 15分钟
- `30m` - 30分钟
- `1h` - 1小时
- `2h` - 2小时
- `4h` - 4小时
- `6h` - 6小时
- `8h` - 8小时
- `12h` - 12小时
- `1d` - 1天
- `3d` - 3天
- `1w` - 1周
- `1M` - 1月

**注意：** 当前默认配置使用的是：`['1m', '5m', '15m', '1h', '4h', '1d', '1w']`

## 代码使用

### data_agent.py

```python
# data/data_agent.py
from common.config import DATA_AGENT_KLINE_INTERVALS as KLINE_INTERVALS

# 使用配置的interval列表
for interval in KLINE_INTERVALS:
    # 处理每个interval
    pass
```

### test_data_agent.py

```python
# tests/test_data_agent.py
from data.data_agent import KLINE_INTERVALS as DATA_AGENT_KLINE_INTERVALS

# 使用测试配置的interval列表，如果为None则使用data_agent的配置
test_intervals = TEST_KLINE_INTERVALS if TEST_KLINE_INTERVALS is not None else DATA_AGENT_KLINE_INTERVALS

# 使用test_intervals进行测试
for interval in test_intervals:
    # 测试每个interval
    pass
```

## 配置示例

### 示例1：只使用快速interval（用于快速测试）

```python
# common/config.py
DATA_AGENT_KLINE_INTERVALS = ['1m', '5m', '15m']  # 只使用3个快速interval
```

### 示例2：使用所有支持的interval

```python
# common/config.py
DATA_AGENT_KLINE_INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d', '1w', '1M']  # 8个interval
```

### 示例3：测试代码使用不同的配置

```python
# tests/test_data_agent.py
TEST_KLINE_INTERVALS = ['1m', '5m']  # 测试时只使用2个interval，加快测试速度
```

## 配置影响

### 1. 连接数计算

每个symbol的连接数 = interval数量

例如：
- 默认配置（7个interval）：每个symbol需要7个连接
- 自定义配置（3个interval）：每个symbol需要3个连接

### 2. 最大连接数

```python
# data/data_agent.py
self._max_connections = max_symbols * len(KLINE_INTERVALS)
```

例如：
- 默认配置：`max_symbols=100, interval_count=7` → 最大连接数 = 700
- 自定义配置：`max_symbols=100, interval_count=3` → 最大连接数 = 300

### 3. 数据库表

每个interval对应一个ClickHouse表：
- `market_klines_1m` - 1分钟K线表
- `market_klines_5m` - 5分钟K线表
- `market_klines_15m` - 15分钟K线表
- `market_klines_1h` - 1小时K线表
- `market_klines_4h` - 4小时K线表
- `market_klines_1d` - 1天K线表
- `market_klines_1w` - 1周K线表

如果配置了新的interval，需要确保对应的表已创建。

## 注意事项

1. **配置一致性**：确保 `data_agent` 和测试代码使用相同的interval配置，避免测试结果不一致。

2. **数据库表**：如果添加了新的interval，需要确保ClickHouse中已创建对应的表。

3. **性能影响**：interval数量越多，连接数越多，资源消耗越大。建议根据实际需求配置。

4. **环境变量格式**：使用环境变量配置时，interval之间用逗号分隔，不要有空格（或会被自动清理）。

5. **配置验证**：代码会自动清理空白字符，但不会验证interval是否有效。请确保配置的interval是Binance支持的。

## 配置验证

配置后，可以通过以下方式验证：

### 1. 查看data_agent日志

启动data_agent后，查看日志中的interval配置：

```
[DataAgentKline] 支持的interval: ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
```

### 2. 运行测试代码

```bash
python -m tests.test_data_agent
```

查看测试输出中的interval配置：

```
[测试] 📋 测试配置:
[测试]   - Interval数量: 7
[测试]   - Interval列表: ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
```

### 3. 通过HTTP API查询

```bash
curl http://localhost:9999/status
```

返回结果中包含当前使用的interval信息。

---

## 相关文件

- `common/config.py`: data_agent配置文件
- `data/data_agent.py`: data_agent主代码
- `tests/test_data_agent.py`: 测试代码

