# References · 交易与订单（trade.order.*）

所有工具 **必须传 `modelId`**；请求经 **trade-mcp → backend** 落库或转发币安期货下单接口。

**高风险**：`trade.order.create`、`trade.order.sell_position` 会产生 **真实委托或平仓**。模型应在用户明确授权后调用，并校验 **symbol、数量、方向、类型**。

---

## 通用返回字段

| 字段 | 说明 |
|------|------|
| `success` | 是否成功 |
| `data` | 订单详情、列表或空 |
| `error` / `message` | 失败原因 |

---

## 1. `trade.order.create`

**作用**：**创建订单**（限价/市价/条件单等，由 `type` 决定）。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `modelId` | 是 | string | 模型 ID |
| `symbol` | 是 | string | 交易对，如 `BTCUSDT` |
| `side` | 是 | string | **`BUY`** / **`SELL`** |
| `type` | 是 | string | 如 **`MARKET`** / `STOP` / `STOP_MARKET` / `TAKE_PROFIT` / `TAKE_PROFIT_MARKET` 等 |
| `quantity` | 是 | double | 数量 |
| `price` | 否 | double | **限价类**需要 |
| `stopPrice` | 否 | double | **条件单**触发价 |
| `positionSide` | 否 | string | **双向持仓**下 **`LONG`** / **`SHORT`**，必填与否依订单类型与账户模式 |

**mcporter 示例（市价买单）**：

```bash
mcporter --config ./mcporter-trade-mcp.json call tradeMcp.trade.order.create \
  modelId=YOUR_MODEL_ID symbol=BTCUSDT side=BUY type=MARKET quantity=0.001 --output json
```

**`data`（成功下单后常见字段，与币安订单响应类似，以后端为准）**：

| 字段 | 说明 |
|------|------|
| `orderId` | 系统订单号 |
| `clientOrderId` / `origClientOrderId` | 客户端订单 ID（若有） |
| `symbol` | 交易对 |
| `status` | 订单状态 |
| `side` / `type` | 买卖方向与类型 |
| `price` / `avgPrice` | 委托价 / 成交均价 |
| `origQty` / `executedQty` | 委托量 / 成交量 |
| `updateTime` | 更新时间戳（ms，若有） |

---

## 2. `trade.order.cancel`

**作用**：**撤销订单**。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `modelId` | 是 | string | 模型 ID |
| `symbol` | 是 | string | 交易对 |
| `orderId` | 二选一 | long | 系统订单 ID |
| `origClientOrderId` | 二选一 | string | 客户端订单 ID |

至少提供 **`orderId`** 或 **`origClientOrderId`** 之一。

**示例**：

```bash
mcporter --config ./mcporter-trade-mcp.json call tradeMcp.trade.order.cancel \
  modelId=YOUR_MODEL_ID symbol=BTCUSDT orderId=123456789 --output json
```

**`data`**：常为被取消订单的详情或确认信息；以实际响应为准。

---

## 3. `trade.order.get`

**作用**：**查询单笔订单**。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `modelId` | 是 | string | 模型 ID |
| `symbol` | 是 | string | 交易对 |
| `orderId` | 二选一 | long | 系统订单 ID |
| `origClientOrderId` | 二选一 | string | 客户端订单 ID |

**`data` 字段语义**：与「创建订单返回」类似（订单详情全量）。

---

## 4. `trade.order.open_orders`

**作用**：查询 **当前挂单**（未成交活跃委托）。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `modelId` | 是 | string | 模型 ID |
| `symbol` | 否 | string | 若省略，可能返回**全合约**挂单（以后端行为为准） |

**`data`**：一般为 **订单对象数组**。

---

## 5. `trade.order.sell_position`

**作用**：**一键平仓**（按业务封装，后端落库）。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `modelId` | 是 | string | 模型 ID |
| `symbol` | 是 | string | `BTCUSDT` 或业务允许的简写（如 `BTC`，以后端为准） |

**示例**：

```bash
mcporter --config ./mcporter-trade-mcp.json call tradeMcp.trade.order.sell_position \
  modelId=YOUR_MODEL_ID symbol=BTCUSDT --output json
```

**`data`**：可能含平仓订单号、成交情况等；以实际响应为准。

---

## 操作 checklist（建议模型执行前自检）

1. `modelId` 与当前用户/策略一致。  
2. `symbol` 为 USDS-M 合约格式（通常 **`XXXUSDT`**）。  
3. `quantity` 满足 **最小下单量** 与 **步长**（可先查交易所规则或内部配置）。  
4. 条件单必须带 **`stopPrice`**（及需要时的 **`price`**）。  
5. 双向持仓时确认 **`positionSide`**。  
6. 解析响应时先看 **`success`**，再读 **`data`** / **`error`**。
