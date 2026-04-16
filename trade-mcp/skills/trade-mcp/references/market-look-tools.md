# 盯盘 MCP 工具（trade-mcp → Java backend）

协作流程与参数确认等见技能 **`trade-mcp/skills/trade-strategy/SKILL.md`**（`references` 内有详细表）。

所有工具经 `BackendClient` 调用主库 **AIFutureTrade backend** REST，无需 `modelId`。

| 工具名 | 作用 | 必填参数 | 可选参数 |
|--------|------|----------|----------|
| `trade_look_market_look_create` | 新建 `market_look` | `symbol`, `strategy_id`, `detail_summary` | `strategy_name`, `execution_status`, `signal_result`, `started_at`, `ended_at` |
| `trade_look_strategy_create_look` | 新建 `type=look` 策略 | **标准：`name`、`validate_symbol`（验证合约 symbol *）、`strategy_context` 均必传** | 代码由服务端生成；成功响应含 `strategy_code` 等；仅无规则占位可不传后两项 |
| `trade_look_strategy_get_by_id` | 按 ID 查策略 | `strategyId` | — |
| `trade_look_strategy_search_look` | 盯盘策略分页（固定 `type=look`） | — | `pageNum`, `pageSize`, `name`（模糊） |
| `trade_look_market_look_query_page` | 分页查盯盘任务 | — | `pageNum`, `pageSize`, `execution_status`, `symbol`, `strategy_id`, `started_at_from/to`, `ended_at_from/to` |
| `trade_look_market_look_get_by_id` | 按 ID 查盯盘任务 | `marketLookId` | — |
| `trade_look_market_look_delete` | 按 ID 删除盯盘任务（服务端 DELETE 后再次查询确认行已不存在） | `id` | — |
| `trade_look_market_look_sql` | 受控只读 SQL | `sql` | `params`（与 `?` 对应） |

### 策略代码重新生成与删除（全类型）

| 工具名 | 作用 | 必填参数 | 可选参数 |
|--------|------|----------|----------|
| `trade_strategy_regenerate_code` | 按策略 ID 调用 AI **重新生成** `strategy_code`；测试通过后落库 | `strategyId` | `strategyContext`, `validateSymbol`（盯盘）, `strategyName`, `persist` |
| `trade_strategy_delete` | 按策略 ID **删除** `strategys` 一行（不可恢复） | `strategyId` | — |

- **HTTP**：`POST /api/strategies/{id}/regenerate-code`；提供方/模型来自系统设置，body **无需** `providerId`/`modelName`（camelCase，亦支持 `strategy_context` / `validate_symbol`）。
- **响应**：含 `strategyCode`、`testPassed`、`testResult`；模型应向用户展示代码并审阅业务逻辑。
- **`persist=false`**：只返回 `strategyCode` 与 `testResult`，不写库。
- **测试未通过**：不保存；响应仍含生成代码与 `testResult` 便于排查。

- **`POST /api/strategies`（创建）**：若服务端生成代码成功，响应含 `strategy_code`、`test_passed`、`test_result` 等（见 backend `StrategyController`）。
- **`DELETE /api/strategies/{id}`**：删除策略；MCP 工具 **`trade_strategy_delete`**。

## 后端路径

- 盯盘：`/api/market-look`, `/api/market-look/page`, `GET/DELETE /api/market-look/{id}`
- 策略：`/api/strategies`, `/api/strategies/{id}`, `POST /api/strategies/{id}/regenerate-code`, `/api/strategies/page?type=look&name=...`
- 受控 SQL：`POST /api/mcp/market-look/sql`，body：`{ "sql": "...", "params": [] }`

## 时间与状态格式

- `execution_status`：`RUNNING` | `SENDING` | `ENDED`
- 时间：推荐 `yyyy-MM-dd HH:mm:ss` 或 ISO-8601

## SQL 工具约束

- 仅 `SELECT`；必须出现表名 `market_look`；禁止多语句与注释；禁止写库关键字。
