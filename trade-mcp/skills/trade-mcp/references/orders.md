# References · Trading and orders (`trade_order_*`)

Every tool **requires `modelId`**. Requests go **trade-mcp → backend** to persist or forward Binance Futures order APIs.

**Param names / required / one-of rules**: see **`trade_order_*`** in **[tools-params.md](tools-params.md)**.

**High risk**: `trade_order_create` and `trade_order_sell_position` place **real orders or close positions**. Call only with explicit user authorization; validate **symbol, size, side, type**.

**mcporter**: **`--server tradeMcp --tool 'trade_order_…'`** with the full MCP name (this file or `list --schema`). Do not omit **`--tool`** or use ambiguous bare positionals.

---

## Common response fields

| Field | Meaning |
|-------|---------|
| `success` | Whether the call succeeded |
| `data` | Order detail, list, or empty |
| `error` / `message` | Failure reason |

---

## 1. `trade_order_create`

**Purpose**: **create an order** (limit/market/conditional — depends on `type`).

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `modelId` | yes | string | Model id |
| `symbol` | yes | string | e.g. `BTCUSDT` |
| `side` | yes | string | **`BUY`** / **`SELL`** |
| `type` | yes | string | e.g. **`MARKET`**, `STOP`, `STOP_MARKET`, `TAKE_PROFIT`, `TAKE_PROFIT_MARKET`, … |
| `quantity` | yes | double | Size |
| `price` | no | double | Needed for limit-like types |
| `stopPrice` | no | double | Trigger for conditional orders |
| `positionSide` | no | string | **Hedge mode**: **`LONG`** / **`SHORT`** — required depending on type/account |

**mcporter example (market buy)**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_order_create' \
  modelId=YOUR_MODEL_ID symbol=BTCUSDT side=BUY type=MARKET quantity=0.001 --output json
```

**`data` (after success; Binance-like; backend is source of truth)**:

| Field | Meaning |
|-------|---------|
| `orderId` | Exchange order id |
| `clientOrderId` / `origClientOrderId` | Client order id if any |
| `symbol` | Symbol |
| `status` | Order status |
| `side` / `type` | Side and type |
| `price` / `avgPrice` | Order price / avg fill |
| `origQty` / `executedQty` | Ordered / filled qty |
| `updateTime` | Update time (ms) if present |

---

## 2. `trade_order_cancel`

**Purpose**: **cancel an order**.

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `modelId` | yes | string | Model id |
| `symbol` | yes | string | Symbol |
| `orderId` | one-of | long | System order id |
| `origClientOrderId` | one-of | string | Client order id |

Provide at least **`orderId`** or **`origClientOrderId`**.

**Example**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_order_cancel' \
  modelId=YOUR_MODEL_ID symbol=BTCUSDT orderId=123456789 --output json
```

**`data`**: often the canceled order or confirmation; trust live response.

---

## 3. `trade_order_get`

**Purpose**: **query a single order**.

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `modelId` | yes | string | Model id |
| `symbol` | yes | string | Symbol |
| `orderId` | one-of | long | System order id |
| `origClientOrderId` | one-of | string | Client order id |

**`data`**: same semantics as create response (full order detail).

---

## 4. `trade_order_open_orders`

**Purpose**: **open orders** (active working orders).

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `modelId` | yes | string | Model id |
| `symbol` | no | string | If omitted, may return **all symbols** (backend-dependent) |

**`data`**: usually an **array of orders**.

---

## 5. `trade_order_sell_position`

**Purpose**: **close position** (business wrapper; backend persists).

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `modelId` | yes | string | Model id |
| `symbol` | yes | string | `BTCUSDT` or shorthand allowed by backend (e.g. `BTC`) |

**Example**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_order_sell_position' \
  modelId=YOUR_MODEL_ID symbol=BTCUSDT --output json
```

**`data`**: may include close order id, fills, etc.; trust live response.

---

## Operational checklist (before the model acts)

1. `modelId` matches the user/strategy.  
2. `symbol` is USDS-M format (usually **`XXXUSDT`**).  
3. `quantity` meets **min qty** and **step** (exchange rules or internal config).  
4. Conditional orders include **`stopPrice`** (and **`price`** when required).  
5. In hedge mode, set **`positionSide`** when required.  
6. Parse **`success`** first, then **`data`** / **`error`**.
