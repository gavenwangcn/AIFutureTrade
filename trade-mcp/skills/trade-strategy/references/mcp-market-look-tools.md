# trade_look_* 工具参数与顺序（参考）

本文件属于 **`trade-strategy` 技能**（`trade-mcp/skills/trade-strategy/`）。MCP 实现类：`trade-mcp/src/main/java/com/aifuturetrade/trademcp/tools/MarketLookTools.java`（路径相对 AIFutureTrade 仓库根目录）。

另可参考同目录树下的简表：`trade-mcp/skills/trade-mcp/references/market-look-tools.md`。

**若与运行中的 MCP 描述字面值冲突，以当前工具 schema 与后端报错为准**；后端对盯盘策略通常**强制要求 `validate_symbol`** 用于行情校验。

## 执行耗时（重要）

**创建盯盘策略**（`trade_look_strategy_create_look`）与 **修改/重新生成策略代码**（`trade_strategy_regenerate_code`，含 buy/sell/look）会触发后端大模型生成与多轮校验，**单次工具调用可能耗时数分钟，极端约 5 分钟**。使用前请向最终用户说明需耐心等待；避免在未返回结果前重复提交相同请求（除非已明确失败或超时后再试）。

## 调用顺序（硬性）

1. **`trade_look_strategy_create_look`** — 新建 `strategys`，`type` 固定为 **look**。  
2. 从成功响应中取出 **策略 `id`（UUID）**。  
3. **`trade_look_market_look_create`** — 新建 `market_look` 盯盘任务；**`strategy_id` 必须为上一步的策略 id**。

## `trade_look_strategy_create_look`

| 参数 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 策略名称 |
| `validate_symbol` | **业务必填** | 校验/测试用合约，如 `BTCUSDT`；后端对盯盘策略会校验；有 `strategy_code` 时必用其做行情试跑类校验 |
| `strategy_context` | 否 | 策略自然语言说明（建议创建时给出）；**撰写方式与生成代码所用 system Prompt 对齐**见同目录 `strategy-context-and-look-prompt.md` |
| `strategy_code` | 否 | Python 盯盘策略代码；若提供则需与 `validate_symbol` 等一致 |

成功响应通常含 **`id`**（策略 UUID）、`message` 等（以实际响应为准）。

## `trade_look_market_look_create`

| 参数 | 必填 | 说明 |
|------|------|------|
| `symbol` | 是 | 合约，如 `BTC` / `BTCUSDT` |
| `strategy_id` | 是 | **look 策略 UUID**（来自创建策略或查询） |
| `detail_summary` | 是 | 任务摘要，非空字符串 |
| `strategy_name` | 否 | 冗余展示名 |
| `execution_status` | 否 | `RUNNING` / `ENDED` 等；默认 `RUNNING` |
| `signal_result` | 否 | 文本或 JSON 字符串 |
| `started_at` / `ended_at` | 否 | 时间格式常见：`yyyy-MM-dd HH:mm:ss` 或 ISO-8601 |

成功响应含 **盯盘任务 `id`**（UUID）等（以实际响应为准）。

## `trade_look_market_look_delete`（删除盯盘任务）

按主键删除 `market_look` **一行**。与前端「盯盘详情」删除、后端 `DELETE /api/market-look/{id}` 一致。

| 参数 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | `market_look.id`（UUID） |

**成功判定（重要）**：响应中 **`success=true` 且 `verifiedAbsent=true`** 表示服务端已执行删除并**再次查询主键确认行已不存在**（不仅依赖 DELETE 返回值）。不存在任务时 `success=false`（常见 HTTP 404）；删除后仍能查到会为错误态。

**典型用途**：用户要求取消/清理某条盯盘任务、或模型在确认 id 后执行删除时使用；删除后该任务不再参与盯盘轮询。

## 查询类（创建后排查、列表）

| 工具 | 用途 |
|------|------|
| `trade_look_strategy_get_by_id` | 按策略 id 查策略（确认 `type=look`） |
| `trade_look_strategy_search_look` | 分页查 look 策略，`name` 可模糊 |
| `trade_look_market_look_get_by_id` | 按盯盘任务 id 查单条 |
| `trade_look_market_look_query_page` | 分页查任务，可按状态、symbol、`strategy_id`、时间范围 |
| `trade_look_market_look_sql` | 受控只读 SQL，**必须**出现表名 `market_look`，仅 `SELECT` |
| `trade_look_market_look_delete` | **删除**盯盘任务（必填 `id`）；成功以 `verifiedAbsent` 为准，见上节 |

## `trade_strategy_regenerate_code`（buy / sell / look 通用）

| 参数 | 必填 | 说明 |
|------|------|------|
| `strategyId` | 是 | `strategys.id` |
| `providerId` | 是 | AI 提供方 ID |
| `modelName` | 是 | 模型名 |
| `strategyContext` | 否 | 若提供则先更新语义再生成；省略则用库中现有正文（须非空） |
| `validateSymbol` | 否 | 盯盘时可选覆盖；省略用库中 |
| `strategyName` | 否 | 测试展示名 |
| `persist` | 否 | 默认 `true`；`false` 时只返回生成结果与测试，**不写库** |

**落库条件**：`persist!=false` **且** 代码测试通过（与新建策略校验一致）。未通过时响应含 `strategyCode`、`testPassed`、`testResult` 供排查。

## 后端 REST 参考（便于理解，非 MCP 直连）

- 盯盘任务：`/api/market-look`、分页、`GET/DELETE /api/market-look/{id}`（删除成功体含 `verifiedAbsent`）  
- 策略：`/api/strategies`、按 id、`POST /api/strategies/{id}/regenerate-code`、分页 `type=look`
