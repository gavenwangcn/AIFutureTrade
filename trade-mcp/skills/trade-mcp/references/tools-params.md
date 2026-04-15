# All tools: mcporter usage / MCP param names and types

## Forbidden (OpenClaw / scripts)

These yield **`error: Unknown tool`** with **`"tool": "trade"`** in JSON:

- `mcporter … call 'tradeMcp.trade_market_tickers_rows' …`
- `mcporter … call tradeMcp.trade_market_klines …`

These **omit explicit `--server` / `--tool`** — **do not** pass server and tool as bare positionals after `call`:

- `mcporter … call tradeMcp "trade_market_tickers_all_symbols" …`
- `mcporter … call tradeMcp 'trade_market_klines' …` (no `--tool` keyword)

**Required**: `mcporter --config ./mcporter-trade-mcp.json --log-level error call --server tradeMcp --tool 'trade_market_tickers_rows' …` (**`--tool` holds the full MCP name, no `tradeMcp.` prefix**; arguments follow `--tool`).

**Persisted scripts**: if you wrap multiple calls in a script, put it under **`<workspace>/trade/`** (create if missing), see **`../SKILL.md`**.

---

Param names match **`trade-mcp` source** (`MarketTools` / `MarketTickersTools` / `MarketLookTools` / `AccountTools` / `OrderTools`) and **`mcporter list tradeMcp --schema --json`**, all **camelCase**. 盯盘相关工具说明见 [market-look-tools.md](market-look-tools.md)。

**Invocation shell** (do not skip `--server` / `--tool`; avoid ambiguous bare positionals):

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool '<MCP tool name from table below>' \
  <key=value pairs> --output json
```

**Argument styles** (aligned with the top of [market.md](market.md)):

| Style | When |
|-------|------|
| `key=value` | Strings, numbers, booleans (`true`/`false`) |
| `key:value` / `key: value` | Equivalent depending on mcporter version |
| JSON array strings | `symbols='["BTCUSDT","ETHUSDT"]'`, `params='["BTCUSDT",50000]'` |
| Whole payload | `--args '{"symbol":"BTCUSDT","interval":"5m","limit":100}'` (keys as in tables below) |

---

## `trade_market_*` (no modelId)

| MCP tool name | Required | Optional | Types / notes |
|---------------|----------|----------|-----------------|
| `trade_market_symbol_prices` | `symbols` | — | **`symbols`**: `string[]`, mcporter: `symbols='["BTCUSDT","ETHUSDT"]'` |
| `trade_market_klines` | `symbol`, `interval` | `limit`, `startTime`, `endTime` | **`symbol`** string; **`interval`** string (e.g. `5m`); **`limit`** int; **`startTime`/`endTime`** long (ms) |
| `trade_market_klines_with_indicators` | `symbol`, `interval` | `limit`, `startTime`, `endTime` | Same as above |

---

## `trade_market_tickers_*` (no modelId)

| MCP tool name | Required | Optional | Types / notes |
|---------------|----------|----------|-----------------|
| `trade_market_tickers_rows` | — | `page`, `size`, `symbol`, `symbols`, `symbolsCsv`, `side`, `minLastPrice`, `maxLastPrice`, `minPriceChangePercent`, `maxPriceChangePercent`, `minQuoteVolume`, `maxQuoteVolume`, `orderBy`, `orderAsc` | **`page`** int (from 1); **`size`** int (≤500); **`symbol`** string; **`symbols`** string[]; **`symbolsCsv`** comma-separated; **`side`** `LONG`/`SHORT`; **`min*`/`max*`** double; **`orderBy`** enum string (see market.md); **`orderAsc`** boolean |
| `trade_market_tickers_rows_count` | — | Same filters as `rows` but **no** `page`/`size`/`orderBy`/`orderAsc` | Count only |
| `trade_market_tickers_snapshot` | — | `page`, `size`, `symbols`, `symbolsCsv` | Paging + optional symbol filter |
| `trade_market_tickers_snapshot_count` | — | `symbols`, `symbolsCsv` | No paging params |
| `trade_market_tickers_all_symbols` | — | — | **No arguments** |
| `trade_market_tickers_latest` | `symbol` | — | **`symbol`** string, e.g. `BTCUSDT` |
| `trade_market_tickers_sql` | `sql` | `params` | **`sql`**: read-only `SELECT`, must mention `24_market_tickers`; **`params`**: binds `?` left-to-right. **Strongly prefer** **`--args '{"sql":"...","params":[...]}'`** to avoid shell escaping; inline `sql=`/`params=` only if you know your shell |

---

## `trade_account_*` (modelId required)

| MCP tool name | Required | Optional |
|---------------|----------|----------|
| `trade_account_balance` | `modelId` | — |
| `trade_account_positions` | `modelId` | — |
| `trade_account_account_info` | `modelId` | — |

**Example**: `modelId=YOUR_MODEL_ID`

---

## `trade_order_*` (modelId required)

| MCP tool name | Required | Optional | Notes |
|---------------|----------|----------|-------|
| `trade_order_create` | `modelId`, `symbol`, `side`, `type`, `quantity` | `price`, `stopPrice`, `positionSide` | **`side`** `BUY`/`SELL`; **`type`** e.g. `MARKET`; **`quantity`** double; conditional orders need **`price`**/**`stopPrice`**; hedge mode needs **`positionSide`** `LONG`/`SHORT` |
| `trade_order_cancel` | `modelId`, `symbol` | `orderId`, `origClientOrderId` | At least one of **`orderId`** or **`origClientOrderId`** |
| `trade_order_get` | `modelId`, `symbol` | `orderId`, `origClientOrderId` | Same as above |
| `trade_order_open_orders` | `modelId` | `symbol` | **`symbol`** optional (backend-dependent “all symbols”) |
| `trade_order_sell_position` | `modelId`, `symbol` | — | **`symbol`** e.g. `BTCUSDT` |

---

## Common pitfalls

1. **Casing**: always **camelCase** (`startTime` not `start_time`, `orderBy` not `orderby`). Trust `list --schema`.
2. **No-arg tools**: do not pass junk keys like `page=1` to `trade_market_tickers_all_symbols` unless the schema says so.
3. **Arrays**: `symbols`, `params` need JSON array strings or `--args`.
4. **Longs**: `orderId` etc. as numbers; if coerced to float wrongly, try `--raw-strings` (see mcporter docs).

Authoritative source: **JSON Schema** from **`mcporter list tradeMcp --schema --json`**.
