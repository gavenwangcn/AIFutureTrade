# 交易模型数据分析模块 - 胜率和盈亏比计算逻辑

## 概述

交易模型数据分析模块提供了两个维度的统计分析：
1. **按策略名称分组统计**（`getModelAnalysis`）：分析单个模型下不同策略的表现
2. **按模型分组统计**（`getAllModelsAnalysis`）：分析所有模型的整体表现

## 数据来源

- **主表**：`trades` 表（交易记录表）
- **关联表**：`strategy_decisions` 表（策略决策表，仅用于按策略分组统计）
- **关联表**：`models` 表（模型表，用于获取模型名称）

## 计算指标

### 1. 胜率（Win Rate）

**定义**：盈利交易占总交易的比例

**计算公式**：
```sql
win_rate = SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) / COUNT(t.id)
```

**说明**：
- 分子：`pnl > 0` 的交易数量（盈利交易数）
- 分母：总交易数量
- 结果范围：0.0 - 1.0（例如：0.65 表示 65% 的胜率）
- 如果总交易数为0，则返回 `NULL`

**SQL实现**（TradeMapper.java:57-58）：
```sql
CASE 
    WHEN COUNT(DISTINCT t.id) = 0 THEN NULL 
    ELSE CAST(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) AS DECIMAL(10, 5)) / COUNT(DISTINCT t.id) 
END as win_rate
```

### 2. 盈亏比（Profit Loss Ratio）

**定义**：平均盈利与平均亏损的比值

**计算公式**：
```sql
profit_loss_ratio = ABS(平均盈利 / 平均亏损)
profit_loss_ratio = ABS(AVG(盈利交易的pnl) / AVG(亏损交易的pnl))
```

**说明**：
- 分子：平均盈利（所有盈利交易的pnl平均值）
- 分母：平均亏损（所有亏损交易的pnl平均值，为负数，需要取绝对值）
- 结果范围：> 0（例如：3.0 表示平均盈利是平均亏损的 3 倍，即 3:1）
- 如果亏损交易数为0或平均亏损为0，则返回 `NULL`（避免除零错误）

**SQL实现**（TradeMapper.java:67-72）：
```sql
CASE 
    WHEN SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) = 0 THEN NULL 
    WHEN AVG(CASE WHEN t.pnl < 0 THEN t.pnl ELSE NULL END) = 0 THEN NULL 
    ELSE ABS(AVG(CASE WHEN t.pnl > 0 THEN t.pnl ELSE NULL END) / 
         NULLIF(AVG(CASE WHEN t.pnl < 0 THEN t.pnl ELSE NULL END), 0)) 
END as profit_loss_ratio
```

**示例**：
- 平均盈利 = 300
- 平均亏损 = -100（取绝对值后为 100）
- 盈亏比 = ABS(300 / (-100)) = 300 / 100 = 3.0（即 3:1）

### 3. 其他相关指标

#### 平均盈利（Average Profit）
```sql
avg_profit = AVG(CASE WHEN t.pnl > 0 THEN t.pnl ELSE NULL END)
```
- 只计算盈利交易的pnl平均值
- 如果没有任何盈利交易，返回 `NULL`

#### 平均亏损（Average Loss）
```sql
avg_loss = AVG(CASE WHEN t.pnl < 0 THEN t.pnl ELSE NULL END)
```
- 只计算亏损交易的pnl平均值（结果为负数）
- 如果没有任何亏损交易，返回 `NULL`

## 统计口径

### 按策略名称分组统计（`selectStrategyAnalysisByModelId`）

**数据范围**：
- 关联 `strategy_decisions` 表和 `trades` 表
- 匹配条件：
  - `sd.model_id = t.model_id`
  - `sd.symbol = t.future`
  - `sd.signal = t.signal`
  - `ABS(TIMESTAMPDIFF(SECOND, sd.created_at, t.timestamp)) <= 300`（5分钟内）

**分组方式**：按 `strategy_name` 分组

**统计范围**：所有匹配的交易记录（不区分买入/卖出）

### 按模型分组统计（`selectAllModelsAnalysis`）

**数据范围**：
- 只统计 `trades.side = 'sell'` 的交易（卖出交易）
- 关联 `models` 表获取模型名称

**分组方式**：按 `model_id` 分组

**统计范围**：只统计卖出类型的交易

**说明**：
- 只统计卖出交易是因为卖出交易才有实际的盈亏（pnl）
- 买入交易只是开仓，没有盈亏

## 代码位置

### 后端代码

1. **SQL查询定义**：
   - 文件：`backend/src/main/java/com/aifuturetrade/dao/mapper/TradeMapper.java`
   - 方法：
     - `selectStrategyAnalysisByModelId()`：按策略分组统计（第52-80行）
     - `selectAllModelsAnalysis()`：按模型分组统计（第94-120行）

2. **业务逻辑处理**：
   - 文件：`backend/src/main/java/com/aifuturetrade/service/impl/ModelServiceImpl.java`
   - 方法：
     - `getModelAnalysis()`：处理单个模型的分析数据（第2063-2139行）
     - `getAllModelsAnalysis()`：处理所有模型的分析数据（第2142-2221行）

3. **API接口**：
   - 文件：`backend/src/main/java/com/aifuturetrade/controller/ModelController.java`
   - 接口：
     - `GET /api/models/{modelId}/analysis`：获取单个模型的分析数据
     - `GET /api/models/analysis`：获取所有模型的分析数据

### 前端代码

1. **API调用**：
   - 文件：`frontend/src/services/api.js`
   - 方法：
     - `getModelAnalysis(modelId)`：获取单个模型分析
     - `getAllModelsAnalysis()`：获取所有模型分析

2. **UI展示**：
   - 文件：`frontend/src/components/ModelAnalysisModal.vue`
   - 组件：交易模型数据分析弹窗

## 计算示例

### 示例1：胜率计算

假设某个模型有以下交易记录：
- 交易1：pnl = 100（盈利）
- 交易2：pnl = -50（亏损）
- 交易3：pnl = 200（盈利）
- 交易4：pnl = -30（亏损）
- 交易5：pnl = 150（盈利）

**胜率计算**：
- 盈利交易数：3（交易1、3、5）
- 总交易数：5
- 胜率 = 3 / 5 = 0.6 = 60%

**盈亏比计算**：
- 平均盈利 = (100 + 200 + 150) / 3 = 450 / 3 = 150
- 平均亏损 = (-50 + (-30)) / 2 = -80 / 2 = -40（取绝对值后为 40）
- 盈亏比 = ABS(150 / (-40)) = 150 / 40 = 3.75（即 3.75:1）

### 示例2：边界情况

**情况1：全部盈利**
- 盈利交易数：5
- 亏损交易数：0
- 胜率 = 5 / 5 = 1.0 = 100%
- 平均盈利 = 所有盈利交易的平均值
- 平均亏损 = NULL（无亏损交易）
- 盈亏比 = NULL（平均亏损为NULL，避免除零错误）

**情况2：全部亏损**
- 盈利交易数：0
- 亏损交易数：5
- 胜率 = 0 / 5 = 0.0 = 0%
- 平均盈利 = NULL（无盈利交易）
- 平均亏损 = 所有亏损交易的平均值
- 盈亏比 = NULL（平均盈利为NULL）

**情况3：无交易记录**
- 总交易数：0
- 胜率 = NULL
- 盈亏比 = NULL

## 注意事项

1. **pnl字段的含义**：
   - `pnl > 0`：盈利交易
   - `pnl < 0`：亏损交易
   - `pnl = 0`：盈亏平衡（在统计中既不算盈利也不算亏损）

2. **按模型统计的特殊性**：
   - 只统计 `side = 'sell'` 的交易
   - 这是因为卖出交易才产生实际盈亏
   - 买入交易只是开仓，没有盈亏

3. **时间窗口匹配**：
   - 按策略统计时，使用5分钟时间窗口匹配策略决策和交易记录
   - 确保策略决策和实际交易能够正确关联

4. **NULL值处理**：
   - 前端需要处理 `NULL` 值，显示为 `--` 或 `N/A`
   - 避免在计算中出现除零错误

## 前端显示

前端在 `ModelAnalysisModal.vue` 中显示这些数据：
- 胜率：使用 `formatPercentage()` 格式化显示为百分比
- 盈亏比：使用 `formatNumber()` 格式化显示为小数（保留2位小数）
- 如果值为 `NULL`，显示为 `--`
