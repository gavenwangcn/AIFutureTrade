# References · 市场交易信息（trade.market.* + trade.market_tickers.*）

面向 **mcporter** 调用 **trade-mcp**：行情来自下游 **binance-service**；涨跌榜来自 **backend** 读 MySQL 表 **`24_market_tickers`**。  
**均不需要 `modelId`**（与账户/订单类工具区分）。

**调用前**：`mcporter list tradeMcp --schema --json` 核对工具名与参数类型；下文 `tradeMcp` 为配置中的 server 别名。

**快速跳转（SQL 查库表）**：[§10 `trade.market_tickers.sql`](#10-trademarket_tickerssql) — 可查字段、`WHERE` 写法、`params` 与 `?` 绑定、服务端白名单。

---

## 通用返回字段

多数响应为 JSON 对象，常见顶层键：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 请求是否成功 |
| `data` | array / object | 业务数据；失败时可能为 null |
| `error` / `message` | string | 失败原因（以实际响应为准） |

列表类接口常在 `data` 内再嵌 `records`、`total` 等，见各工具。

---

## 1. `trade.market.symbol_prices`

**作用**：批量查询多个合约的实时价格（来自 binance-service）。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `symbols` | 是 | string[] | 交易对列表，如 `["BTCUSDT","ETHUSDT"]` |

**mcporter 示例**（参数名以 schema 为准）：

```bash
mcporter --config ./mcporter-trade-mcp.json call tradeMcp.trade.market.symbol_prices \
  symbols='["BTCUSDT","ETHUSDT"]' --output json
```

**返回 `data`（典型）**：各 symbol 对应价格结构；字段名以后端/binance-service 序列化为准，常见含 **last / mark** 等，请以 `list --schema` 或一次实调为准。

---

## 2. `trade.market.klines`

**作用**：查询 K 线 OHLCV（不需要 modelId）。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `symbol` | 是 | string | 如 `BTCUSDT` |
| `interval` | 是 | string | `1m` / `5m` / `15m` / `1h` / `4h` / `1d` 等 |
| `limit` | 否 | integer | 条数，默认 **499** |
| `startTime` | 否 | long | 起始时间戳 **毫秒** |
| `endTime` | 否 | long | 结束时间戳 **毫秒** |

**mcporter 示例**：

```bash
mcporter --config ./mcporter-trade-mcp.json call tradeMcp.trade.market.klines \
  symbol=BTCUSDT interval=5m limit=100 --output json
```

**`data` 数组中单条 K 线（常见字段）**：

| 字段 | 说明 |
|------|------|
| `open_time` / `close_time` | 开盘/收盘时间（ms） |
| `open_time_dt_str` / `close_time_dt_str` | 可读时间（若服务已格式化） |
| `open` / `high` / `low` / `close` | OHLC |
| `volume` | 成交量 |
| `quote_asset_volume` | 计价成交额 |
| `number_of_trades` | 成交笔数 |
| `taker_buy_base_volume` | 主动买成交量 |

---

## 3. `trade.market.klines_with_indicators`

**作用**：在 K 线基础上附加 **MA/EMA/RSI/MACD/KDJ/ATR/ADX/VOL** 等指标（与 Java `KlineIndicatorCalculator` 对齐）。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `symbol` | 是 | string | 交易对 |
| `interval` | 是 | string | 周期 |
| `limit` | 否 | integer | 默认 499 |
| `startTime` / `endTime` | 否 | long | 毫秒时间窗 |

**语义要点**：

- `data` **按时间从旧到新**。
- **整根省略**：若某根上**任一**指标无法给出有效值，则**不返回该根**（不是删字段）。
- 至少需 **99 根**原始 K 线才可能从第 **99** 根起全部指标齐全；`limit=298` 时返回条数可能约为 **200**（298−98）。**需要更长历史请增大 limit**。

**`indicators`（每根上为嵌套对象，键名固定）**：

| 分组 | 键 | 含义（简要） |
|------|-----|----------------|
| `ma` | `ma5`,`ma20`,`ma60`,`ma99` | 简单移动平均 |
| `ema` | `ema5`,`ema20`,`ema30`,`ema60`,`ema99` | 指数移动平均 |
| `rsi` | `rsi6`,`rsi9`,`rsi14` | RSI |
| `macd` | `dif`,`dea`,`bar` | MACD |
| `kdj` | `k`,`d`,`j` | KDJ |
| `atr` | `atr7`,`atr14`,`atr21` | ATR |
| `adx` | `adx14`,`+di14`,`-di14` | ADX/DMI |
| `vol` | `vol`,`buy_vol`,`sell_vol`,`mavol5`,`mavol10`,`mavol60` | 量与均量 |

数值一般为 **最多 4 位小数**。

---

## 4. `trade.market_tickers.rows`

**作用**：分页查询 **`24_market_tickers`** 原始行（多条件筛选、排序）。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `page` | 否 | int | 页码，从 **1** 开始 |
| `size` | 否 | int | 每页条数，最大 **500** |
| `symbol` | 否 | string | 单个交易对 |
| `symbols` | 否 | string[] | 多个交易对 |
| `symbolsCsv` | 否 | string | 逗号分隔，如 `BTCUSDT,ETHUSDT` |
| `side` | 否 | string | `LONG` / `SHORT` |
| `minLastPrice` / `maxLastPrice` | 否 | double | 最新价区间 |
| `minPriceChangePercent` / `maxPriceChangePercent` | 否 | double | 24h 涨跌幅 % 区间 |
| `minQuoteVolume` / `maxQuoteVolume` | 否 | double | 计价成交额区间 |
| `orderBy` | 否 | string | 排序列：`id`/`event_time`/`symbol`/`last_price`/`quote_volume`/`price_change_percent`/`base_volume`/`ingestion_time` |
| `orderAsc` | 否 | boolean | 是否升序，默认 **false**（降序） |

---

## 5. `trade.market_tickers.rows_count`

与 **`rows`** 相同的筛选参数，返回满足条件的 **总行数**（用于分页总页数）。无 `page`/`size`/`orderBy`。

---

## 6. `trade.market_tickers.snapshot`

**作用**：每个 **symbol** 只保留 **最新一条**（按 `event_time`），分页。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `page` / `size` | 否 | int | 分页 |
| `symbols` / `symbolsCsv` | 否 | 限定交易对；不传可查全市场（视后端策略） |

---

## 7. `trade.market_tickers.snapshot_count`

与 **snapshot** 相同筛选下的 **symbol 分组总数**（或等价计数，以实现为准）。

---

## 8. `trade.market_tickers.all_symbols`

**作用**：库中 **distinct** 交易对列表。无参数。

---

## 9. `trade.market_tickers.latest`

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `symbol` | 是 | string | 如 `BTCUSDT` |

返回该 symbol **最新一条** ticker 行。

---

## 10. `trade.market_tickers.sql`

**作用**：对 MySQL 表 **`24_market_tickers`** 执行 **受控只读 `SELECT`**。适合需要 **任意列组合、复杂 `WHERE`、`ORDER BY`、`LIMIT`、子查询/聚合**（在允许语法内）的场景；简单分页筛选可改用 **`trade.market_tickers.rows`**（参数已封装区间与排序）。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `sql` | 是 | string | 单条 **`SELECT`**；字符串中必须出现字面量 **`24_market_tickers`**（建议表名加反引号：`` `24_market_tickers` ``） |
| `params` | 否 | array | 与 SQL 中 **`?`** 占位符 **从左到右** 依次绑定（预编译参数，防注入）；无占位符时可省略 |

### 10.1 与 `trade.market_tickers.rows` 的区别

| 能力 | `trade.market_tickers.sql` | `trade.market_tickers.rows` |
|------|---------------------------|------------------------------|
| 筛选方式 | 手写 `WHERE`，任意合法条件组合 | 固定参数：`symbol`/`symbols`/`side`、价与涨跌幅与成交额区间、`orderBy` 等 |
| 选列 / 聚合 | 可 `SELECT` 任意列、`COUNT`、`MAX` 等（仍须满足白名单） | 返回行结构由后端封装 |
| 风险 | 写错 SQL 会被服务端拒绝 | 参数化，不易写出非法 SQL |

### 10.2 服务端白名单（`MarketTickerSqlGuard`）

以下由 **backend** 校验，不满足则报错：

- 仅允许以 **`SELECT`** 开头（trim 后）；**长度 ≤ 20000** 字符。
- **禁止多语句**：出现 **`;`** 且其后还有非空白内容（例如 `SELECT ...; SELECT ...`）会被拒。
- SQL 全文（小写比较）必须包含 **`24_market_tickers`**。
- **禁止注释**：`--`、`/*`。
- **禁止关键字片段**（前后带空格匹配，节选）：`insert`、`update`、`delete`、`drop`、`truncate`、`alter`、`grant`、`revoke`、`merge`、`call`、`exec`、`execute`、`into outfile`、`information_schema`、`sleep(` 等（完整列表见源码 `MarketTickerSqlGuard`）。

### 10.3 可查字段一览（表 `24_market_tickers`，蛇形列名）

列名与实体 `MarketTickerDO` 一致，**SQL 中请使用下表「数据库列名」**（与 Java 字段的驼峰对应关系见 DO 注解）。

| 数据库列名 | 类型（逻辑） | 说明 |
|------------|--------------|------|
| `id` | BIGINT | 主键，自增 |
| `event_time` | DATETIME | 行情事件时间 |
| `symbol` | VARCHAR | 交易对，如 `BTCUSDT` |
| `price_change` | DOUBLE | 价格变动（绝对值） |
| `price_change_percent` | DOUBLE | 24h 涨跌幅（百分比数值，如 `2.5` 表示 2.5%） |
| `side` | VARCHAR | 方向：`LONG` / `SHORT` |
| `change_percent_text` | VARCHAR | 涨跌幅展示文案 |
| `average_price` | DOUBLE | 均价 |
| `last_price` | DOUBLE | 最新价 |
| `last_trade_volume` | DOUBLE | 最后一笔成交量 |
| `open_price` | DOUBLE | 开盘价 |
| `high_price` | DOUBLE | 最高价 |
| `low_price` | DOUBLE | 最低价 |
| `base_volume` | DOUBLE | 基础币成交量 |
| `quote_volume` | DOUBLE | 24h 计价成交额（USDT 等） |
| `stats_open_time` | DATETIME | 统计窗口开始 |
| `stats_close_time` | DATETIME | 统计窗口结束 |
| `first_trade_id` | BIGINT | 首笔成交 ID |
| `last_trade_id` | BIGINT | 末笔成交 ID |
| `trade_count` | BIGINT | 成交笔数 |
| `ingestion_time` | DATETIME | 数据写入库时间 |
| `update_price_date` | DATETIME | 价格更新日期 |

**结果序列化**：`datetime` 在 JSON 中常为 **ISO 8601 字符串**；数值列为数字。

### 10.4 `WHERE` 筛查写法（对应上表列名）

通用原则：**条件中的列名必须是上表之一**；字符串用单引号；**优先用 `?` + `params` 传动态值**，避免拼接用户输入。

| 需求 | 示例条件（片段） |
|------|------------------|
| 单交易对 | `` WHERE `symbol` = ? `` + `params: ["BTCUSDT"]` |
| 多个交易对 | `` WHERE `symbol` IN (?, ?) `` + `params: ["BTCUSDT","ETHUSDT"]` |
| 排除某 side | `` WHERE `side` <> 'LONG' `` 或 `` WHERE `side` = ? `` + `params: ["SHORT"]` |
| 最新价区间 | `` WHERE `last_price` BETWEEN ? AND ? `` + `params: [50000, 52000]` |
| 涨跌幅区间（%） | `` WHERE `price_change_percent` >= ? AND `price_change_percent` <= ? `` |
| 成交额下限 | `` WHERE `quote_volume` > ? ORDER BY `quote_volume` DESC `` |
| 时间范围（事件时间） | `` WHERE `event_time` >= ? AND `event_time` < ? ``（参数传驱动支持的 datetime 或字符串，与 JDBC 一致） |
| 入库时间 | 同上，列名换成 `` `ingestion_time` `` |
| 组合 AND | `` WHERE `symbol` = ? AND `last_price` > ? AND `price_change_percent` > ? `` |
| 组合 OR | `` WHERE (`symbol` = ? OR `symbol` = ?) AND `quote_volume` > ? ``（注意括号） |

**排序与截断**：`` ORDER BY `event_time` DESC ``、`` ORDER BY `quote_volume` DESC ``、`` LIMIT 50 `` 等均可写在合法单条 `SELECT` 内。

**聚合示例**（若业务需要）：`` SELECT `symbol`, COUNT(*) AS cnt FROM `24_market_tickers` WHERE `event_time` >= ? GROUP BY `symbol` HAVING cnt > ? `` — 仍须包含表名且不得触发禁止关键字。

### 10.5 `params` 与 `?` 的对应关系

- SQL 中第 **1** 个 `?` → `params[0]`，第 **2** 个 `?` → `params[1]`，依此类推。
- **示例**：`` SELECT * FROM `24_market_tickers` WHERE `symbol`=? AND `last_price`>? LIMIT ? ``  
  → `params` 应为 `["BTCUSDT", 60000, 20]`（类型与 JDBC 兼容：字符串、数值、整数）。

### 10.6 mcporter 示例

**单占位符**：

```bash
mcporter --config ./mcporter-trade-mcp.json call tradeMcp.trade.market_tickers.sql \
  sql="SELECT symbol,last_price,quote_volume,price_change_percent,event_time FROM \`24_market_tickers\` WHERE symbol=? ORDER BY event_time DESC LIMIT 20" \
  params='["BTCUSDT"]' --output json
```

**多占位符**（注意顺序与 `WHERE` 中 `?` 一致）：

```bash
mcporter --config ./mcporter-trade-mcp.json call tradeMcp.trade.market_tickers.sql \
  sql="SELECT symbol,last_price,quote_volume FROM \`24_market_tickers\` WHERE symbol=? AND quote_volume>? ORDER BY quote_volume DESC LIMIT ?" \
  params='["BTCUSDT",1000000,10]' --output json
```

（外层引号与转义以当前 shell 为准；若调用失败，改用 JSON 文件或 mcporter 文档中的 function-call 形式。）

---

## 行数据字段（`24_market_tickers` 查询结果）

单条行字段与 **§10.3** 表一致；失败时见响应中 `error` / `message`（含白名单拒绝原因）。
