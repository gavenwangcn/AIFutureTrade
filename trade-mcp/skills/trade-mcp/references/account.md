# References · 账户信息（trade.account.*）

三类工具均通过 **trade-mcp → backend** 调用币安期货相关接口，**必须提供 `modelId`**（业务侧模型/账户路由标识）。

**调用前**：`mcporter list tradeMcp --schema --json` 核对参数名。

---

## 通用返回字段

| 字段 | 说明 |
|------|------|
| `success` | 是否成功 |
| `data` | 账户相关对象或列表 |
| `error` / `message` | 失败信息 |

下游 **backend** 路径（实现参考）：`/api/mcp/binance-futures/account/*`。

---

## 1. `trade.account.account_info`

**作用**：查询期货 **账户信息**（与 model 绑定）。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `modelId` | 是 | string | 模型 ID |

**mcporter 示例**：

```bash
mcporter --config ./mcporter-trade-mcp.json call tradeMcp.trade.account.account_info \
  modelId=YOUR_MODEL_ID --output json
```

**`data`（典型，以实际 API 为准）**：可能包含 **账户权限、手续费档位、多资产模式** 等币安期货账户维度字段；具体键名以后端返回 JSON 为准。处理建议：

- 先判断 `success === true`；
- 将 `data` 作为 **不透明对象** 展示或按需取键；
- 若需稳定字段列表，请在 backend OpenAPI / 控制器文档中核对。

---

## 2. `trade.account.balance`

**作用**：查询期货 **余额**（全仓/逐仓、各资产等由后端映射）。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `modelId` | 是 | string | 模型 ID |

**mcporter 示例**：

```bash
mcporter --config ./mcporter-trade-mcp.json call tradeMcp.trade.account.balance \
  modelId=YOUR_MODEL_ID --output json
```

**`data`（常见语义，非强制键名）**：

| 可能字段 | 说明 |
|----------|------|
| 资产列表 / `assets` | 各币种余额、可用、钱包余额等 |
| 汇总字段 | 如总权益、未实现盈亏（以后端为准） |

**注意**：字段名与 Binance 官方 REST 字段可能经过 **backend 转义或裁剪**，以 **单次响应 JSON** 为准。

---

## 3. `trade.account.positions`

**作用**：查询期货 **持仓**。

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `modelId` | 是 | string | 模型 ID |

**mcporter 示例**：

```bash
mcporter --config ./mcporter-trade-mcp.json call tradeMcp.trade.account.positions \
  modelId=YOUR_MODEL_ID --output json
```

**`data`（常见为数组时）单条持仓可能含**：

| 常见语义字段 | 说明 |
|--------------|------|
| `symbol` | 交易对 |
| `positionSide` / `side` | 多空方向（LONG/SHORT 或 BUY/SELL，依实现） |
| `positionAmt` / 数量类 | 持仓数量（正负表示方向） |
| `entryPrice` | 开仓均价 |
| `unRealizedProfit` | 未实现盈亏 |
| `leverage` | 杠杆 |
| `liquidationPrice` | 强平价（若有） |

实际键名以 **返回 JSON** 为准。

---

## 错误与重试

- **`modelId` 无效或缺失**：通常 `success: false`，`error` 含说明。
- **下游 backend 不可达**：连接错误，检查 trade-mcp 配置的 `downstream.backend.base-url` 与网络。
- **频率限制**：遵守 Binance 与内部网关规则；失败时退避重试。
