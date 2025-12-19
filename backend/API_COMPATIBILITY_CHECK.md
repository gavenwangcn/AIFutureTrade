# Backend Controller 与 Frontend API 兼容性检查报告

## 检查时间
生成时间：基于当前代码库状态

## 1. Model API 接口对比

### ✅ 匹配的接口

| 前端调用 | Backend Controller | 状态 |
|---------|-------------------|------|
| `GET /api/models` | `GET /api/models` | ✅ 匹配 |
| `GET /api/models/{modelId}` | `GET /api/models/{modelId}` | ✅ 匹配 |
| `POST /api/models` | `POST /api/models` | ✅ 匹配 |
| `DELETE /api/models/{modelId}` | `DELETE /api/models/{modelId}` | ✅ 匹配 |
| `GET /api/models/{modelId}/portfolio` | `GET /api/models/{modelId}/portfolio` | ✅ 匹配 |
| `GET /api/models/{modelId}/trades?limit=10` | `GET /api/models/{modelId}/trades?limit=10` | ✅ 匹配 |
| `GET /api/models/{modelId}/conversations?limit=20` | `GET /api/models/{modelId}/conversations?limit=20` | ✅ 匹配（已修复） |
| `GET /api/models/{modelId}/prompts` | `GET /api/models/{modelId}/prompts` | ✅ 匹配 |
| `PUT /api/models/{modelId}/prompts` | `PUT /api/models/{modelId}/prompts` | ✅ 匹配 |
| `POST /api/models/{modelId}/execute` | `POST /api/models/{modelId}/execute` | ✅ 匹配 |
| `POST /api/models/{modelId}/execute-buy` | `POST /api/models/{modelId}/execute-buy` | ✅ 匹配 |
| `POST /api/models/{modelId}/execute-sell` | `POST /api/models/{modelId}/execute-sell` | ✅ 匹配 |
| `POST /api/models/{modelId}/disable-buy` | `POST /api/models/{modelId}/disable-buy` | ✅ 匹配 |
| `POST /api/models/{modelId}/disable-sell` | `POST /api/models/{modelId}/disable-sell` | ✅ 匹配 |
| `POST /api/models/{modelId}/auto-trading` | `POST /api/models/{modelId}/auto-trading` | ✅ 匹配 |
| `POST /api/models/{modelId}/leverage` | `POST /api/models/{modelId}/leverage` | ✅ 匹配 |
| `POST /api/models/{modelId}/max_positions` | `POST /api/models/{modelId}/max_positions` | ✅ 匹配 |
| `PUT /api/models/{modelId}/provider` | `PUT /api/models/{modelId}/provider` | ✅ 匹配 |
| `POST /api/models/{modelId}/batch-config` | `POST /api/models/{modelId}/batch-config` | ✅ 匹配 |
| `GET /api/models/{modelId}/portfolio/symbols` | `GET /api/models/{modelId}/portfolio/symbols` | ✅ 匹配 |

### ⚠️ 已修复的问题

1. **conversations 接口默认 limit 值不匹配** ✅ **已修复**
   - 前端默认：`limit = 20`
   - Backend 原默认：`limit = 5`
   - **修复**：Backend 默认值已改为 `limit = 20`，并移除了限制逻辑

2. **conversations 数据格式字段命名** ✅ **已修复**
   - 前端期望：`user_prompt`, `ai_response`, `cot_trace` (snake_case)
   - Backend 原返回：`userPrompt`, `aiResponse`, `cotTrace` (camelCase)
   - **修复**：Backend 现在同时返回两种格式，确保兼容性

### ✅ 聚合投资组合接口

| 前端调用 | Backend Controller | 状态 |
|---------|-------------------|------|
| `GET /api/aggregated/portfolio` | `GET /api/aggregated/portfolio` (AggregatedPortfolioController) | ✅ 匹配 |
| `GET /api/aggregated/portfolio` | `GET /api/models/aggregated/portfolio` (ModelController) | ✅ 双重路径支持 |

## 2. Market API 接口对比

### ✅ 匹配的接口

| 前端调用 | Backend Controller | 状态 |
|---------|-------------------|------|
| `GET /api/market/prices` | `GET /api/market/prices` | ✅ 匹配 |
| `GET /api/market/leaderboard/gainers?limit=10` | `GET /api/market/leaderboard/gainers?limit=10` | ✅ 匹配 |
| `GET /api/market/leaderboard/losers?limit=10` | `GET /api/market/leaderboard/losers?limit=10` | ✅ 匹配 |
| `GET /api/market/leaderboard?limit=10&force=1` | `GET /api/market/leaderboard?limit=10&force=0` | ✅ 匹配（已废弃但兼容） |
| `GET /api/market/klines?symbol=...&interval=...&limit=...&start_time=...&end_time=...` | `GET /api/market/klines?symbol=...&interval=...&limit=...&start_time=...&end_time=...` | ✅ 匹配（支持两种参数命名） |
| `GET /api/market/indicators/{symbol}` | `GET /api/market/indicators/{symbol}` | ✅ 匹配 |

## 3. Provider API 接口对比

### ✅ 匹配的接口

| 前端调用 | Backend Controller | 状态 |
|---------|-------------------|------|
| `GET /api/providers` | `GET /api/providers` | ✅ 匹配 |
| `POST /api/providers` | `POST /api/providers` | ✅ 匹配 |
| `DELETE /api/providers/{providerId}` | `DELETE /api/providers/{providerId}` | ✅ 匹配 |
| `POST /api/providers/models` | `POST /api/providers/models` | ✅ 匹配 |

## 4. Futures API 接口对比

### ✅ 匹配的接口

| 前端调用 | Backend Controller | 状态 |
|---------|-------------------|------|
| `GET /api/futures` | `GET /api/futures` | ✅ 匹配 |
| `POST /api/futures` | `POST /api/futures` | ✅ 匹配 |
| `DELETE /api/futures/{futureId}` | `DELETE /api/futures/{futureId}` | ✅ 匹配 |

### ℹ️ 额外接口

- Backend 还提供了 `GET /api/futures/symbols`，前端未使用（可选）

## 5. Settings API 接口对比

### ✅ 匹配的接口

| 前端调用 | Backend Controller | 状态 |
|---------|-------------------|------|
| `GET /api/settings` | `GET /api/settings` | ✅ 匹配 |
| `PUT /api/settings` | `PUT /api/settings` | ✅ 匹配 |

## 6. Account API 接口对比

### ✅ 匹配的接口

| 前端调用 | Backend Controller | 状态 |
|---------|-------------------|------|
| `GET /api/accounts` | `GET /api/accounts` | ✅ 匹配 |
| `POST /api/accounts` | `POST /api/accounts` | ✅ 匹配 |
| `DELETE /api/accounts/{accountAlias}` | `DELETE /api/accounts/{accountAlias}` | ✅ 匹配 |

## 7. Strategy API 接口对比

### ✅ 匹配的接口

| 前端调用 | Backend Controller | 状态 |
|---------|-------------------|------|
| `GET /api/strategies` | `GET /api/strategies` | ✅ 匹配 |
| `GET /api/strategies/{id}` | `GET /api/strategies/{id}` | ✅ 匹配 |
| `GET /api/strategies/search?name=...&type=...` | `GET /api/strategies/search?name=...&type=...` | ✅ 匹配 |
| `GET /api/strategies/page?pageNum=...&pageSize=...&name=...&type=...` | `GET /api/strategies/page?pageNum=...&pageSize=...&name=...&type=...` | ✅ 匹配 |
| `POST /api/strategies` | `POST /api/strategies` | ✅ 匹配 |
| `PUT /api/strategies/{id}` | `PUT /api/strategies/{id}` | ✅ 匹配 |
| `DELETE /api/strategies/{id}` | `DELETE /api/strategies/{id}` | ✅ 匹配 |

## 8. ModelStrategy API 接口对比

### ✅ 匹配的接口

| 前端调用 | Backend Controller | 状态 |
|---------|-------------------|------|
| `GET /api/model-strategies` | `GET /api/model-strategies` | ✅ 匹配 |
| `GET /api/model-strategies/{id}` | `GET /api/model-strategies/{id}` | ✅ 匹配 |
| `GET /api/model-strategies/model/{modelId}` | `GET /api/model-strategies/model/{modelId}` | ✅ 匹配 |
| `GET /api/model-strategies/model/{modelId}/type/{type}` | `GET /api/model-strategies/model/{modelId}/type/{type}` | ✅ 匹配 |
| `POST /api/model-strategies` | `POST /api/model-strategies` | ✅ 匹配 |
| `PUT /api/model-strategies/{id}/priority` | `PUT /api/model-strategies/{id}/priority` | ✅ 匹配 |
| `POST /api/model-strategies/model/{modelId}/type/{type}/batch` | `POST /api/model-strategies/model/{modelId}/type/{type}/batch` | ✅ 匹配 |
| `DELETE /api/model-strategies/{id}` | `DELETE /api/model-strategies/{type}` | ✅ 匹配 |

### ℹ️ 额外接口

- Backend 还提供了 `GET /api/model-strategies/strategy/{strategyId}` 和 `DELETE /api/model-strategies/model/{modelId}/strategy/{strategyId}/type/{type}`，前端未使用（可选）

## 数据格式检查

### ✅ Conversations 数据格式
- **字段命名**：Backend 同时返回 camelCase 和 snake_case 格式，确保前端兼容性
- **字段列表**：
  - `id`, `modelId`
  - `userPrompt` / `user_prompt`
  - `aiResponse` / `ai_response`
  - `cotTrace` / `cot_trace`
  - `conversationType` / `conversation_type`
  - `tokens`
  - `timestamp` (字符串格式：yyyy-MM-dd HH:mm:ss)

### ✅ Trades 数据格式
- **字段命名**：使用小写格式（symbol, signal, price, quantity, pnl等）
- **兼容字段**：同时提供 `future` 和 `symbol` 字段
- **字段列表**：
  - `id`, `modelId`
  - `future` / `symbol` (兼容字段)
  - `signal`, `price`, `quantity`, `pnl`, `message`, `status`
  - `timestamp` (字符串格式)
  - `current_price` (实时价格，如果有)

### ✅ Portfolio 数据格式
- **字段命名**：使用 camelCase 格式
- **字段列表**：
  - `portfolio`: { totalValue, cash, positionsValue, realizedPnl, unrealizedPnl, initialCapital, positions[] }
  - `accountValueHistory`: []
  - `autoBuyEnabled`, `autoSellEnabled`, `leverage`

### ModelDTO 格式
- 使用 camelCase 格式，与 Spring Boot 标准一致
- 前端通过 `...model` 展开操作可以访问所有字段

### 响应格式
- 大部分接口返回 `ResponseEntity<T>`，格式匹配
- 错误响应格式：`{ "success": false, "error": "..." }` 或 `{ "success": true, ... }`

## 总结

### ✅ 总体状态
- **接口路径匹配度**：100% ✅
- **HTTP 方法匹配度**：100% ✅
- **参数匹配度**：100% ✅
- **数据格式匹配度**：100% ✅（已修复字段命名兼容性问题）

### ✅ 已修复的问题

1. **ModelController.getConversations 默认 limit 值** ✅ **已修复**
   - 原值：`defaultValue = "5"`
   - 修复后：`defaultValue = "20"` 以匹配前端

2. **ModelServiceImpl.getConversations 字段格式** ✅ **已修复**
   - 原格式：仅 camelCase (`userPrompt`, `aiResponse`, `cotTrace`)
   - 修复后：同时提供 camelCase 和 snake_case 格式，确保前端兼容性

### 📝 建议

1. ✅ **已完成**：统一错误响应格式（大部分接口已统一）
2. ✅ **已完成**：字段命名兼容性（conversations 接口已同时提供两种格式）
3. ℹ️ **可选**：添加 API 文档（Swagger）确保接口规范清晰（已有 Swagger 配置）

### 🔍 数据格式兼容性说明

- **Conversations**：✅ 同时支持 camelCase 和 snake_case
- **Trades**：✅ 使用小写格式，兼容 `future` 和 `symbol` 字段
- **Portfolio**：✅ 使用 camelCase 格式
- **其他接口**：✅ 使用标准的 camelCase 或小写格式

