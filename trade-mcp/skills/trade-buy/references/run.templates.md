# trade-buy · references：RUN templates（只在需要复制粘贴时打开）

本文件刻意把“可复制的大段模板”独立出来，避免 RUN 阶段一次性加载过多文本。

---

## 1) 主 agent：`sessions_spawn` 参数模板（强制 lightContext）

```json
{
  "runtime": "subagent",
  "lightContext": true,
  "runTimeoutSeconds": 86400,
  "cleanup": "keep",
  "task": "（粘贴本文件 2/3/4 的 subagent 任务要求）"
}
```

---

## 2) subagent：启动脚本（后台 + 超时 + conda）

subagent 必须用 `exec` 启动，并立刻后台化：

- `background=true`（或 `yieldMs=0`）
- **必须显式** `timeout=86400`（秒）
- **必须**用 conda 环境运行：
  - `conda run -n trade-buy python trade_buy/watch_buy_signal.py ...`

---

## 3) subagent：检查频率与方式（强制 30 秒）

- 状态检查只允许用 `process poll(timeout=30000)`（毫秒）驱动
- 每次 poll 返回后再 `process log` 读取尾部并解析 JSON 单行
- **禁止**用 `exec sleep ...` 或 exec 模拟定时器
- `process poll/log` 临时失败要有限次退避重试；超过次数必须 `sessions_send` 通知并停止

---

## 4) subagent：通知主 agent（`sessions_send` 固定模板）

命中（signal）：

```json
{
  "sessionKey": "main",
  "timeoutSeconds": 0,
  "message": "[trade-buy] BUY signal triggered for ETHUSDT (5m RSI14>70)\nJSON: {...}"
}
```

超时（timeout）：

```json
{
  "sessionKey": "main",
  "timeoutSeconds": 0,
  "message": "[trade-buy] No signal within 24h for ETHUSDT (5m RSI14>70)\nJSON: {...}"
}
```

说明：

- `sessionKey` 必须指向主会话（常见 `main`），不要指向 subagent 子会话。
- `timeoutSeconds: 0` 让 subagent 不阻塞等待；`sessions_send` 会继续完成 announce 投递流程。

