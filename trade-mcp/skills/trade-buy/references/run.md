# trade-buy · references：RUN（spawn subagent 后台盯盘 + 通知）

本阶段目标：在你确认 workspace 下的脚本 OK 后，主 agent 使用 `sessions_spawn` 启动 subagent，在后台运行脚本，直到命中信号或超时，并用 `sessions_send` 通知主 agent → 主 agent 再投递到通讯渠道。

---

## 1) 主 agent：spawn subagent（强制 lightContext）

主 agent 调 `sessions_spawn`（runtime=subagent）必须：

- `lightContext: true`（强制，lightweight bootstrap）
- `runTimeoutSeconds: 86400`（默认 24h，可按需改）
- `task`: 必须包含“如何启动脚本/如何轮询/如何 sessions_send”三件事

推荐参数模板：

见 `run.templates.md` 的可复制模板（避免本文件过长）。

---

## 2) subagent：启动脚本（后台 + 超时）

subagent 必须用 `exec` 启动，并立刻后台化：

- `background=true`（或 `yieldMs=0`）
- **必须显式** `timeout=86400`（秒）
- **必须**用 conda 环境运行：
  - `conda run -n trade-buy python trade_buy/watch_buy_signal.py ...`

---

## 3) subagent：检查频率与方式（强制 30 秒）

subagent 必须遵守：

- 状态检查只允许用 `process poll(timeout=30000)`（毫秒）驱动
- 每次 poll 返回后再 `process log` 读取尾部并解析 JSON 单行
- **禁止**用 `exec sleep ...` 或 exec 模拟定时器
- `process poll/log` 临时失败要有限次退避重试；超过次数必须 `sessions_send` 通知并停止

---

## 4) subagent：通知主 agent（`sessions_send` 固定模板）

见 `run.templates.md` 的可复制模板（避免本文件过长）。

