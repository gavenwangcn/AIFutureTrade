# References · Market data (`trade_market_*` + `trade_market_tickers_*`)

For **mcporter** calling **trade-mcp**: quotes come from **binance-service**; rankings/ticker DB rows come from **backend** reading MySQL **`24_market_tickers`**.  
**Neither needs `modelId`** (unlike account/order tools).

**Before calling**: `mcporter list tradeMcp --schema --json` to verify tool names and param types; `tradeMcp` below is the server alias in config.

**Jump to SQL**: [§10 `trade_market_tickers_sql`](#10-trade_market_tickers_sql) — columns, `WHERE`, `params` + `?`, server allowlist.

**Full param list**: [tools-params.md](tools-params.md) (this file is semantics; that file is keys/types).

**Persisted scripts**: if an agent writes scripts orchestrating tools here (especially multi-step **`trade_market_tickers_sql`**), put them under **`<workspace>/trade/`** (create if missing), see **`../SKILL.md`**.

---

## mcporter conventions (this reference)

trade-mcp registers tools as **single snake_case identifiers** (e.g. `trade_market_klines`, `trade_market_tickers_rows`) **without `.`**. Do **not** use `call tradeMcp "…"` without **`--server` / `--tool`**. Use:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool '<full tool name>' \
  <key=value ...> --output json
```

- **Args**: `key=value`; arrays: `symbols='["A","B"]'`; or **`--args '{"page":1,"size":50}'`** (keys match schema).
- **Paging**: `trade_market_tickers_rows` uses **`page`** (from 1), **`size`** (≤500); for total rows use **`trade_market_tickers_rows_count`** with the **same filters** (**do not** pass `page`/`size`/`orderBy`).

---

## Common top-level fields

Most responses are JSON objects with:

| Field | Type | Meaning |
|-------|------|---------|
| `success` | boolean | Request ok |
| `data` | array / object | Payload; may be null on failure |
| `error` / `message` | string | Failure reason |

List endpoints may nest `records`, `total`, etc. inside `data` — see each tool.

---

## 1. `trade_market_symbol_prices`

**Purpose**: batch **last/mark** prices for multiple symbols (binance-service).

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `symbols` | yes | string[] | e.g. `["BTCUSDT","ETHUSDT"]` |

**mcporter example**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_market_symbol_prices' \
  symbols='["BTCUSDT","ETHUSDT"]' --output json
```

**`data`**: per-symbol price structures; field names follow backend/binance-service — use `list --schema` or one live call.

---

## 2. `trade_market_klines`

**Purpose**: OHLCV **K-lines** (no modelId).

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `symbol` | yes | string | e.g. `BTCUSDT` |
| `interval` | yes | string | `1m` / `5m` / `15m` / `1h` / `4h` / `1d`, … |
| `limit` | no | integer | default **499** |
| `startTime` | no | long | start **ms** |
| `endTime` | no | long | end **ms** |

**mcporter example**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_market_klines' \
  symbol=BTCUSDT interval=5m limit=100 --output json
```

**Each element in `data` (typical fields)**:

| Field | Meaning |
|-------|---------|
| `open_time` / `close_time` | Open/close time (ms) |
| `open_time_dt_str` / `close_time_dt_str` | Human-readable times if formatted |
| `open` / `high` / `low` / `close` | OHLC |
| `volume` | Base volume |
| `quote_asset_volume` | Quote volume |
| `number_of_trades` | Trade count |
| `taker_buy_base_volume` | Taker buy base volume |

---

## 3. `trade_market_klines_with_indicators`

**Purpose**: K-lines plus **MA/EMA/RSI/MACD/KDJ/ATR/ADX/VOL/Supertrend** (aligned with Java `KlineIndicatorCalculator` and Python `trade/market/market_data.py`).

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `symbol` | yes | string | Symbol |
| `interval` | yes | string | Interval |
| `limit` | no | integer | default 499 |
| `startTime` / `endTime` | no | long | Window in ms |

**Semantics**:

- `data` is **oldest → newest**.
- **Whole-bar drop**: if **any** indicator is invalid on a bar, that bar is **omitted** (not field-stripped).
- You need ~**99** raw bars before a bar can have all indicators; with `limit=298` you may get ~**200** bars. **Increase `limit`** for longer history.

**`indicators` (per bar, nested object)**:

| Group | Keys | Meaning (short) |
|-------|------|-----------------|
| `ma` | `ma5`,`ma20`,`ma60`,`ma99` | SMA |
| `ema` | `ema5`,`ema20`,`ema30`,`ema60`,`ema99` | EMA |
| `rsi` | `rsi6`,`rsi9`,`rsi14` | RSI |
| `macd` | `dif`,`dea`,`bar` | MACD |
| `kdj` | `k`,`d`,`j` | KDJ |
| `atr` | `atr7`,`atr14`,`atr21` | ATR |
| `adx` | `adx14`,`+di14`,`-di14` | ADX/DMI |
| `vol` | `vol`,`buy_vol`,`sell_vol`,`mavol5`,`mavol10`,`mavol60` | Volume stats |
| `supertrend` | `line`,`trend` (1=bull, -1=bear),`upper`,`lower`,`atr_period` (10),`multiplier` (3) | Supertrend (TradingView `ta.supertrend`) |

Values are typically **up to 4 decimal places** (`trend` is integer ±1).

**mcporter example**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_market_klines_with_indicators' \
  symbol=BTCUSDT interval=5m limit=120 --output json
```

---

## 4. `trade_market_tickers_rows`

**Purpose**: paged **raw rows** from **`24_market_tickers`** (filters + sort).

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `page` | no | int | Page, starts **1** |
| `size` | no | int | Page size, max **500** |
| `symbol` | no | string | Single symbol |
| `symbols` | no | string[] | Multiple symbols |
| `symbolsCsv` | no | string | Comma-separated |
| `side` | no | string | `LONG` / `SHORT` |
| `minLastPrice` / `maxLastPrice` | no | double | Last price range |
| `minPriceChangePercent` / `maxPriceChangePercent` | no | double | 24h change % range |
| `minQuoteVolume` / `maxQuoteVolume` | no | double | Quote volume range |
| `orderBy` | no | string | `id`/`event_time`/`symbol`/`last_price`/`quote_volume`/`price_change_percent`/`base_volume`/`ingestion_time` |
| `orderAsc` | no | boolean | Ascending; default **false** |

**mcporter paging example** (page 1, 50 rows, sort by quote volume desc):

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_market_tickers_rows' \
  page=1 size=50 orderBy=quote_volume orderAsc=false --output json
```

**Total count** (same filters as `rows`; **no** `page` / `size` / `orderBy`):

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_market_tickers_rows_count' \
  minQuoteVolume=1000000 --output json
```

**Aligned pattern** (do not fake `--tool` via quoted pseudo-functions):

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_market_tickers_rows' \
  page=1 size=20 orderBy=quote_volume orderAsc=false --output json
```

---

## 5. `trade_market_tickers_rows_count`

Same filters as **`rows`**, returns **total row count** for paging. No `page`/`size`/`orderBy`.

---

## 6. `trade_market_tickers_snapshot`

**Purpose**: **latest row per symbol** by `event_time`, paged.

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `page` / `size` | no | int | Paging |
| `symbols` / `symbolsCsv` | no | Limit symbols; omit for whole market (backend-dependent) |

**mcporter example**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_market_tickers_snapshot' \
  page=1 size=100 --output json
```

---

## 7. `trade_market_tickers_snapshot_count`

**Symbol group count** for the same filters as snapshot (implementation-defined).

---

## 8. `trade_market_tickers_all_symbols`

**Purpose**: **distinct** symbols in the DB. **No parameters.**

---

## 9. `trade_market_tickers_latest`

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `symbol` | yes | string | e.g. `BTCUSDT` |

Returns the **latest** ticker row for that symbol.

---

## 10. `trade_market_tickers_sql`

**Purpose**: **read-only controlled `SELECT`** against MySQL **`24_market_tickers`**. Use for arbitrary columns, complex `WHERE`, `ORDER BY`, `LIMIT`, subqueries/aggregates (within allowlist). For simple paging/filters prefer **`trade_market_tickers_rows`**.

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `sql` | yes | string | Single **`SELECT`**; literal **`24_market_tickers`** must appear (backticks recommended: `` `24_market_tickers` ``) |
| `params` | no | array | Binds **`?`** left-to-right (prepared; no injection); omit if no placeholders |

### 10.1 vs `trade_market_tickers_rows`

| Capability | `trade_market_tickers_sql` | `trade_market_tickers_rows` |
|------------|---------------------------|----------------------------|
| Filtering | Hand-written `WHERE` | Fixed params: symbols, side, price/%/volume ranges, `orderBy`, … |
| Columns / aggregates | Any allowed `SELECT`, `COUNT`, `MAX`, … | Fixed row shape from backend |
| Risk | Bad SQL rejected server-side | Parameterized, harder to write illegal SQL |

### 10.2 Server allowlist (`MarketTickerSqlGuard`)

**Backend** rejects if:

- Only **`SELECT`** after trim; **length ≤ 20000**.
- **No multi-statements**: `;` with non-whitespace after it (e.g. two selects) → reject.
- Full SQL (lower-cased check) must contain **`24_market_tickers`**.
- **No comments**: `--`, `/*`.
- **Forbidden fragments** (non-exhaustive): `insert`, `update`, `delete`, `drop`, `truncate`, `alter`, `grant`, `revoke`, `merge`, `call`, `exec`, `execute`, `into outfile`, `information_schema`, `sleep(`, … — see `MarketTickerSqlGuard` in backend source.

### 10.3 Columns (`24_market_tickers`, snake_case)

Aligned with entity `MarketTickerDO`; use **DB column names** below in SQL.

| DB column | Logical type | Meaning |
|-----------|--------------|---------|
| `id` | BIGINT | PK, autoincrement |
| `event_time` | DATETIME | Market event time |
| `symbol` | VARCHAR | e.g. `BTCUSDT` |
| `price_change` | DOUBLE | Absolute price change |
| `price_change_percent` | DOUBLE | 24h change % (e.g. `2.5` = 2.5%) |
| `side` | VARCHAR | `LONG` / `SHORT` |
| `change_percent_text` | VARCHAR | Display string for change |
| `average_price` | DOUBLE | Average price |
| `last_price` | DOUBLE | Last price |
| `last_trade_volume` | DOUBLE | Last trade size |
| `open_price` | DOUBLE | Open |
| `high_price` | DOUBLE | High |
| `low_price` | DOUBLE | Low |
| `base_volume` | DOUBLE | Base volume |
| `quote_volume` | DOUBLE | 24h quote volume |
| `stats_open_time` | DATETIME | Stats window start |
| `stats_close_time` | DATETIME | Stats window end |
| `first_trade_id` | BIGINT | First trade id |
| `last_trade_id` | BIGINT | Last trade id |
| `trade_count` | BIGINT | Trade count |
| `ingestion_time` | DATETIME | Ingest time |
| `update_price_date` | DATETIME | Price update date |

**JSON**: datetimes often **ISO 8601 strings**; numbers as JSON numbers.

### 10.4 `WHERE` patterns

Use **column names from §10.3**; quote strings; **prefer `?` + `params`** for dynamic values.

| Need | Example fragment |
|------|------------------|
| One symbol | `` WHERE `symbol` = ? `` + `params: ["BTCUSDT"]` |
| Many symbols | `` WHERE `symbol` IN (?, ?) `` + `params: ["BTCUSDT","ETHUSDT"]` |
| Exclude side | `` WHERE `side` <> 'LONG' `` or `` WHERE `side` = ? `` + `params: ["SHORT"]` |
| Last price range | `` WHERE `last_price` BETWEEN ? AND ? `` + `params: [50000, 52000]` |
| Change % range | `` WHERE `price_change_percent` >= ? AND `price_change_percent` <= ? `` |
| Min quote vol | `` WHERE `quote_volume` > ? ORDER BY `quote_volume` DESC `` |
| Event time | `` WHERE `event_time` >= ? AND `event_time` < ? `` |
| Ingest time | same with `` `ingestion_time` `` |
| AND combo | `` WHERE `symbol` = ? AND `last_price` > ? AND `price_change_percent` > ? `` |
| OR combo | `` WHERE (`symbol` = ? OR `symbol` = ?) AND `quote_volume` > ? `` |

**Sort/limit**: `` ORDER BY `event_time` DESC ``, `` LIMIT 50 ``, etc., inside one allowed `SELECT`.

**Aggregate example**: `` SELECT `symbol`, COUNT(*) AS cnt FROM `24_market_tickers` WHERE `event_time` >= ? GROUP BY `symbol` HAVING cnt > ? `` — still must reference the table and avoid forbidden keywords.

### 10.5 `params` vs `?`

- 1st `?` → `params[0]`, 2nd → `params[1]`, …
- Example: `` SELECT * FROM `24_market_tickers` WHERE `symbol`=? AND `last_price`>? LIMIT ? `` → `params`: `["BTCUSDT", 60000, 20]`.

### 10.6 mcporter examples

**Preferred: `--args` JSON** (avoids shell escaping; **recommended for agents**):

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_market_tickers_sql' \
  --args '{"sql":"SELECT * FROM `24_market_tickers` LIMIT 1"}' --output json
```

**With placeholders**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_market_tickers_sql' \
  --args '{"sql":"SELECT symbol,last_price FROM `24_market_tickers` WHERE symbol=? LIMIT 20","params":["BTCUSDT"]}' \
  --output json
```

**Alternative: inline `sql=` / `params=`** (shell-dependent; error-prone):

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_market_tickers_sql' \
  sql="SELECT symbol,last_price,quote_volume,price_change_percent,event_time FROM \`24_market_tickers\` WHERE symbol=? ORDER BY event_time DESC LIMIT 20" \
  params='["BTCUSDT"]' --output json
```

**Multiple placeholders**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_market_tickers_sql' \
  sql="SELECT symbol,last_price,quote_volume FROM \`24_market_tickers\` WHERE symbol=? AND quote_volume>? ORDER BY quote_volume DESC LIMIT ?" \
  params='["BTCUSDT",1000000,10]' --output json
```

(You can also pass one JSON via **`--args`** for `sql`+`params`.)

---

## Row fields (`24_market_tickers` query results)

Same as **§10.3**. On failure, see `error` / `message` (includes allowlist rejection reasons).
