# K线价格精度排查报告

## 排查目标
检查获取历史K线数据的API接口内部逻辑，确认是否有截取SDK真实返回的symbol的K线数据价格精度，要求保留小数点后6位。

## 排查结果

### 1. SDK返回数据流程

#### 1.1 `common/binance_futures.py` - `get_klines` 方法
- **位置**: `common/binance_futures.py:576-705`
- **功能**: 调用币安官方SDK获取K线数据
- **返回格式**: 
  - 列表格式：`[open_time, open_price, high_price, low_price, close_price, ...]`
  - 字典格式：`{"open": ..., "high": ..., "low": ..., "close": ...}`
- **价格数据格式**: 
  - SDK返回的价格可能是字符串格式（币安API标准格式）
  - 也可能是数字格式（取决于SDK版本）
  - **关键点**: 在 `get_klines` 方法中，价格数据**直接赋值**，**没有进行任何格式化或截取**

```python
# 列表格式处理（第635-656行）
open_price = item[1]  # 直接赋值，无格式化
high_price = item[2]  # 直接赋值，无格式化
low_price = item[3]   # 直接赋值，无格式化
close_price = item[4] # 直接赋值，无格式化

kline_dict = {
    "open": open_price,  # 直接保存原始值
    "high": high_price,
    "low": low_price,
    "close": close_price,
    ...
}
```

```python
# 字典格式处理（第680-683行）
kline_dict = {
    "open": entry.get("open") or entry.get("o"),  # 直接获取原始值
    "high": entry.get("high") or entry.get("h"),
    "low": entry.get("low") or entry.get("l"),
    "close": entry.get("close") or entry.get("c"),
    ...
}
```

**结论**: ✅ SDK返回的价格数据**没有被截取**，保持了原始精度。

### 2. API接口数据处理

#### 2.1 `backend/app.py` - `/api/market/klines` 接口
- **位置**: `backend/app.py:1207-1344`
- **数据源**: 
  - SDK模式：从 `market_fetcher._futures_client.get_klines()` 获取
  - DB模式：从 `ClickHouseDatabase.get_market_klines()` 获取

#### 2.2 SDK模式数据处理（第1300-1312行）
```python
# 转换SDK返回数据为统一格式，价格保留6位小数
formatted_klines = []
for kline in klines:
    formatted_klines.append({
        'timestamp': kline.get('open_time', 0),
        'open': round(float(kline.get('open', 0)), 6),    # ✅ 保留6位小数
        'high': round(float(kline.get('high', 0)), 6),    # ✅ 保留6位小数
        'low': round(float(kline.get('low', 0)), 6),      # ✅ 保留6位小数
        'close': round(float(kline.get('close', 0)), 6),  # ✅ 保留6位小数
        'volume': float(kline.get('volume', 0)),
        'turnover': float(kline.get('quote_asset_volume', 0))
    })
```

**结论**: ✅ API接口**正确保留6位小数**，使用 `round(float(...), 6)` 格式化。

#### 2.3 DB模式数据处理
- **位置**: `common/database_clickhouse.py:2087-2171`
- **查询**: 从ClickHouse数据库查询K线数据
- **格式化**: 
```python
klines.append({
    'timestamp': int(row[0]),
    'open': round(float(row[1]), 6),   # ✅ 保留6位小数
    'high': round(float(row[2]), 6),   # ✅ 保留6位小数
    'low': round(float(row[3]), 6),     # ✅ 保留6位小数
    'close': round(float(row[4]), 6),  # ✅ 保留6位小数
    ...
})
```

**结论**: ✅ 数据库查询返回的数据**正确保留6位小数**。

### 3. 潜在问题分析

#### 3.1 SDK返回数据精度
- **币安API标准**: K线数据返回的价格通常是**字符串格式**，精度取决于交易对的精度设置
- **常见精度**: 大多数交易对的价格精度为**8位小数**（如 BTC/USDT）
- **潜在风险**: 如果SDK返回的价格字符串本身精度不够（如只有2位小数），那么即使使用 `round(..., 6)` 也无法恢复原始精度

#### 3.2 数据转换过程
1. SDK返回: 字符串格式价格（如 `"12345.12345678"`）
2. `get_klines` 方法: 直接保存为字符串（无格式化）
3. API接口: `float("12345.12345678")` → `12345.12345678` → `round(..., 6)` → `12345.123456`

**如果SDK返回的字符串只有2位小数**（如 `"12345.12"`）:
1. SDK返回: `"12345.12"`
2. `get_klines` 方法: 保存为 `"12345.12"`
3. API接口: `float("12345.12")` → `12345.12` → `round(12345.12, 6)` → `12345.12`（无法恢复6位小数）

### 4. 改进措施

#### 4.1 添加调试日志
已在 `backend/app.py` 中添加调试日志，记录：
- SDK返回的原始价格数据格式和类型
- 格式化后的价格数据（保留6位小数）

这样可以确认SDK返回的数据精度是否足够。

#### 4.2 数据验证建议
建议在实际运行中检查日志输出，确认：
1. SDK返回的价格数据格式（字符串/数字）
2. SDK返回的价格数据精度（小数位数）
3. 格式化后的价格数据是否符合预期

### 5. 总结

✅ **SDK返回数据**: 没有被截取，保持了原始精度
✅ **API接口处理**: 正确使用 `round(float(...), 6)` 保留6位小数
✅ **数据库查询**: 正确使用 `round(float(...), 6)` 保留6位小数

⚠️ **注意事项**: 
- 如果SDK返回的价格数据本身精度不够（如只有2位小数），则无法通过格式化恢复6位小数
- 币安API通常返回足够精度的价格数据（8位小数），但需要在实际运行中验证

## 相关文件
- `backend/app.py`: API接口实现
- `common/binance_futures.py`: SDK客户端封装
- `common/database_clickhouse.py`: 数据库查询实现

