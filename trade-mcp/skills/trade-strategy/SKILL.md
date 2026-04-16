---
name: trade-strategy
description: >-
  Guides models to create look (盯盘) strategies and market_look tasks using trade-mcp tools only:
  parameter validation, user confirmation before calls, ID handoff, post-create verification against
  real Python execution context, scenario-based testing with mock market_state, and clarification when
  rules are ambiguous. Iterates with the user until strategy rules are confirmed or the user abandons;
  uses trade_strategy_regenerate_code to revise strategy after calibration. After create/regenerate, the model
  must show the returned strategy_code to the user and judge (beyond test_passed) whether logic matches intent.
  Strategy create/update tool calls can take several minutes (often up to ~5 minutes); tell the user to wait
  and avoid duplicate retries until timeout or error. Use when the user asks to build/configure 盯盘策略、盯盘任务、
  market_look, validate_symbol, strategy_context, or trade_look_* / trade_strategy_*（含 `trade_strategy_delete`） MCP tools in AIFutureTrade,
  including deleting a market_look task via trade_look_market_look_delete.
---

# trade-strategy

本技能位于 **`trade-mcp/skills/trade-strategy/`**（`trade-mcp` 的 `skills` 目录下）。模型通过 **已配置的 trade-mcp** 调用 `trade_look_*` 工具；本技能只规定流程与约束。

## 执行耗时（必须告知用户）

涉及 **创建策略**、**修改策略（重新生成代码）** 的 MCP 工具调用（例如 **`trade_look_strategy_create_look`**、**`trade_strategy_regenerate_code`**）时，服务端通常要经历大模型生成代码、语法/继承/试跑类校验等步骤，**单次调用耗时可能较长（数分钟级别，极端情况下可达约 5 分钟）**。

- **须在调用前或调用伊始向用户说明**：请耐心等待，不要误以为卡死。
- **未完成前**：不要因无立即响应而重复发起相同创建/再生请求；若客户端或网关报超时，再按报错与用户确认是否重试。
- **盯盘任务创建**（`trade_look_market_look_create`）一般较快；慢的主要在策略侧生成与校验。

## 盯盘策略与任务（经 trade-mcp）

在协助用户**创建盯盘策略（`type=look`）与盯盘任务（`market_look`）**时，必须按下列流程执行。禁止用脱离 MCP 的「手写脚本」替代正式工具去创建或查询策略/任务（除非用户明确要求仅本地实验且与 MCP 无关）。

## 1. 先读工具约束，缺参则问用户

收到「为某某合约（symbol）建盯盘…」类指令时：

- **必读** MCP 工具说明与参数：`trade_look_strategy_create_look`、`trade_look_market_look_create`，以及查询类工具（见 `references/mcp-market-look-tools.md`）。若用户要**删除盯盘任务**，再必读 **`trade_look_market_look_delete`**（第 9 节）。
- **重点核对**：
  - **创建策略（`trade_look_strategy_create_look`）**  
    - **标准 / 推荐流程（要生成可执行盯盘策略代码）**：**`name`、`validate_symbol`、`strategy_context` 三者均为必传**。  
    - **`validate_symbol`**：**验证用合约 symbol**（如 `BTCUSDT`），与页面「获取代码」一致，用于行情校验与代码试跑；**缺则无法完成带 AI 生成的合法创建**。  
    - **不要**在 MCP 中提交 `strategy_code`（一律服务端生成）。  
    - **例外**：仅建**无 `strategy_context` 的占位空壳**时，可不传 `validate_symbol`（一般不推荐）。
  - **创建盯盘任务**：`symbol`、`strategy_id`、`detail_summary` 必填；`strategy_id` **必须是已存在的 look 策略 UUID**（通常来自上一步创建策略的返回值）。
- **若上下文缺少** symbol、策略名称、校验合约、策略自然语言规则、是否带代码、任务摘要、时间窗等：**主动向用户提问**，不要猜测关键业务参数。

## 2. 调用工具前必须让用户确认

在**第一次**调用 `trade_look_strategy_create_look` 或 `trade_look_market_look_create` 之前：

- 将**已整理好的参数**（建议用表格或列表）**完整回复给用户**，请用户明确确认后再调用。
- **依赖顺序**：先 **创建盯盘策略** → 从响应中取得 **策略 `id`** → 再 **创建盯盘任务** 并传入该 `strategy_id`。不得跳过策略创建（除非用户已提供有效策略 ID 且已通过 MCP 查询确认）。

## 3. 记住并回传 ID，并展示策略代码（必须）

- 调用 `trade_look_strategy_create_look` 成功后：在回复中**写明策略 `id`（UUID）**；若响应含 **`strategy_code`**（由服务端生成时必有），**必须把完整策略代码展示给用户**（可用代码块），不得只汇报 ID。
- 若响应含 **`test_passed` / `test_result`**：简要说明自动化测试结论；**模型仍须根据对话上下文独立判断**：生成代码是否在业务逻辑上真正满足用户要求（条件、周期、触发语义等）；若**不满足**，向用户说明差距，并修订 `strategy_context` 后使用 **`trade_strategy_regenerate_code`**（可先 `persist=false` 试跑）直至用户认可或放弃。
- 调用 `trade_look_market_look_create` 成功后：**写明返回的盯盘任务 `id`**（或响应中主键字段），便于用户后续查询、排查或**删除该盯盘任务**（见第 9 节）。
- 会话内后续步骤应能复述这些 ID，避免用户重复查找。

## 4. 创建策略后：核对代码是否满足意图（结合真实执行逻辑）

在已展示 **`strategy_code`** 的前提下（见第 3 节）：

- **生成侧对齐**：先读 `references/strategy-context-and-look-prompt.md`——其中说明 **Java 如何用 `strategy_look_prompt.txt`（system）+ 用户策略正文（user）** 生成代码，以及 **system Prompt 对代码的硬性约束摘要**、**如何撰写 strategy_context** 才能与运行环境一致。
- **运行侧对齐**：再结合 `references/look-execution-and-testing.md`（执行链路、`market_state`、返回值、mock 场景）。无完整仓库时依赖上述两篇即可审阅；有仓库时可对照源码与 `backend/.../strategy_look_prompt.txt` 全文。
- **主动审阅**：结合用户原始需求，判断代码是否实现预期分支；**用自然语言向用户说明**一致点与疑点，必要时**先澄清/修订 strategy_context 再重新生成**，不要仅因 `test_passed=true` 就默认业务正确。

## 5. 复杂策略：构造场景与模拟数据（思想实验或说明性示例）

对**多条件、多周期**类策略：

- 可基于已理解的 **`market_state` 结构**（单 symbol、含 `price`、`indicators.timeframes`、`previous_close_prices` 等）说明：在哪些**模拟行情/K 线/指标**组合下应触发 `notify`，哪些不应触发。
- **测试数据原则**：针对「用户规则中的每一种结果分支」至少给一个**具体数值示例**（symbol、价格、某周期 K 线片段、关键指标），说明预期输出（是否 notify、`justification` 要点）。
- 实际试跑以项目内 **`strategy_code_tester_look`** 与后端校验为准；模型侧以**可追溯的推理与示例**为主，避免编造与仓库不一致的 API。

## 6. 模糊则追问，并用示例与用户核对

当「自然语言策略」与「生成的代码」对应关系**不清晰**时：

- **主动询问用户**，对每一条规则或条件请用户确认是否为其真实意图。
- 可结合**假设的模拟数据**（见第 5 点）逐项问：「若出现 A，您是否期望通知？若出现 B 呢？」

## 7. 校准—修改—再确认循环（直至用户满意或明确放弃）

当已通过对话**审阅生成结果**（自然语言规则、`strategy_code`、测试结论等），发现**仍不符合用户真实需求**时，不得一次性结束；应进入**可重复**的闭环，直到满足终止条件。

### 7.1 循环内要做的事

1. **对齐缺口**：用用户能懂的话说明「当前策略/代码与你想实现的内容差在哪里」（规则、条件、周期、阈值、notify 语义等）。
2. **再次向用户确认**：基于完整上下文，请用户补充或修正策略规则与条件；必要时用第 5、6 节的**示例与追问**逐项对齐。
3. **更新策略内容（经 MCP）**：在用户同意修改方向后，对已存在策略：
   - 使用 **`trade_strategy_regenerate_code`**，传入 **`strategyId`** 与**修订后的 `strategyContext`**（与上一步用户确认的正文一致）；提供方与模型由系统设置决定，**无需** `providerId`/`modelName`。可先 **`persist=false`** 查看返回的 **`strategyCode`** 与 **`testResult`**，**向用户展示代码**并确认逻辑后再 **`persist=true`** 落库。详见 `references/mcp-market-look-tools.md`。
   - 若仅需改名称、校验合约等元数据而不重新生成代码，可按后端能力使用策略更新接口（以 MCP/后端暴露为准）；**仍以 MCP 工具为主**。
4. **再次请用户确认**：展示新摘要或关键片段，问用户是否认可；**不认可则回到步骤 1**，继续循环。

### 7.2 终止条件（必须二选一）

- **成功终止**：用户**明确确认**当前策略信息（及如有盯盘任务，任务参数也可接受）可以定稿；此后如需再建 `market_look`，仍遵守第 2 节「先确认再调用」。
- **放弃终止**：用户**明确说明**放弃本次策略构建、或放弃本次盯盘任务构建（例如「不做了」「先取消」）。此时**不再**为同一目标反复调用创建/再生工具；可提示用户日后用查询类工具查看已有数据。

### 7.3 禁止

- **不得**在用户未表态「确认」或「放弃」前，默认策略已合格并停止追问（除非会话已自然结束且用户已口头定稿）。
- **不得**用非 MCP 方式「偷偷」改库；修改策略内容与重新生成代码须通过 **`trade_strategy_regenerate_code`**；删除策略须通过 **`trade_strategy_delete`**（见第 10 节）等已提供的工具路径。

## 8. 仅用 MCP 做创建与查询

- **创建/查询盯盘策略与盯盘任务**：优先且重点使用 trade-mcp 提供的 **`trade_look_*`** 工具（创建、按 ID 查、分页查、受控 SQL 等）。
- **禁止**：为「代替 MCP」而随意生成独立脚本去直连数据库或 REST 创建策略/任务（除非用户明确授权且场景是离线维护，并说明与 MCP 无关）。
- 需要列表或排查时：使用 `trade_look_strategy_search_look`、`trade_look_market_look_query_page`、`trade_look_strategy_get_by_id`、`trade_look_market_look_get_by_id` 等。
- **修正已存在策略的代码/描述**：使用 **`trade_strategy_regenerate_code`**（见第 7 节闭环）。
- **删除策略行**：使用 **`trade_strategy_delete`**（见第 10 节）。

## 9. 盯盘任务删除（market_look）

当用户要**取消、清理某条盯盘任务**，或明确表示不再让该任务参与盯盘轮询时：

- **唯一推荐的 MCP 路径**：调用 **`trade_look_market_look_delete`**，参数 **`id`** 为 **`market_look` 表主键**（UUID），即创建任务成功时返回的盯盘任务 `id`；若未知，先用 **`trade_look_market_look_get_by_id`** / **`trade_look_market_look_query_page`** 查到正确 `id` 再删。
- **成功判定**：以响应 **`success=true` 且 `verifiedAbsent=true`** 为准（服务端删除后会再次按主键查询，确认行已不存在）。`id` 不存在时通常为失败（如 HTTP 404 映射到 `success=false`）；勿仅凭「调用了删除」就认为已清掉。
- **语义**：删除的是 **`market_look` 一行**，与后端 **`DELETE /api/market-look/{id}`**、前端盯盘详情删除一致；**不会**自动删除关联的 look 策略（`strategys`）。
- **字段级说明与注意事项**：见 `references/mcp-market-look-tools.md` 中 **`trade_look_market_look_delete`** 小节。

## 10. 策略删除（strategys）

当用户要**删除整条策略记录**（`strategys` 表，含 buy/sell/look）时：

- **MCP 路径**：**`trade_strategy_delete`**，参数 **`strategyId`** 为策略 UUID（与创建/查询返回的 `id` 一致）。
- **须用户明确确认**后再调用；删除**不可恢复**。
- **关联数据**：若仍存在引用该策略的记录（例如未清理的盯盘任务 **`market_look`**），删除可能失败；通常应先 **`trade_look_market_look_delete`** 等清理关联，再删策略。详见 `references/mcp-market-look-tools.md` 中 **`trade_strategy_delete`**。

## 快速检查清单

0. 若将调用创建策略或 `trade_strategy_regenerate_code`：**是否已提示可能需等待数分钟（约 5 分钟级）**？  
1. **`trade_look_strategy_create_look` 标准流程是否含 `name` + `validate_symbol`（验证合约 symbol *）+ `strategy_context` 三必传**？缺则问。  
2. 用户是否已确认即将提交的参数？  
3. 是否先策略后任务？`strategy_id` 是否已拿到？  
4. 返回的策略 **`id` 是否写清**？若响应含 **`strategy_code`**：**是否已向用户完整展示代码**并**对照用户需求做了逻辑审阅**（不仅依赖 `test_passed`）？  
5. `trade_strategy_regenerate_code` 返回后：**是否展示 `strategyCode`** 并请用户确认？  
6. 有代码时是否在执行语义上自洽？复杂时是否有场景级说明/追问？  
7. 若结果不满意，是否已进入第 7 节闭环，直至用户**确认**或**明确放弃**？  
8. 是否全程以 MCP 工具为主？  
9. 若用户要**删除盯盘任务**：是否已用 **`trade_look_market_look_delete`** 并以 **`verifiedAbsent`** 确认成功（第 9 节）？  
10. 若用户要**删除策略**：是否已确认且按需先清理 **`market_look`** 等关联，再调 **`trade_strategy_delete`**（第 10 节）？

更多字段级说明见：`references/mcp-market-look-tools.md`。  
**策略正文与生成 Prompt（含 system/user 分工、撰写要点）**：`references/strategy-context-and-look-prompt.md`。  
**盯盘代码运行环境、契约、`market_state`、mock 与测试**：`references/look-execution-and-testing.md`。
