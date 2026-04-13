# References · Account (`trade_account_*`)

All three tools call Binance Futures-related APIs via **trade-mcp → backend**. **`modelId` is required** (business routing id for model/account).

**Param names / required fields**: see the **`trade_account_*`** table in **[tools-params.md](tools-params.md)**.

**Before calling**: `mcporter list tradeMcp --schema --json` to verify param names.

**mcporter**: use **`--server tradeMcp --tool 'trade_account_…'`** (full names in this file or `list --schema`). Do not omit **`--tool`** or pass server+tool as bare positionals after `call`. Params: `modelId=...`.

---

## Common response fields

| Field | Meaning |
|-------|---------|
| `success` | Whether the call succeeded |
| `data` | Account object or list |
| `error` / `message` | Failure text |

Downstream **backend** paths (implementation reference): `/api/mcp/binance-futures/account/*`.

---

## 1. `trade_account_account_info`

**Purpose**: futures **account info** (bound to the model).

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `modelId` | yes | string | Model id |

**mcporter example**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_account_account_info' \
  modelId=YOUR_MODEL_ID --output json
```

**`data` (typical; trust live API)**: may include permissions, commission tier, multi-asset mode, etc. Handling:

- Check `success === true` first;
- Treat `data` as an **opaque object** or pick keys as needed;
- For a stable field list, check backend OpenAPI / controller docs.

---

## 2. `trade_account_balance`

**Purpose**: futures **balances** (cross/isolated mapping is backend-specific).

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `modelId` | yes | string | Model id |

**mcporter example**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_account_balance' \
  modelId=YOUR_MODEL_ID --output json
```

**`data` (semantic; keys not guaranteed)**:

| Possible field | Meaning |
|----------------|---------|
| Asset list / `assets` | Per-asset balance, available, wallet balance, etc. |
| Summary fields | Total equity, unrealized PnL (backend-dependent) |

**Note**: names may differ from raw Binance REST after **backend** mapping; trust each **response JSON**.

---

## 3. `trade_account_positions`

**Purpose**: futures **positions**.

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `modelId` | yes | string | Model id |

**mcporter example**:

```bash
mcporter --config ./mcporter-trade-mcp.json --log-level error call \
  --server tradeMcp --tool 'trade_account_positions' \
  modelId=YOUR_MODEL_ID --output json
```

**`data` (when a list)**: each position may include:

| Typical field | Meaning |
|---------------|---------|
| `symbol` | Symbol |
| `positionSide` / `side` | Long/short (LONG/SHORT or BUY/SELL per impl) |
| `positionAmt` / qty fields | Size (sign may encode side) |
| `entryPrice` | Entry price |
| `unRealizedProfit` | Unrealized PnL |
| `leverage` | Leverage |
| `liquidationPrice` | Liquidation price (if present) |

Actual keys: **returned JSON**.

---

## Errors and retries

- **Invalid or missing `modelId`**: often `success: false` with `error` text.
- **Backend unreachable**: connection errors — check trade-mcp `downstream.backend.base-url` and network.
- **Rate limits**: follow Binance and internal gateway rules; backoff and retry on failure.
