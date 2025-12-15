# account_value_historys 数据插入和使用流程分析

## 📋 概述

`account_value_historys` 表用于记录每个交易模型的历史账户价值数据，支持前端页面展示资金走势图表。本文档详细分析了数据插入的场景逻辑和前端使用方式。

---

## 🔄 数据插入场景

### 1. 插入触发时机

账户价值历史数据在以下两个交易周期结束时自动插入：

#### 场景1：买入周期结束 (`execute_buy_cycle`)
```python
# 位置: trade/trading_engine.py:309
def execute_buy_cycle(self):
    try:
        # ... 买入决策和执行逻辑 ...
        
        # 记录账户价值快照
        current_prices = self.market_data_fetcher.get_prices()
        self._record_account_snapshot(current_prices)
        
        # 同步model_futures表
        self._sync_model_futures()
        
        return updated_portfolio
    except Exception as e:
        # 错误处理...
```

#### 场景2：卖出周期结束 (`execute_sell_cycle`)
```python
# 位置: trade/trading_engine.py:495
def execute_sell_cycle(self):
    try:
        # ... 卖出决策和执行逻辑 ...
        
        # 记录账户价值快照
        current_prices = self.market_data_fetcher.get_prices()
        self._record_account_snapshot(current_prices)
        
        # 同步model_futures表
        self._sync_model_futures()
        
        return updated_portfolio
    except Exception as e:
        # 错误处理...
```

### 2. 插入方法调用链

```
execute_buy_cycle() / execute_sell_cycle()
    ↓
_record_account_snapshot(current_prices)
    ↓
db.get_portfolio(model_id, current_prices)  # 获取最新投资组合数据
    ↓
db.record_account_value(...)  # 记录账户价值
    ↓
┌─────────────────────────────────────────┐
│ 1. 更新 account_values 表 (UPDATE/INSERT) │
│    - 每个model_id只有一条最新记录        │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 2. 插入 account_value_historys 表 (INSERT) │
│    - 每次调用都插入新记录，保留完整历史   │
│    - 使用UTC+8时区时间                   │
└─────────────────────────────────────────┘
```

### 3. 数据来源和计算

#### `_record_account_snapshot` 方法实现
```python
# 位置: trade/trading_engine.py:695-721
def _record_account_snapshot(self, current_prices: Dict) -> None:
    """
    记录账户价值快照（公共方法）
    
    Args:
        current_prices: 当前价格映射
    """
    # 1. 获取最新投资组合数据（包含实时价格）
    updated_portfolio = self.db.get_portfolio(self.model_id, current_prices)
    
    # 2. 提取账户价值字段
    balance = updated_portfolio.get('total_value', 0)           # 总余额
    available_balance = updated_portfolio.get('cash', 0)        # 可用余额
    cross_wallet_balance = updated_portfolio.get('positions_value', 0)  # 全仓余额
    
    # 3. 获取账户别名
    model = self.db.get_model(self.model_id)
    account_alias = model.get('account_alias', '') if model else ''
    
    # 4. 调用数据库方法记录账户价值
    self.db.record_account_value(
        self.model_id,
        balance=balance,
        available_balance=available_balance,
        cross_wallet_balance=cross_wallet_balance,
        account_alias=account_alias
    )
```

#### `record_account_value` 方法实现
```python
# 位置: common/database_basic.py:1597-1700
def record_account_value(self, model_id: int, balance: float,
                        available_balance: float, cross_wallet_balance: float,
                        account_alias: str = '', cross_un_pnl: float = 0.0):
    """
    Record account value snapshot
    
    注意：
    1. account_values表：每个model_id只有一条记录，如果已存在则UPDATE，不存在则INSERT
    2. account_value_historys表：每次调用都INSERT新记录，保留完整历史
    """
    # 1. 更新或插入 account_values 表（最新值）
    # ...
    
    # 2. 插入 account_value_historys 表（历史记录）
    history_id = self._generate_id()
    beijing_tz = timezone(timedelta(hours=8))
    current_time = datetime.now(beijing_tz)  # UTC+8时间
    
    self.insert_rows(
        self.account_value_historys_table,
        [[history_id, model_uuid, account_alias, balance, 
          available_balance, cross_wallet_balance, cross_un_pnl, current_time]],
        ["id", "model_id", "account_alias", "balance", "available_balance", 
         "cross_wallet_balance", "cross_un_pnl", "timestamp"]
    )
```

### 4. 插入的数据字段

| 字段名 | 说明 | 数据来源 |
|--------|------|----------|
| `id` | 唯一标识 | `_generate_id()` 生成UUID |
| `model_id` | 模型UUID | 从models表映射获取 |
| `account_alias` | 账户别名 | 从models表获取 |
| `balance` | 总余额 | `portfolio.total_value` |
| `available_balance` | 可用余额 | `portfolio.cash` |
| `cross_wallet_balance` | 全仓余额 | `portfolio.positions_value` |
| `cross_un_pnl` | 未实现盈亏 | 默认0.0（可扩展） |
| `timestamp` | 时间戳 | UTC+8时区的当前时间 |

---

## 📊 前端数据使用流程

### 1. API接口

#### 获取单个模型的账户价值历史
```python
# 位置: backend/app.py:802
@app.route('/api/models/<int:model_id>/portfolio', methods=['GET'])
def get_model_portfolio(model_id):
    # ...
    account_value = db.get_account_value_history(model_id, limit=100)
    
    return jsonify({
        'portfolio': portfolio,
        'account_value_history': account_value,  # 返回历史数据
        'auto_trading_enabled': bool(model.get('auto_trading_enabled', 1)),
        'leverage': model.get('leverage', 10)
    })
```

#### 数据库查询方法
```python
# 位置: common/database_basic.py:1700-1745
def get_account_value_history(self, model_id: int, limit: int = 100) -> List[Dict]:
    """
    Get account value history
    
    Returns:
        账户价值历史记录列表，包含字段：
        - accountAlias: 账户唯一识别码
        - balance: 总余额
        - availableBalance: 下单可用余额
        - crossWalletBalance: 全仓余额
        - crossUnPnl: 全仓持仓未实现盈亏
        - timestamp: ISO格式字符串（UTC+8时区）
    """
    # 从 account_value_historys 表查询历史记录
    rows = self.query(f"""
        SELECT id, model_id, account_alias, balance, available_balance, 
               cross_wallet_balance, cross_un_pnl, timestamp
        FROM {self.account_value_historys_table}
        WHERE model_id = '{model_uuid}'
        ORDER BY timestamp DESC
        LIMIT {limit}
    """)
    
    # 转换为驼峰命名格式，并将timestamp转换为ISO格式字符串
    formatted_results = []
    for result in results:
        timestamp_str = self._format_timestamp_to_string(result.get("timestamp"))
        formatted_results.append({
            "id": result.get("id"),
            "model_id": result.get("model_id"),
            "accountAlias": result.get("account_alias", ""),
            "balance": result.get("balance", 0.0),
            "availableBalance": result.get("available_balance", 0.0),
            "crossWalletBalance": result.get("cross_wallet_balance", 0.0),
            "crossUnPnl": result.get("cross_un_pnl", 0.0),
            "timestamp": timestamp_str  # ISO格式：'2024-01-01T12:00:00+08:00'
        })
    return formatted_results
```

### 2. 前端数据获取

#### 加载投资组合数据
```javascript
// 位置: frontend/src/composables/useTradingApp.js:630-669
const loadPortfolio = async () => {
  if (!currentModelId.value) return
  
  loading.value.portfolio = true
  errors.value.portfolio = null
  try {
    // 调用API获取投资组合和账户价值历史
    const data = await modelApi.getPortfolio(currentModelId.value)
    
    if (data.portfolio) {
      portfolio.value = {
        totalValue: data.portfolio.total_value || 0,
        availableCash: data.portfolio.cash || 0,
        realizedPnl: data.portfolio.realized_pnl || 0,
        unrealizedPnl: data.portfolio.unrealized_pnl || 0
      }
    }
    
    // 保存账户价值历史数据
    if (data.account_value_history) {
      accountValueHistory.value = data.account_value_history
      await nextTick()
      // 更新图表显示
      updateAccountChart(data.account_value_history, portfolio.value.totalValue, false)
    }
  } catch (error) {
    console.error('[TradingApp] Error loading portfolio:', error)
    errors.value.portfolio = error.message
  } finally {
    loading.value.portfolio = false
  }
}
```

### 3. 前端图表渲染

#### 单模型图表（当前模型）
```javascript
// 位置: frontend/src/composables/useTradingApp.js:862-960
const updateAccountChart = (history, currentValue, isMultiModel = false) => {
  // ...
  
  if (!isMultiModel) {
    // 单模型图表
    // 后端已返回UTC+8时区的ISO格式字符串，直接解析并格式化显示
    const data = history.reverse().map(h => {
      const date = new Date(h.timestamp)  // 解析ISO格式字符串
      let timeStr = ''
      if (isNaN(date.getTime())) {
        timeStr = h.timestamp || ''
      } else {
        // 格式化为本地时间显示（后端已经是UTC+8，所以直接显示即可）
        timeStr = date.toLocaleTimeString('zh-CN', {
          hour: '2-digit',
          minute: '2-digit'
        })
      }
      return {
        time: timeStr,
        value: h.balance || h.total_value || 0  // 使用balance字段作为图表值
      }
    })
    
    // 如果存在当前值，添加到图表末尾
    if (currentValue !== undefined && currentValue !== null) {
      const now = new Date()
      const currentTime = now.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit'
      })
      data.push({
        time: currentTime,
        value: currentValue
      })
    }
    
    // 使用ECharts渲染图表
    accountChart.value.setOption({
      xAxis: {
        type: 'category',
        data: data.map(d => d.time)  // 时间轴
      },
      yAxis: {
        type: 'value',
        formatter: (value) => `$${value.toLocaleString()}`
      },
      series: [{
        type: 'line',
        data: data.map(d => d.value),  // 账户价值数据
        smooth: true,
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(51, 112, 255, 0.2)' },
              { offset: 1, color: 'rgba(51, 112, 255, 0)' }
            ]
          }
        }
      }]
    })
  }
}
```

---

## 🔍 完整数据流图

```
┌─────────────────────────────────────────────────────────────┐
│ 交易周期执行 (execute_buy_cycle / execute_sell_cycle)      │
└────────────────────┬──────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ _record_account_snapshot(current_prices)                    │
│                                                             │
│ 1. db.get_portfolio(model_id, current_prices)              │
│    └─> 计算 total_value, cash, positions_value             │
│                                                             │
│ 2. db.get_model(model_id)                                  │
│    └─> 获取 account_alias                                   │
│                                                             │
│ 3. db.record_account_value(...)                            │
└────────────────────┬──────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ record_account_value()                                      │
│                                                             │
│ ┌─────────────────────────────────────┐                   │
│ │ account_values 表 (UPDATE/INSERT)    │                   │
│ │ - 每个model_id只有一条最新记录       │                   │
│ └─────────────────────────────────────┘                   │
│                                                             │
│ ┌─────────────────────────────────────┐                   │
│ │ account_value_historys 表 (INSERT)  │                   │
│ │ - 每次调用都插入新记录                │                   │
│ │ - timestamp: UTC+8时区               │                   │
│ └─────────────────────────────────────┘                   │
└────────────────────┬──────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 前端API请求                                                  │
│ GET /api/models/<model_id>/portfolio                        │
└────────────────────┬──────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ db.get_account_value_history(model_id, limit=100)          │
│                                                             │
│ SELECT * FROM account_value_historys                        │
│ WHERE model_id = ?                                          │
│ ORDER BY timestamp DESC                                     │
│ LIMIT 100                                                   │
└────────────────────┬──────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 数据格式转换                                                 │
│                                                             │
│ - 字段名转换为驼峰命名 (accountAlias, availableBalance)    │
│ - timestamp转换为ISO格式字符串 (UTC+8)                      │
└────────────────────┬──────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 前端接收数据                                                 │
│                                                             │
│ {                                                           │
│   portfolio: {...},                                         │
│   account_value_history: [                                 │
│     {                                                       │
│       id: "...",                                            │
│       model_id: "...",                                      │
│       accountAlias: "...",                                  │
│       balance: 10000.00,                                    │
│       availableBalance: 5000.00,                           │
│       crossWalletBalance: 5000.00,                         │
│       timestamp: "2024-01-01T12:00:00+08:00"               │
│     },                                                      │
│     ...                                                     │
│   ]                                                         │
│ }                                                           │
└────────────────────┬──────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ updateAccountChart(history, currentValue, false)            │
│                                                             │
│ 1. 解析timestamp为Date对象                                  │
│ 2. 格式化为时间字符串 (HH:mm)                               │
│ 3. 提取balance作为图表值                                    │
│ 4. 使用ECharts渲染折线图                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 关键特性

### 1. 数据保留策略
- **account_values表**：只保留最新的一条记录（UPDATE模式）
- **account_value_historys表**：保留所有历史记录（INSERT模式）

### 2. 时间处理
- **数据库存储**：UTC+8时区的datetime
- **API返回**：ISO格式字符串（如 `'2024-01-01T12:00:00+08:00'`）
- **前端显示**：解析ISO字符串后格式化为本地时间

### 3. 数据更新频率
- 每次买入周期结束时插入一条记录
- 每次卖出周期结束时插入一条记录
- 如果买入和卖出周期同时执行，可能在同一时间点插入多条记录

### 4. 数据查询限制
- 默认查询最近100条记录（`limit=100`）
- 按时间降序排序（`ORDER BY timestamp DESC`）
- 前端图表显示时按时间升序排列（`history.reverse()`）

---

## 🎯 使用场景总结

### 场景1：查看单个模型的资金走势
1. 用户在前端选择某个模型
2. 前端调用 `/api/models/<model_id>/portfolio`
3. 后端返回该模型的账户价值历史数据（最近100条）
4. 前端使用ECharts渲染折线图，展示资金走势

### 场景2：对比多个模型的资金走势
1. 用户切换到聚合视图
2. 前端调用 `/api/models/aggregated/portfolio`
3. 后端返回所有模型的账户价值历史数据
4. 前端使用ECharts渲染多线图表，对比不同模型的资金走势

### 场景3：实时更新资金走势
1. 交易周期执行完成后，自动插入新的账户价值记录
2. 前端定时刷新（或用户手动刷新）获取最新数据
3. 图表自动更新，显示最新的资金走势

---

## 🔧 相关文件

- **数据插入**：
  - `trade/trading_engine.py` - `_record_account_snapshot()` 方法
  - `common/database_basic.py` - `record_account_value()` 方法

- **数据查询**：
  - `backend/app.py` - `/api/models/<model_id>/portfolio` 接口
  - `common/database_basic.py` - `get_account_value_history()` 方法

- **前端使用**：
  - `frontend/src/composables/useTradingApp.js` - `loadPortfolio()` 和 `updateAccountChart()` 方法
  - `frontend/src/services/api.js` - API调用封装

---

*最后更新: 2024年*

