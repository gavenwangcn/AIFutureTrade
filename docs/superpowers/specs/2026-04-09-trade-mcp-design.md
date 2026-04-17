# trade-mcp（MCP 服务）设计文档（方案 A：细粒度 Tools）

日期：2026-04-09  
作者：AI Coding Agent（与仓库协作）  

## 1. 背景与目标

本设计用于在现有工程 `AIFutureTrade` 中新增一个基于 Java/Spring Boot 的 MCP 服务：`trade-mcp`。  
`trade-mcp` 对外暴露 MCP tools（账号、交易、市场数据），对内**仅通过 HTTP 调用下游服务的 Controller REST 接口**获取/执行能力：

- **账号相关**、**交易相关**：调用 `backend` 服务（必须传入 `modelId`）
- **市场数据相关**：调用 `binance-service` 服务（不传 `modelId`）

关键约束：

- **所有对下游的调用都必须调用对方的 Controller REST 服务**（而不是直接调用对方 Service/DAO，也不是直接调用交易所 SDK）。
- **写操作（如创建订单）必须走原有的创建订单逻辑**：不仅是执行 SDK 下单，还需要对应数据落库/业务一致性（等价于“对应 model 执行相关操作”）。
- **K 线带指标**：技术指标在 **binance-service**（`GET /api/market-data/klines-with-indicators`）计算；`trade-mcp` 仅转发。Java 实现与 Python 侧（`trade/market/market_data.py` 等）逻辑对齐，尤其是 TradingView/Wilder 等边界处理。

## 2. 非目标（明确不做）

- 不在 `trade-mcp` 内保存/管理交易所 API Key/Secret（由 `backend` 基于 `modelId` 管理并使用）。
- 不在 `trade-mcp` 内直接对接 Binance SDK（所有写操作必须经由 `backend`；市场数据走 `binance-service`）。
- 不在本阶段引入消息队列、事件溯源等架构升级。

## 3. 总体架构

### 3.1 服务边界

- `trade-mcp`（新建）：MCP Server（WebMVC），对外提供 tools。
- `backend`（增强）：新增账号/交易相关 REST Controller + Service（MVC 三层），内部复用现有落库/下单逻辑（以 `modelId` 选择密钥/账户）。
- `binance-service`（增强/复用）：市场数据 REST Controller + Service（MVC 三层），提供 symbol 实时价格、K 线数据等。

### 3.2 数据流（核心链路）

1) **账号/交易（带 modelId）**  
`Agent -> MCP(tool: trade_account_* / trade_order_*) -> trade-mcp -> backend Controller -> backend Service -> (SDK/DB/原有逻辑) -> backend Controller -> trade-mcp -> Agent`

2) **市场数据（不带 modelId）**  
`Agent -> MCP(tool: trade_market_*) -> trade-mcp -> binance-service Controller -> binance-service Service -> Binance -> Controller -> trade-mcp`

3) **K 线 + 指标（不带 modelId）**  
`Agent -> MCP(tool: trade_market_klines_with_indicators) -> trade-mcp -> binance-service GET /klines-with-indicators(计算指标) -> trade-mcp -> Agent`

## 4. 下游 REST 契约（现状与补齐）

### 4.1 binance-service（现有接口）

已存在 `MarketDataController`：

- `POST /api/market-data/symbol-prices`（body：`List<String> symbols`）  
- `GET /api/market-data/klines?symbol=...&interval=...&limit=...&startTime=...&endTime=...`
- `GET /api/market-data/klines-with-indicators?...`（同参；指标在 binance-service 内计算）

说明：

- `trade-mcp` 的市场数据 tools 直接调用上述接口。
- 若后续发现字段不完整（例如 K 线缺少 `taker_buy_base_volume` 等），在 `binance-service` 侧按 MVC 方式补齐/增强，但 `trade-mcp` 永远只调用 Controller。

### 4.2 backend（需要新增接口）

现状：当前 `backend` 中可见的期货交易 REST 暴露较少（例如已有 `POST /api/binance-futures-order/sell-position`）。  
为了让 `trade-mcp` 能完整覆盖账号/下单/撤单/查单等能力，需要在 `backend` 新增一组“**面向 MCP 的交易所代理 Controller**”，并通过 Service 复用既有逻辑（含落库）。

约定：

- 统一前缀：`/api/mcp/binance-futures`（避免与现有 `/api/...` 冲突，且语义明确）
- 账号类路径：`/api/mcp/binance-futures/account/*`
- 交易类路径：`/api/mcp/binance-futures/order/*`
- **所有接口必须带 `modelId`**（`@RequestParam` 或 `@PathVariable` 统一一种即可；推荐 `@RequestParam modelId`，便于 MCP 透传）
- 返回体采用统一 envelope：`{ "success": boolean, "data": ..., "message": "...", "error": "..." }`

建议新增（最小闭环）接口清单（与 `trade-mcp` tools 1:1 对应）：

账号类（Account）

- `GET /api/mcp/binance-futures/account/balance?modelId=...`
- `GET /api/mcp/binance-futures/account/positions?modelId=...`
- `GET /api/mcp/binance-futures/account/account-info?modelId=...`
- （可选）`GET /api/mcp/binance-futures/account/income?modelId=...&startTime=...&endTime=...&limit=...`

交易类（Order）

- `POST /api/mcp/binance-futures/order/create`（body：创建订单参数 + `modelId`，或 `modelId` 作为 query）  
  - 必须走原落库/策略一致的下单流程
- `POST /api/mcp/binance-futures/order/cancel?modelId=...`（body：`{symbol, orderId}` 或 `{symbol, clientOrderId}`）
- `GET /api/mcp/binance-futures/order/get?modelId=...&symbol=...&orderId=...`
- `GET /api/mcp/binance-futures/order/open-orders?modelId=...&symbol=...`
- `POST /api/mcp/binance-futures/order/sell-position?modelId=...&symbol=...`（可直接复用现有 `sellPosition` 逻辑，或内部转发到已有 Service）

实现三层（MVC）建议：

- Controller：`com.aifuturetrade.controller.mcp.*`
- Service：`com.aifuturetrade.service.mcp.*`
- Client/Domain：复用现有 `com.aifuturetrade.common.api.binance.*`（如 `BinanceFuturesAccountClient`、`BinanceFuturesOrderClient`）与现有落库 Service/Mapper（以满足“写操作落库”）

> 注意：如果现有“创建订单”逻辑分散在 `ModelServiceImpl` / `AlgoOrderService` / 其他 Service 中，新增 `Mcp*Service` 的实现应当**调用原 Service 的公开方法**，而不是复制逻辑，避免落库口径不一致。

## 5. trade-mcp：MCP Tools 设计（方案 A：细粒度）

命名空间：统一以 `trade.*` 开头，按领域拆分为 `trade_account_*`、`trade_order_*`、`trade_market_*`。

### 5.1 Tools 清单（建议）

账号类（都必须带 `modelId`）

- `trade_account_balance(modelId)`
- `trade_account_positions(modelId)`
- `trade_account_account_info(modelId)`

交易类（都必须带 `modelId`）

- `trade_order_create(modelId, symbol, side, type, quantity, price?, timeInForce?, reduceOnly?, clientOrderId?, stopPrice?, workingType?, positionSide?, recvWindow?)`
- `trade_order_cancel(modelId, symbol, orderId?, origClientOrderId?)`
- `trade_order_get(modelId, symbol, orderId?, origClientOrderId?)`
- `trade_order_open_orders(modelId, symbol?)`
- `trade_order_sell_position(modelId, symbol)`（对齐现有一键平仓能力）

市场数据类（不带 `modelId`）

- `trade_market_symbol_prices(symbols[])`
- `trade_market_klines(symbol, interval, limit?, startTime?, endTime?)`
- `trade_market_klines_with_indicators(symbol, interval, limit?, startTime?, endTime?)`

### 5.2 Tools → 下游 REST 映射

- `trade_market_symbol_prices` → `binance-service` `POST /api/market-data/symbol-prices`
- `trade_market_klines` → `binance-service` `GET /api/market-data/klines`
- `trade_market_klines_with_indicators` → `binance-service` `GET /api/market-data/klines-with-indicators`（`trade-mcp` 仅转发）

- `trade_account_*` → `backend` 新增 `/api/mcp/binance-futures/account/*`
- `trade_order_*` → `backend` 新增 `/api/mcp/binance-futures/order/*`

## 6. K 线与指标：返回结构与对齐规则

### 6.1 原始 K 线字段（输入）

`trade-mcp` 从 `binance-service /klines` 获得的每根 K 线需至少包含：

- `openTime`（或 `open_time`）时间戳（毫秒）
- `open`/`high`/`low`/`close`（double）
- `volume`（double）
- `taker_buy_base_volume`（double，若缺失则视为 0）

> 若 `binance-service` 返回字段命名与 Python 不同，`trade-mcp` 会做一次字段归一化后再计算指标。

### 6.2 指标封装（输出）

`trade_market_klines_with_indicators` 返回每根 K 线附带：

```json
{
  "openTime": 1712345678901,
  "open": 0.0,
  "high": 0.0,
  "low": 0.0,
  "close": 0.0,
  "volume": 0.0,
  "taker_buy_base_volume": 0.0,
  "indicators": {
    "ma": {"ma5": null, "ma20": null, "ma60": null, "ma99": null},
    "ema": {"ema5": null, "ema20": null, "ema30": null, "ema60": null, "ema99": null},
    "rsi": {"rsi6": null, "rsi9": null, "rsi14": null},
    "macd": {"dif": null, "dea": null, "bar": null},
    "kdj": {"k": null, "d": null, "j": null},
    "atr": {"atr7": null, "atr14": null, "atr21": null},
    "vol": {"vol": 0.0, "buy_vol": 0.0, "sell_vol": 0.0, "mavol5": null, "mavol10": null, "mavol60": null}
  }
}
```

其中 “null 的起始索引规则”必须与 Python 侧一致（见 `trade/market/market_data.py::_calculate_indicators_for_klines`）：

- `ma5`：i>=4 才可用；`ma99`：i>=98
- `ema5`：i>=4；`ema99`：i>=98（注意：EMA 的初始化逻辑必须按前端/ Python 的 `_ema_frontend`）
- `rsi6`：i>=6；`rsi14`：i>=14（注意：RSI 用 TradingView/Wilder 平滑逻辑）
- `macd.*`：i>=25（注意：柱值 bar = (dif - dea) * 2，按 Python 的 `_macd_frontend`）
- `kdj`：readyIndex = (kPeriod-1)+(smoothK-1)+(smoothD-1)；默认 (9,3,3) ⇒ 12
- `atr7`：i>=6；`atr14`：i>=13；`atr21`：i>=20（注意：Wilder/RMA）
- `mavol5`：i>=4；`mavol60`：i>=59

### 6.3 Java 指标算法对齐（必须 1:1）

以下算法必须按 Python 实现迁移，避免使用“默认库实现”造成边界差异：

- **EMA**：使用 `market_data.py` 中 `_ema_frontend` 的初始化与递推规则  
  - i==0: EMA=close  
  - i<period-1: EMA=累计均值  
  - i==period-1: EMA=SMA(period)  
  - i>period-1: 递推 \(EMA = close * α + EMA_{prev} * (1-α)\), \(α = 2/(N+1)\)

- **RSI**：使用 `_calculate_rsi_tradingview`（Wilder’s smoothing，TradingView 逻辑）

- **MACD**：使用 `_macd_frontend`（与前端一致；bar 乘 2）

- **KDJ**：使用 `_calculate_kdj_tradingview`（raw_k 用 MIN/MAX；K 与 D 用 SMA；J=3K-2D）

- **ATR**：使用 `_calculate_atr_tradingview`（TR 三项 max；首个 ATR 用 SMA；后续用 RMA）

对齐验证策略：

- 在 `trade-mcp` 新增单测：读取一份固定 K 线 fixture（可从 `binance-service` 取样并落为 JSON），分别用 Java 实现算出指标，与 Python 运行结果（或仓库中已有期望值文件）对比，允许误差阈值（例如 `1e-8` 到 `1e-6`，按 double 计算误差设定）。

## 7. trade-mcp：实现分层（MVC 与适配）

虽然 MCP Server 的对外形态不是传统 REST Controller，但内部仍采用类似三层解耦：

- **Tool 层**：声明 MCP tool（输入 schema、输出 schema、错误映射）
- **Service 层**：编排调用下游 REST、指标计算、结果组装
- **Client 层**：封装 `backend` / `binance-service` 的 HTTP 调用（`RestClient` 或 `WebClient`），统一重试/超时/错误解析

## 8. 配置与运行

`trade-mcp` 需要以下配置项（`application.yml`）：

- `downstream.backend.base-url`（例如 `http://localhost:8080`）
- `downstream.binance-service.base-url`（例如 `http://localhost:8081`）
- 超时：connect/read timeout
- （可选）鉴权：若内网无需鉴权可先不加；若需要可用 shared token header

## 9. 错误处理与可观测性

- 统一错误 envelope：tool 返回 `{success:false, error:"...", message:"..."}` 或 MCP 推荐错误格式（实现时按所用 MCP 框架要求映射）
- 下游 HTTP 非 2xx：解析下游 body（若为 `{success:false}`）并透传 message
- 记录关键日志：tool 名、modelId（账号/交易）、symbol/interval/limit（市场数据）、下游耗时

## 10. 交付拆分（最小可用）

第一阶段（MVP）：

- `trade-mcp`：实现 `trade_market_symbol_prices`、`trade_market_klines_with_indicators`
- `backend`：新增 `account.balance/positions/account_info` 与 `order.create/cancel/get/open_orders/sell_position` 的 Controller + Service（先覆盖最常用）
- `binance-service`：复用现有市场接口；若字段不够则补齐

第二阶段：

- 扩展更多 account/order 能力（income、leverage、marginType、positionSide 等）
- 更完善的指标回归测试与性能优化

