# 盯盘 MCP 工具（trade-mcp → Java backend）

所有工具经 `BackendClient` 调用主库 **AIFutureTrade backend** REST，无需 `modelId`。

| 工具名 | 作用 | 必填参数 | 可选参数 |
|--------|------|----------|----------|
| `trade_look_market_look_create` | 新建 `market_look` | `symbol`, `strategy_id`, `detail_summary` | `strategy_name`, `execution_status`, `signal_result`, `started_at`, `ended_at` |
| `trade_look_strategy_create_look` | 新建 `type=look` 策略 | `name` | `validate_symbol`（有 `strategy_code` 时必填）, `strategy_context`, `strategy_code` |
| `trade_look_strategy_get_by_id` | 按 ID 查策略 | `strategyId` | — |
| `trade_look_strategy_search_look` | 盯盘策略分页（固定 `type=look`） | — | `pageNum`, `pageSize`, `name`（模糊） |
| `trade_look_market_look_query_page` | 分页查盯盘任务 | — | `pageNum`, `pageSize`, `execution_status`, `symbol`, `strategy_id`, `started_at_from/to`, `ended_at_from/to` |
| `trade_look_market_look_get_by_id` | 按 ID 查盯盘任务 | `marketLookId` | — |
| `trade_look_market_look_sql` | 受控只读 SQL | `sql` | `params`（与 `?` 对应） |

## 后端路径

- 盯盘：`/api/market-look`, `/api/market-look/page`, `/api/market-look/{id}`
- 策略：`/api/strategies`, `/api/strategies/{id}`, `/api/strategies/page?type=look&name=...`
- 受控 SQL：`POST /api/mcp/market-look/sql`，body：`{ "sql": "...", "params": [] }`

## 时间与状态格式

- `execution_status`：`RUNNING` | `SENDING` | `ENDED`
- 时间：推荐 `yyyy-MM-dd HH:mm:ss` 或 ISO-8601

## SQL 工具约束

- 仅 `SELECT`；必须出现表名 `market_look`；禁止多语句与注释；禁止写库关键字。
