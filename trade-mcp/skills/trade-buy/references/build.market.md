# trade-buy · references: BUILD market (open when choosing tools/fields)

Use during **BUILD**: pick trade-mcp market/indicator tools and understand responses when writing the watch script.
This file lists the **minimum market surface for trade-buy**; full details live in `skills/trade-mcp/references/market.md` as needed.

## Prefer: `trade_market_klines_with_indicators`

Purpose: one call returns K-lines + RSI and other indicators so you do not reimplement indicators in script.

- **Tool name**: `trade_market_klines_with_indicators`
- **Typical args**: `symbol` (e.g. `ETHUSDT`), `interval` (e.g. `5m`), `limit` (suggest ≥ 150 so RSI/EMA stabilize)
- **Response notes**:
  - `data` is oldest → newest
  - If any indicator is invalid on a bar, the **whole bar is omitted** (not field-stripped)
  - RSI often at `indicators.rsi.rsi14` (verify in live responses)

For lighter OHLCV only, use `trade_market_klines` and compute RSI yourself.

## Lazy load: full fields / examples

When you need exact fields, `limit` behavior, or sample shapes, read:

- `skills/trade-mcp/references/market.md` sections for:
  - `trade_market_klines`
  - `trade_market_klines_with_indicators`
