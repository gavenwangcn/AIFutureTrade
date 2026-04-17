# trade_look_* 工具参数与顺序（参考）

本文件属于 **`trade-strategy` 技能**（`trade-mcp/skills/trade-strategy/`）。MCP 实现类：`trade-mcp/src/main/java/com/aifuturetrade/trademcp/tools/MarketLookTools.java`（路径相对 AIFutureTrade 仓库根目录）。

另可参考同目录树下的简表：`trade-mcp/skills/trade-mcp/references/market-look-tools.md`。

**若与运行中的 MCP 描述字面值冲突，以当前工具 schema 与后端报错为准**。  
**`validate_symbol`（验证合约 symbol）**：在**标准创建流程**（要提交 `strategy_context`、由服务端 AI 生成代码）下为**必传**，与「获取代码」一致用于行情校验与试跑。

## 执行耗时（重要）

**创建盯盘策略**（`trade_look_strategy_create_look`）与 **AI 重新生成策略代码**（`trade_strategy_regenerate_code`，含 buy/sell/look）会触发后端**大模型生成**与多轮校验，**单次工具调用可能耗时数分钟，极端约 5 分钟**。

**`trade_strategy_apply_submitted_code`**：**不经过大模型生成**；仅提交已有 `strategyCode` 并由服务端跑 Trade **完整测试**，通过才落库。仍可能因试跑等耗时，但通常**明显短于**上两类含 LLM 的调用。

以上路径使用前请向最终用户说明需等待；避免在未返回结果前重复提交相同请求（除非已明确失败或超时后再试）。

## 调用顺序（硬性）

1. **`trade_look_strategy_create_look`** — 新建 `strategys`，`type` 固定为 **look**。  
2. 从成功响应中取出 **策略 `id`（UUID）**；若本次由服务端生成代码，响应还含 **`strategy_code`**、**`test_passed`**、**`test_result`** 等——**模型须向用户展示完整 `strategy_code`** 并审阅是否满足业务需求（勿只回报 ID）。  
3. **`trade_look_market_look_create`** — 新建 `market_look` 盯盘任务；**`strategy_id` 必须为上一步的策略 id**。

## `trade_look_strategy_create_look`

| 参数 | 必填 | 说明 |
|------|------|------|
| `name` | **是** | 策略名称 |
| `validate_symbol` | **是**（标准流程） | **验证用合约 symbol**（如 `BTCUSDT`）。与前端「获取代码」一致，用于行情校验与策略代码试跑；**与 `strategy_context` 同时提交时缺一不可** |
| `strategy_context` | **是**（标准流程） | 策略自然语言说明；由服务端按**系统设置**中的策略 API 提供方/模型生成代码；**撰写要点**见 `strategy-context-and-look-prompt.md` |
| （勿传 `strategy_code`） | — | MCP 创建路径下代码一律服务端生成；勿在工具参数中传代码 |

**标准流程小结**：**`name` + `validate_symbol` + `strategy_context`** 三者为创建「可执行盯盘策略（含 AI 生成）」的**必传组合**。仅当故意建**无规则占位**（不传 `strategy_context`）时，可不传 `validate_symbol`（后端允许，但一般不推荐）。

**成功响应（HTTP 201）常见字段**：`id`、`message`；若已生成并保存代码，另有 **`strategy_code`**、**`strategy_context`**、**`test_passed`**、**`test_result`**。模型应对照用户意图审阅 `strategy_code`，并向用户完整展示代码。

## `trade_look_market_look_create`

| 参数 | 必填 | 说明 |
|------|------|------|
| `symbol` | 是 | 合约，如 `BTC` / `BTCUSDT` |
| `strategy_id` | 是 | **look 策略 UUID**（来自创建策略或查询） |
| `detail_summary` | 是 | 任务摘要，非空字符串 |
| `strategy_name` | 否 | 冗余展示名 |
| `execution_status` | 否 | `RUNNING` / `ENDED` 等；默认 `RUNNING` |
| `signal_result` | 否 | 文本或 JSON 字符串 |
| `ended_at` | 否 | 计划截止时间；**不传 `started_at`**（工具已不提供）：服务端 **开始时间=当前**；**不传 `ended_at` 且 RUNNING** 时，服务端 **结束时间=开始+24h**。格式：`yyyy-MM-dd HH:mm:ss` 或 ISO-8601 |

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
| `trade_look_container_logs` | 读取**固定盯盘 Docker 容器**（`aifuturetrade-model-look-1`）最近若干行日志；**唯一参数** `tail`（可选，默认 1000，最大 5000 由后端裁剪）。用于排查策略打印/异常，**不涉及** `market_state` 或策略 API |
| `trade_strategy_delete` | **删除策略**（必填 `strategyId`）；见下节「`trade_strategy_delete`」 |

## `trade_look_container_logs`（盯盘容器日志快照）

| 参数 | 必填 | 说明 |
|------|------|------|
| `tail` | 否 | 最近多少行；默认 **1000**，服务端上限 **5000** |

**说明**：始终读取容器 **`aifuturetrade-model-look-1`**，无容器名等其它入参。成功时响应含 `lines`（字符串行列表）、`lineCount` 等；需 backend 能访问 Docker。与「创建策略/任务」流程无关，供诊断用。

## `trade_strategy_regenerate_code`（buy / sell / look 通用）

| 参数 | 必填 | 说明 |
|------|------|------|
| `strategyId` | 是 | `strategys.id` |
| `strategyContext` | 否 | 若提供则先更新语义再生成；省略则用库中现有正文（须非空） |
| `validateSymbol` | 否 | 盯盘时可选覆盖；省略用库中 |
| `strategyName` | 否 | 测试展示名 |
| `persist` | 否 | 默认 `true`；`false` 时只返回生成结果与测试，**不写库** |

**提供方与模型**：取自系统设置「策略API提供方」，**无需** `providerId` / `modelName`。

**响应**：含 **`strategyCode`**、**`testPassed`**、**`testResult`** 等。模型须向用户**展示 `strategyCode`**，并判断逻辑是否满足需求。

**落库条件**：`persist!=false` **且** 代码测试通过（与新建策略校验一致）。未通过时仍返回生成代码与 `testResult` 供排查。

## `trade_strategy_apply_submitted_code`（buy / sell / look 通用，**非 AI 生成**）

**与 `trade_strategy_regenerate_code` 的本质区别**：本工具**不会**调用策略用大模型根据 `strategy_context` **生成**代码；只接受调用方传入的**完整** `strategyCode`，服务端再跑与新建/再生一致的 **Trade 测试执行**，**仅测试通过才更新库中的 `strategy_code`**。

| 参数 | 必填 | 说明 |
|------|------|------|
| `strategyId` | 是 | `strategys.id` |
| `strategyCode` | 是 | 待保存的完整 Python 策略源码（字符串） |
| `strategyName` | 否 | 测试展示名；省略用库中 `name` |
| `validateSymbol` | 否 | 仅 **type=look** 时需覆盖库中验证合约时传入；否则用库中 `validate_symbol` |

**响应（常用字段）**：`strategyCode`、`testPassed`、`testResult`、`persisted`（`true` 表示已写入库）、`message`。**`persisted=false`** 表示测试未通过或出错，**数据库中原策略代码不变**。

**后端 REST**：`POST /api/strategies/{id}/update-strategy-code`（请求体可含 `strategyCode` / `strategy_code` 等字段，与控制器约定一致）。

## `trade_strategy_delete`（buy / sell / look 通用）

| 参数 | 必填 | 说明 |
|------|------|------|
| `strategyId` | 是 | `strategys.id`（UUID） |

按主键删除 **`strategys`** 一行，对应 **`DELETE /api/strategies/{id}`**。成功时响应通常含 **`success=true`**。若仍存在引用该策略的数据（如未清理的 `market_look` 等），删除可能失败，需先处理关联或按错误信息排查。**不可恢复**，调用前应请用户确认。

## 后端 REST 参考（便于理解，非 MCP 直连）

- 盯盘任务：`/api/market-look`、分页、`GET/DELETE /api/market-look/{id}`（删除成功体含 `verifiedAbsent`）  
- 策略：`/api/strategies`、`DELETE /api/strategies/{id}`、按 id 查询、`POST /api/strategies/{id}/regenerate-code`、`POST /api/strategies/{id}/update-strategy-code`（直接提交代码+测试通过后保存）、分页 `type=look`
