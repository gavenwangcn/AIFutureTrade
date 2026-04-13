# trade-mcp · references index (progressive loading)

Read on demand; avoid loading every tool detail at once. Follow the decision tree below.

**Agent workspace**: any **persisted scripts** (mcporter wrappers, complex SQL, batch jobs) must live under **`<workspace>/trade/`** (create if missing). See the dedicated section in **`SKILL.md`**.

**mcporter calls**: **always** use **`mcporter --config ./mcporter-trade-mcp.json --log-level error call --server tradeMcp --tool '…full MCP tool name…'`**. **Do not** use `call tradeMcp "…"` without `--server`/`--tool`. Key=value pairs, JSON arrays, `--args`, and pagination are documented per file; **`market.md`** opens with shared conventions.

**Per-tool parameters (names / required / types)**: start with **[tools-params.md](tools-params.md)**, then open topic files as needed.

## Decision tree (open only what you need)

- **Quotes / K-lines / indicators**: open `market.md`
- **24h ticker table (`24_market_tickers`)**
  - Simple filters / paging: open `market.md` (`trade_market_tickers_rows`)
  - **Ad-hoc SQL**: open `market.md` section: [`trade_market_tickers_sql` (§10)](market.md#10-trade_market_tickers_sql)
- **Account balance / positions (needs modelId)**: open `account.md`
- **Place / cancel / query / close orders (high risk; needs modelId)**: open `orders.md`

## File list

| File | Contents |
|------|----------|
| **[tools-params.md](tools-params.md)** | **Full param list** (required/optional, camelCase, arrays and `params`) |
| [market.md](market.md) | `trade_market_*`, `trade_market_tickers_*` (includes SQL section) |
| [account.md](account.md) | `trade_account_*` (requires `modelId`) |
| [orders.md](orders.md) | `trade_order_*` (requires `modelId`; place/cancel/close) |
