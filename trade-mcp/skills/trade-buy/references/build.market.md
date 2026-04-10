# trade-buy · references：BUILD market（只在写脚本选工具/字段时打开）

本文件用于 **BUILD 阶段**：写盯盘脚本时选择 trade-mcp 的行情/指标工具与理解返回结构。
本文件只放 **trade-buy 用到的最小行情能力**，完整细则请按需查看 `skills/trade-mcp/references/market.md`。

## 优先用：`trade.market.klines_with_indicators`

用途：一次调用拿到 K 线 + RSI 等指标，减少你在脚本里重复实现指标计算。

- **工具名**：`trade.market.klines_with_indicators`
- **典型参数**：`symbol`（如 `ETHUSDT`）、`interval`（如 `5m`）、`limit`（建议 ≥ 150，保证 RSI/EMA 等指标齐全）
- **返回要点**：
  - `data` 按时间从旧到新
  - 若某根任一指标无法给有效值，该根会被整体省略（不是删字段）
  - RSI 常见键：`indicators.rsi.rsi14`（具体以实际响应为准）

当你需要更轻量的 OHLCV，可用 `trade.market.klines`，但 RSI 需脚本自己算。

## 懒加载：查看完整字段/示例

当你需要更精确字段列表、limit 行为、示例返回结构时，再去读：

- `skills/trade-mcp/references/market.md` 中：
  - `trade.market.klines`
  - `trade.market.klines_with_indicators`

