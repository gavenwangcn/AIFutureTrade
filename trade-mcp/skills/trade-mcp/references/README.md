# trade-mcp · references 索引（渐进式加载）

按需阅读，避免一次性加载全部工具细则。建议按下面“决策树”逐步打开。

**Agent 工作区**：凡需 **落盘脚本**（封装 mcporter、复杂 SQL、批处理），文件一律放在 **`<workspace>/trade/`**（无则新建）。见 **`SKILL.md`** 专节。

**mcporter 调用**：工具名含多个 `.`，请使用 **`call --server tradeMcp --tool '…完整 MCP 工具名…'`** 传参（键值对、数组 JSON、`--args`、分页等示例见各文件，**`market.md` 文首**有统一约定）。

**每个工具怎么传参（参数名 / 必填 / 类型）**：优先打开 **[tools-params.md](tools-params.md)**，再按需深入各专题文件。

## 决策树（只打开你需要的那个文件）

- **我要查行情 / K 线 / 指标**：打开 `market.md`
- **我要查 24h ticker 库表（`24_market_tickers`）**
  - 简单筛选/分页：打开 `market.md`（`trade.market_tickers.rows`）
  - **SQL 自由查询**：打开 `market.md` 的专章：[`trade.market_tickers.sql`（§10）](market.md#10-trademarket_tickerssql)
- **我要查账户余额/持仓（需要 modelId）**：打开 `account.md`
- **我要下单/撤单/查单/平仓（高风险，需要 modelId）**：打开 `orders.md`

## 文件清单

| 文件 | 内容 |
|------|------|
| **[tools-params.md](tools-params.md)** | **全工具参数清单**（必填/可选、camelCase、数组与 `params` 写法） |
| [market.md](market.md) | `trade.market.*`、`trade.market_tickers.*`（含 SQL 专章） |
| [account.md](account.md) | `trade.account.*`（须 `modelId`） |
| [orders.md](orders.md) | `trade.order.*`（须 `modelId`；下单/撤单/平仓） |
