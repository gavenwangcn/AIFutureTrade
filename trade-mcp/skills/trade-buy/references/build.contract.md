# trade-buy · references：BUILD contract（只在写脚本/改策略时打开）

本文件用于 **BUILD 阶段**：主 agent 生成/迭代盯盘脚本时，需要遵守的输入默认值、命中条件与输出协议。
RUN 阶段只负责执行，不应在 RUN 期间“重新设计”这些契约。

## 1) 默认值

- `symbol`: `ETHUSDT`
- `interval`: `5m`
- `poll_interval_seconds`: `10`
- `max_seconds`: `86400`（24h）
- `strategy`: 默认 `rsi_gt`
- `rsi_period`: `14`
- `rsi_threshold`: `70`

## 2) 命中条件（默认策略）

当最新一根（指标齐全的）K 线上：

- `RSI(rsi_period) > rsi_threshold`

则视为“买入信号”（仅做示例；真实买入与下单策略要单独授权与风控）。

## 3) 脚本输出协议（必须）

脚本在 **stdout** 输出若干日志行均可，但在**终止前必须输出且仅输出一次**以下任一 JSON 单行（便于 subagent 稳定解析）：

### 命中

```json
{"status":"signal","symbol":"ETHUSDT","interval":"5m","strategy":"rsi14_gt_70","timestamp_ms":1710000000000,"details":{"rsi14":72.3,"close":1850.12}}
```

### 超时

```json
{"status":"timeout","symbol":"ETHUSDT","interval":"5m","strategy":"rsi14_gt_70","timestamp_ms":1710000000000,"details":{"elapsed_seconds":86400}}
```

