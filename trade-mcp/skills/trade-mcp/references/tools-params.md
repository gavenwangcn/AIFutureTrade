# 全工具传参方式（mcporter / MCP 参数名与类型）

## 禁止（OpenClaw / 脚本易错）

以下写法会得到 **`error: Unknown tool`**，且 JSON 里 **`"tool": "trade"`**：

- `mcporter … call 'tradeMcp.trade.market_tickers.rows' …`
- `mcporter … call tradeMcp.trade.market.klines …`

**必须用**：`call --server tradeMcp --tool 'trade.market_tickers.rows'`（**`--tool` 里是完整 MCP 名，不含 `tradeMcp.` 前缀**）。

**落盘脚本目录**：若将多次调用封装为脚本，放在 **`<workspace>/trade/`**（无则新建），见 **`../SKILL.md`**。

---

以下参数名与 **`trade-mcp` 源码**（`MarketTools` / `MarketTickersTools` / `AccountTools` / `OrderTools`）及 **`mcporter list tradeMcp --schema --json`** 一致，均为 **camelCase**。

**统一调用外壳**（勿使用 `tradeMcp.trade.xxx` 连写）：

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool '<下表「MCP 工具名」列>' \
  <参数键值对> --output json
```

**传参形式**（与 [market.md](market.md) 文首约定一致）：

| 形式 | 适用 |
|------|------|
| `key=value` | 字符串、数字、布尔（`true`/`false`） |
| `key:value` / `key: value` | 与上等价（视 mcporter 版本） |
| JSON 数组字符串 | `symbols='["BTCUSDT","ETHUSDT"]'`、`params='["BTCUSDT",50000]'` |
| 整包参数 | `--args '{"symbol":"BTCUSDT","interval":"5m","limit":100}'`（键名同下表） |

---

## `trade.market.*`（不需要 modelId）

| MCP 工具名 | 必填 | 可选 | 类型说明 |
|------------|------|------|----------|
| `trade.market.symbol_prices` | `symbols` | — | **`symbols`**：`string[]`，mcporter：`symbols='["BTCUSDT","ETHUSDT"]'` |
| `trade.market.klines` | `symbol`, `interval` | `limit`, `startTime`, `endTime` | **`symbol`** string；**`interval`** string（如 `5m`）；**`limit`** int；**`startTime`/`endTime`** long（毫秒） |
| `trade.market.klines_with_indicators` | `symbol`, `interval` | `limit`, `startTime`, `endTime` | 同上 |

---

## `trade.market_tickers.*`（不需要 modelId）

| MCP 工具名 | 必填 | 可选 | 类型说明 |
|------------|------|------|----------|
| `trade.market_tickers.rows` | — | `page`, `size`, `symbol`, `symbols`, `symbolsCsv`, `side`, `minLastPrice`, `maxLastPrice`, `minPriceChangePercent`, `maxPriceChangePercent`, `minQuoteVolume`, `maxQuoteVolume`, `orderBy`, `orderAsc` | **`page`** int（从 1）；**`size`** int（≤500）；**`symbol`** string；**`symbols`** string[]；**`symbolsCsv`** string（逗号分隔）；**`side`** `LONG`/`SHORT`；**`min*`/`max*`** double；**`orderBy`** 枚举字符串见 market.md；**`orderAsc`** boolean |
| `trade.market_tickers.rows_count` | — | 与 `rows` 相同筛选字段，但 **无** `page`/`size`/`orderBy`/`orderAsc` | 仅用于计数 |
| `trade.market_tickers.snapshot` | — | `page`, `size`, `symbols`, `symbolsCsv` | 分页 + 可选限定交易对 |
| `trade.market_tickers.snapshot_count` | — | `symbols`, `symbolsCsv` | 无分页参数 |
| `trade.market_tickers.all_symbols` | — | — | **无参数**，不传任何 key |
| `trade.market_tickers.latest` | `symbol` | — | **`symbol`** string，如 `BTCUSDT` |
| `trade.market_tickers.sql` | `sql` | `params` | **`sql`** string（只读 `SELECT`，须含 `24_market_tickers`）；**`params`** 与 `?` 从左到右对应。**技能强制建议**：用 **`--args '{"sql":"...","params":[...]}'`** 传参，避免 shell 转义反引号/引号出错；仅在熟悉转义时用 `sql=`/`params=` 行内形式 |

---

## `trade.account.*`（必须 modelId）

| MCP 工具名 | 必填 | 可选 |
|------------|------|------|
| `trade.account.balance` | `modelId` | — |
| `trade.account.positions` | `modelId` | — |
| `trade.account.account_info` | `modelId` | — |

**示例**：`modelId=YOUR_MODEL_ID`

---

## `trade.order.*`（必须 modelId）

| MCP 工具名 | 必填 | 可选 | 说明 |
|------------|------|------|------|
| `trade.order.create` | `modelId`, `symbol`, `side`, `type`, `quantity` | `price`, `stopPrice`, `positionSide` | **`side`** `BUY`/`SELL`；**`type`** 如 `MARKET`；**`quantity`** double；条件单等按需带 **`price`**/**`stopPrice`**；双向持仓带 **`positionSide`** `LONG`/`SHORT` |
| `trade.order.cancel` | `modelId`, `symbol` | `orderId`, `origClientOrderId` | **`orderId`** long 与 **`origClientOrderId`** string **至少其一** |
| `trade.order.get` | `modelId`, `symbol` | `orderId`, `origClientOrderId` | 同上，至少其一 |
| `trade.order.open_orders` | `modelId` | `symbol` | **`symbol`** 可省略（全市场挂单视后端） |
| `trade.order.sell_position` | `modelId`, `symbol` | — | **`symbol`** 如 `BTCUSDT` |

---

## 易错点核对

1. **参数名大小写**：一律 **camelCase**（如 `startTime` 不是 `start_time`，`orderBy` 不是 `orderby`）。以 `list --schema` 为准。
2. **无参数工具**：`trade.market_tickers.all_symbols` 不要拼 `page=1` 等无效键（除非 schema 声明）。
3. **数组参数**：`symbols`、`params` 必须用 JSON 数组字符串或 `--args`。
4. **长整型**：`orderId` 等用数字；若被错误当成浮点，可试 `--raw-strings`（见 mcporter 文档）。

以 **`mcporter list tradeMcp --schema --json`** 输出的 **JSON Schema** 为最终权威。
