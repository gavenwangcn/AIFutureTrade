# 交易循环 SDK 接口调用分析

## 配置信息
- **交易循环频率**: 每3分钟循环一次
- **买入循环频率**: 每3分钟一次
- **卖出循环频率**: 每3分钟一次
- **候选symbol数量**: 默认从涨跌幅榜获取10个（`PROMPT_MARKET_SYMBOL_LIMIT * 2`）

## SDK 接口调用分析

### 1. 买入循环（execute_buy_cycle）

#### 1.1 价格查询
- **方法**: `market_fetcher.get_prices(symbol_list)`
- **数据源**: 从数据库 `24_market_tickers` 表获取（**不是SDK调用**）
- **调用次数**: 0次 SDK API调用

#### 1.2 K线数据查询
- **方法**: `_merge_timeframe_data(symbol)` → `get_market_data_*` → `_get_market_data_by_interval` → `get_klines`
- **时间周期**: 7个时间周期（1m, 5m, 15m, 1h, 4h, 1d, 1w）
- **每个symbol的调用次数**: 7次 SDK API调用
- **候选symbol数量**: 默认10个（从涨跌幅榜获取）
- **总K线API调用次数**: 10个symbol × 7个时间周期 = **70次/循环**

#### 1.3 买入循环总结
- **价格API调用**: 0次（从数据库获取）
- **K线API调用**: 70次/循环
- **总SDK调用**: 70次/循环

---

### 2. 卖出循环（execute_sell_cycle）

#### 2.1 价格查询
- **方法**: `market_fetcher.get_current_prices(formatted_symbols)`
- **数据源**: SDK API (`get_symbol_prices`)
- **调用方式**: 逐个调用，每个symbol一次API调用
- **持仓symbol数量**: 假设M个持仓
- **价格API调用次数**: **M次/循环**（每个持仓symbol一次）

#### 2.2 K线数据查询
- **方法**: `_merge_timeframe_data(symbol)` → `get_market_data_*` → `_get_market_data_by_interval` → `get_klines`
- **时间周期**: 7个时间周期（1m, 5m, 15m, 1h, 4h, 1d, 1w）
- **每个symbol的调用次数**: 7次 SDK API调用
- **持仓symbol数量**: 假设M个持仓
- **总K线API调用次数**: M个symbol × 7个时间周期 = **7M次/循环**

#### 2.3 卖出循环总结
- **价格API调用**: M次/循环
- **K线API调用**: 7M次/循环
- **总SDK调用**: 8M次/循环

---

## 每分钟调用次数计算

### 假设条件
- **交易循环频率**: 每3分钟一次
- **候选symbol数量**: 10个（买入循环）
- **持仓symbol数量**: M个（卖出循环，假设M=3）

### 每分钟调用次数

#### 买入循环（每3分钟一次）
- **K线API调用**: 70次/循环 ÷ 3分钟 = **23.3次/分钟**
- **价格API调用**: 0次/分钟（从数据库获取）

#### 卖出循环（每3分钟一次）
- **价格API调用**: M次/循环 ÷ 3分钟 = **M/3次/分钟**（假设M=3，则为1次/分钟）
- **K线API调用**: 7M次/循环 ÷ 3分钟 = **7M/3次/分钟**（假设M=3，则为7次/分钟）

### 总计（假设M=3个持仓）
- **价格API调用**: 0 + 1 = **1次/分钟**
- **K线API调用**: 23.3 + 7 = **30.3次/分钟**
- **总SDK调用**: **31.3次/分钟**

---

## 详细调用流程

### 买入循环调用链
```
execute_buy_cycle()
  └─> _select_buy_candidates()
      └─> _build_market_state_for_candidates()
          ├─> get_prices() [数据库查询，非SDK]
          └─> _merge_timeframe_data() [对每个symbol]
              ├─> get_market_data_1m() → get_klines() [SDK API调用]
              ├─> get_market_data_5m() → get_klines() [SDK API调用]
              ├─> get_market_data_15m() → get_klines() [SDK API调用]
              ├─> get_market_data_1h() → get_klines() [SDK API调用]
              ├─> get_market_data_4h() → get_klines() [SDK API调用]
              ├─> get_market_data_1d() → get_klines() [SDK API调用]
              └─> get_market_data_1w() → get_klines() [SDK API调用]
```

### 卖出循环调用链
```
execute_sell_cycle()
  └─> _get_market_state()
      ├─> get_current_prices() → get_symbol_prices() [SDK API调用，每个symbol一次]
      └─> _merge_timeframe_data() [对每个持仓symbol]
          ├─> get_market_data_1m() → get_klines() [SDK API调用]
          ├─> get_market_data_5m() → get_klines() [SDK API调用]
          ├─> get_market_data_15m() → get_klines() [SDK API调用]
          ├─> get_market_data_1h() → get_klines() [SDK API调用]
          ├─> get_market_data_4h() → get_klines() [SDK API调用]
          ├─> get_market_data_1d() → get_klines() [SDK API调用]
          └─> get_market_data_1w() → get_klines() [SDK API调用]
```

---

## 关键发现

1. **价格查询优化**: 买入循环使用数据库查询价格，不调用SDK API，减少了API调用次数
2. **K线查询是主要开销**: 每次循环需要为每个symbol获取7个时间周期的K线数据
3. **卖出循环价格查询**: 使用SDK API实时获取价格，每个持仓symbol一次调用
4. **调用频率**: 每3分钟循环一次，平均每分钟约30-35次SDK API调用（取决于持仓数量）

---

## 优化建议

1. **缓存K线数据**: 对于1d和1w等较长周期，可以考虑缓存，减少API调用
2. **批量获取价格**: 卖出循环可以考虑批量获取价格，而不是逐个调用
3. **按需获取K线**: 如果策略不需要所有7个时间周期，可以只获取需要的周期
4. **增加循环间隔**: 如果API调用频率过高，可以考虑增加循环间隔时间

---

## 代码位置参考

- **买入循环**: `trade/trading_engine.py:247` - `execute_buy_cycle()`
- **卖出循环**: `trade/trading_engine.py:108` - `execute_sell_cycle()`
- **K线获取**: `market/market_data.py:1100` - `_get_market_data_by_interval()`
- **价格获取**: `market/market_data.py:285` - `get_prices()` (数据库) / `market/market_data.py:354` - `get_current_prices()` (SDK)
- **SDK调用**: `common/binance_futures.py:513` - `get_klines()` / `common/binance_futures.py:435` - `get_symbol_prices()`

