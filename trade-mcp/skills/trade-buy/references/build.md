# trade-buy · references：BUILD（生成/迭代脚本，人工确认后再 RUN）

本阶段目标：由主 agent 在 **workspace** 下生成盯盘脚本（`trade_buy/`），并允许你通过消息渠道多轮迭代修正，直到你人工确认脚本 OK。

**本阶段不负责运行 subagent。**

---

## 1) 产物位置（强制：`<workspace>/trade_buy/`）

与 **`SKILL.md`** 顶层约定一致：脚本与依赖文件必须生成在 **当前 Agent 工作目录** 下（相对于 workspace 根目录）：

- `trade_buy/watch_buy_signal.py`
- `trade_buy/trade_mcp_client.py`
- `trade_buy/requirements.txt`
- `trade_buy/environment.yml`（conda 环境定义，环境名固定为 `trade-buy`）

可选：

- `trade_buy/README.md`

仓库内的 `skills/trade-buy/trade-buy/` 仅作模板参考，运行以 workspace 产物为准。

---

## 2) conda 环境（提前安装依赖）

服务器使用 conda 时，本技能要求依赖提前安装在 conda 环境 **`trade-buy`** 中。

在 workspace 根目录执行（推荐）：

```bash
conda env create -f trade_buy/environment.yml -n trade-buy || \
conda env update -f trade_buy/environment.yml -n trade-buy
```

## 2.1 trade-mcp MCP server 地址（固定）

本技能约定 trade-mcp 的 MCP server 地址为固定值：

- `TRADE_MCP_URL=http://154.89.148.172:8099/sse`

在运行/测试脚本前，必须在环境中设置该变量（例如在 subagent `exec` 环境或系统环境里）：

```bash
export TRADE_MCP_URL="http://154.89.148.172:8099/sse"
```

或使用 requirements（可选）：

```bash
conda create -n trade-buy python=3.11 -y
conda run -n trade-buy python -m pip install -r trade_buy/requirements.txt
```

---

## 3) 脚本运行契约（必须满足）

脚本必须：

- 循环执行直到命中或超时
- 默认每 10 秒查询一次（脚本内部）
- 默认最大 24 小时（脚本内部）
- 终止前输出且仅输出一次 JSON 单行（命中/超时），用于 subagent 解析与通知

JSON 单行形状见 `build.contract.md`。

---

## 4) 人工确认 checklist（建议）

在进入 RUN 之前，建议你确认：

- `TRADE_MCP_URL` 配置正确、可连通
- `conda run -n trade-buy python trade_buy/watch_buy_signal.py --help` 可运行
- 用短参数快速验证超时路径：
  - `--max-seconds 30 --poll-interval-seconds 5` 能在 30 秒后输出 timeout JSON 并退出
- 如果策略条件容易触发，验证 signal JSON 也能输出一次并退出

