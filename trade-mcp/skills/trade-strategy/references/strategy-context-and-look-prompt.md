# 策略描述（strategy_context）与盯盘代码生成 Prompt 对齐说明

供 **单独使用 trade-strategy 技能的 Agent** 理解：后端如何用 **系统 Prompt + 用户正文** 生成 Python 盯盘代码，以及用户应如何**撰写策略自然语言**，使生成结果与真实运行环境一致、且可被审阅与修改。

---

## 1. 生成链路（真实环境，Java backend）

创建/更新盯盘策略并带 **AI 生成代码** 时，主库 **AIFutureTrade backend** 会：

1. 将 **`strategy_look_prompt.txt`**（资源路径见下）全文作为 **system** 消息：定义输出格式、禁止事项、`market_state` 语义、返回值与日志等。
2. 将用户/业务侧的策略说明放在 **user** 消息中，典型形式为：  
   `## 策略规则（strategy_context）` + 换行 + **正文**（即字段 `strategy_context` 对应的内容）。

因此：**策略正文不写进 Prompt 文件**，而是与「规范」分离；模型必须先读 system 里的硬约束，再按 user 里的规则写代码。

**仓库内完整 Prompt 文件路径（有仓库时）**：`backend/src/main/resources/prompts/strategy_look_prompt.txt`  
（买入/卖出分别对应 `strategy_buy_prompt.txt`、`strategy_sell_prompt.txt`，结构类似：规范在 system，业务在 user。）

---

## 2. System Prompt 对「生成代码」的核心要求（精简版）

以下内容是对 `strategy_look_prompt.txt` 的**语义压缩**，用于在无仓库时对齐预期；**以线上资源文件为准**。

| 类别 | 要求摘要 |
|------|----------|
| 数据来源 | **仅**使用入参 `symbol` 与 `market_state[symbol]`；**禁止**在策略代码里 HTTP/WS/自拉交易所/调独立行情服务。 |
| 可用字段 | `price`、24h 量/额、`previous_close_prices`、`indicators.timeframes` 各周期 K 线及**已预计算指标**；**勿依赖**全市场 `market_indicators`；盯盘路径**勿依赖** `source`。 |
| 目标行为 | 满足条件时 `signal: "notify"` 触发企微类通知；否则 **`return {}`**；勿用非 `notify` 的 signal 冒充通知。 |
| 输出形态 | 只输出**纯 Python**；第一行为 import；**禁止** Markdown 代码块包装。 |
| 返回类型 | `Dict[str, List[Dict]]`，key 为**大写基础符号**（与 `symbol` 一致）；value 为**列表**；方法内常用局部变量名 `decisions`，以 `return decisions` 结束。 |
| notify 载荷 | 列表元素含 `signal`, `symbol`(合约全称), `market_date`, `key_date`, `price`, `justification` 等；`market_date`/`key_date` 须可 `json.dumps`。 |
| 日志 | 分支与取数处大量使用 `self.log.info` / `warning` / `error`，禁止长时间静默。 |
| 空值 | 指标可能为 `None`，须用 `is None` / `is not None`，禁止单靠 `if x:`。 |
| 方法签名 | 严格 `execute_look_decision(self, symbol: str, market_state: Dict)`，禁止改参。 |

**模板基类**：`StrategyBaseLook`（`strategy_template_look.py`）。

---

## 3. 如何撰写 `strategy_context`，便于生成代码与真实环境匹配

策略正文应让模型**少歧义、可落地到 `market_state`**。建议包含：

1. **合约与周期**：明确盯盘品种（基础符号如 BTC）及用到的周期（如 1h、4h）；若多周期联合，写清**先后或同时**关系。  
2. **指标与阈值**：写出指标名（如 RSI14、MA20/MA60）及**比较关系**（上穿、下穿、大于、区间）。  
3. **「上一根收盘」语义**：若与「当前 K」区分，说明用 `previous_close_prices` 还是 K 线数组的第几根，减少索引错误。  
4. **缺数据时行为**：K 线不足、指标为 `None` 时，是**不发通知**还是降级逻辑——写一句即可。  
5. **通知文案**：期望 `justification` 或展示给用户的大意（便于填 `notify` 条目）。  
6. **明确禁止**：不要在正文里要求「策略里请求外部 API」「订阅 websocket」——与 system 冲突，生成器会违规范或需返工。

**弱描述 → 易出问题的例子**：「涨了就提醒」——未给周期、幅度、与谁比较。  
**较强描述**：「1h 周期 RSI14 从低于 30 上穿至高于 30 时 notify；若 1h K 线不足 15 根或 RSI 为 None 则不通知并视为条件不满足。」

---

## 4. 审阅/修改策略时的检查（生成代码 ↔ 用户意图）

在拿到生成代码后，对照本文第 2 节与 `look-execution-and-testing.md`：

- 是否**只读** `market_state`，无违规网络调用。  
- 返回结构是否为 **`{基础符号: [dict, ...]}`**，notify 是否为 **`signal: "notify"`**。  
- 用户描述的**每一条**可判定条件，是否在代码中有对应分支与日志。  
- 若用户想改行为，应**先改 `strategy_context` 的表述**（更清晰、可测试），再触发重新生成或手工改代码并保持与模板一致。

---

## 5. 与 MCP 创建策略字段的关系

通过 **`trade_look_strategy_create_look`** 创建盯盘策略时：

- **`name` / `validate_symbol` / `strategy_context`**：标准流程下**三者均必传**；**`validate_symbol`** 为**验证用合约 symbol**（如 `BTCUSDT`），与「获取代码」一致，用于行情校验与试跑。  
- **`strategy_context`**：对应上述用户侧策略正文（建议直接采用第 3 节写法）。  
- **`strategy_code`**：由服务端生成，勿在 MCP 参数中提交；生成结果须满足第 2 节；**`validate_symbol`** 须与试跑/校验用合约一致。  
- **多轮校准与修正（推荐）**：对已存在的策略，使用 **`trade_strategy_regenerate_code`**（`strategyId` + 可选**修订后的 `strategyContext`/`validateSymbol`**）；提供方与模型取自系统设置；可先 **`persist=false`** 查看 `strategyCode` 与 `testResult`，用户满意后再 **`persist=true`**。若对话后仍不满意，应**反复澄清规则并再次调用**，直至用户**确认定稿**或**明确放弃**（流程见 **`../SKILL.md` 第 7 节**）。详见 `mcp-market-look-tools.md`。

---

## 6. 相关文档

- 运行时结构与 mock：`look-execution-and-testing.md`  
- MCP 工具参数：`mcp-market-look-tools.md`  
- 主技能流程：`../SKILL.md`
