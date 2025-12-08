# K线数据SDK批量查询优化说明

## 优化背景

由于币安SDK单次查询历史K线数据最多只能返回120条（limit限制），但K线页面需要300+条数据显示以便计算各类指标（如MA99需要99根K线），因此需要实现多次查询来获取足够的历史数据。

## 优化方案

### 1. 配置项

在 `common/config.py` 中新增配置项：

```python
KLINE_SDK_QUERY_BATCH_COUNT = int(os.getenv('KLINE_SDK_QUERY_BATCH_COUNT', '3'))  # SDK模式下查询批次次数，默认3次（120*3=360条）
```

**说明**：
- 默认值：3次
- 可通过环境变量 `KLINE_SDK_QUERY_BATCH_COUNT` 调整
- 每次查询120条，3次共360条数据

### 2. 查询逻辑

#### 2.1 查询流程

1. **第一次查询**：
   - `endTime`: 当前时间（或传入的`end_time`参数）
   - `startTime`: 不传入（`None`）
   - `limit`: 120
   - **特殊处理**：去掉返回的第一根K线（因为最近一根K线通过WebSocket监听接口实时获取）

2. **第二次查询**：
   - `endTime`: 第一次查询最后一根K线的`open_time` - 1毫秒
   - `startTime`: 不传入（`None`）
   - `limit`: 120

3. **第三次查询**（如果配置了3次）：
   - `endTime`: 第二次查询最后一根K线的`open_time` - 1毫秒
   - `startTime`: 不传入（`None`）
   - `limit`: 120

#### 2.2 数据合并

- 所有批次查询的结果合并到一个数组中
- 由于SDK返回的数据是倒序的（从新到旧），需要按`timestamp`升序排序（从旧到新）

#### 2.3 停止条件

查询会在以下情况停止：
1. 达到配置的批次次数
2. 某批次返回的数据少于120条（说明已获取到最早的数据）
3. 某批次查询失败
4. 某批次返回的数据为空

### 3. 代码实现

#### 3.1 核心逻辑

```python
# SDK模式下需要多次查询以获取足够的历史数据
batch_count = KLINE_SDK_QUERY_BATCH_COUNT  # 默认3次，可配置
sdk_limit_per_batch = 120  # SDK单次查询最大限制

all_klines = []
current_end_time = end_timestamp  # 第一次查询的endTime

# 循环查询多次
for batch_idx in range(batch_count):
    # 调用SDK获取K线数据（只传入endTime）
    batch_klines = market_fetcher._futures_client.get_klines(
        symbol=symbol,
        interval=interval,
        limit=sdk_limit_per_batch,
        startTime=None,  # 不传入startTime
        endTime=current_end_time
    )
    
    # 第一次查询去掉第一根K线
    if batch_idx == 0 and len(batch_klines) > 0:
        batch_klines = batch_klines[1:]
    
    # 格式化数据并添加到总结果中
    formatted_batch_klines = [...]
    all_klines.extend(formatted_batch_klines)
    
    # 准备下一次查询的endTime
    if len(formatted_batch_klines) > 0:
        earliest_kline_timestamp = formatted_batch_klines[-1].get('timestamp', 0)
        current_end_time = earliest_kline_timestamp - 1  # 减1毫秒，避免重复

# 按timestamp升序排序
all_klines.sort(key=lambda x: x.get('timestamp', 0))
klines = all_klines
```

#### 3.2 关键点

1. **只传入endTime**：每次查询只传入`endTime`参数，不传入`startTime`
2. **第一次查询特殊处理**：去掉第一根K线（因为最近一根通过监听接口获取）
3. **时间戳递减**：每次查询的`endTime`为上一次查询最早K线的`open_time - 1`毫秒
4. **数据排序**：合并后按`timestamp`升序排序

### 4. 数据流向

```
第一次查询（endTime=当前时间）
  ↓
返回120条K线（倒序：最新→最早）
  ↓
去掉第一根（最新的）
  ↓
剩余119条
  ↓
第二次查询（endTime=第一次查询最早K线的open_time - 1）
  ↓
返回120条K线（倒序）
  ↓
第三次查询（endTime=第二次查询最早K线的open_time - 1）
  ↓
返回120条K线（倒序）
  ↓
合并所有结果（119 + 120 + 120 = 359条）
  ↓
按timestamp升序排序
  ↓
返回给前端
```

### 5. 配置示例

#### 5.1 使用默认值（3次）

无需配置，系统自动使用默认值：
- 查询3次
- 每次120条
- 共约359条数据（第一次去掉1根）

#### 5.2 通过环境变量调整

```bash
# Linux/Mac
export KLINE_SDK_QUERY_BATCH_COUNT=5  # 查询5次，共约599条

# Windows PowerShell
$env:KLINE_SDK_QUERY_BATCH_COUNT="5"
```

#### 5.3 Docker Compose配置

```yaml
services:
  backend:
    environment:
      - KLINE_SDK_QUERY_BATCH_COUNT=5
```

### 6. 日志输出

优化后的代码会输出详细的日志信息：

```
[API] 从SDK获取K线数据: symbol=BTCUSDT, interval=5m, 查询批次=3, 每批=120条
[API] SDK查询批次 1/3: endTime=1765203365000
[API] 第一次查询，去掉第一根K线（最近一根通过监听接口获取）
[API] SDK批次 1 完成，获取 119 条K线数据
[API] 批次 1 最早K线时间戳: 1765196765000, 下次查询endTime: 1765196764999
[API] SDK查询批次 2/3: endTime=1765196764999
[API] SDK批次 2 完成，获取 120 条K线数据
[API] SDK查询批次 3/3: endTime=1765190164999
[API] SDK批次 3 完成，获取 120 条K线数据
[API] SDK查询完成，共获取 359 条K线数据（3个批次）
```

### 7. 注意事项

1. **数据去重**：通过`endTime - 1`毫秒避免重复数据
2. **时间顺序**：SDK返回的数据是倒序的，需要排序
3. **第一次查询特殊处理**：去掉第一根K线，避免与实时数据重复
4. **错误处理**：如果某批次查询失败，会停止后续查询并记录错误
5. **数据量限制**：如果某批次返回少于120条，说明已获取到最早数据，停止查询

### 8. 性能考虑

- **查询次数**：默认3次，可根据实际需求调整
- **查询延迟**：每次查询约100-500ms，3次查询总延迟约300-1500ms
- **数据量**：默认约359条，满足大多数指标计算需求（MA99需要99根）

### 9. 相关文件

- `backend/app.py`: `get_market_klines()` 函数
- `common/config.py`: `KLINE_SDK_QUERY_BATCH_COUNT` 配置项
- `common/binance_futures.py`: `get_klines()` 方法

### 10. 测试建议

1. **测试不同批次次数**：验证1次、3次、5次查询的结果
2. **测试边界情况**：数据不足120条的情况
3. **测试时间范围**：验证时间戳递减逻辑
4. **测试数据排序**：验证最终数据是否按时间升序排列
5. **测试去重**：验证是否有重复的K线数据

